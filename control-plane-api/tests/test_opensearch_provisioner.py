"""Tests for OpenSearch Provisioner (CAB-1685).

Tests cover:
- Tenant provisioning (role + mapping creation, ISM assignment)
- Tenant deprovisioning (role + mapping deletion)
- Role mapping updates (user membership changes)
- Tier changes (ISM policy reassignment)
- Error handling (partial failures, no client)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.opensearch_provisioner import (
    PII_FIELDS,
    TIER_ISM_POLICIES,
    OpenSearchProvisioner,
)


@pytest.fixture
def mock_client():
    """Create a mock OpenSearch client with transport.perform_request."""
    client = MagicMock()
    client.transport = MagicMock()
    client.transport.perform_request = AsyncMock(return_value={"status": "OK"})
    return client


@pytest.fixture
def provisioner(mock_client):
    """Create a provisioner with a mock client."""
    p = OpenSearchProvisioner(os_client=mock_client)
    return p


@pytest.fixture
def provisioner_no_client():
    """Create a provisioner without a client."""
    return OpenSearchProvisioner(os_client=None)


class TestProvisionTenant:
    @pytest.mark.asyncio
    async def test_creates_reader_and_viewer_roles(self, provisioner, mock_client):
        result = await provisioner.provision_tenant("acme-corp")

        assert result["status"] == "ok"
        assert "stoa_gw_tenant_acme_corp" in result["roles_created"]
        assert "stoa_gw_viewer_acme_corp" in result["roles_created"]
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_reader_role_has_dls_no_fls(self, provisioner, mock_client):
        await provisioner.provision_tenant("acme-corp")

        # Find the PUT call for reader role
        calls = mock_client.transport.perform_request.call_args_list
        reader_call = next(c for c in calls if "stoa_gw_tenant_acme_corp" in str(c) and "roles/" in str(c))

        body = reader_call.kwargs.get("body") or reader_call[1].get("body") or reader_call[0][2]
        index_perm = body["index_permissions"][0]
        assert "dls" in index_perm
        assert '"acme-corp"' in index_perm["dls"]
        assert '"platform"' in index_perm["dls"]  # includes shared platform docs
        assert "fls" not in index_perm

    @pytest.mark.asyncio
    async def test_reader_role_covers_audit_index(self, provisioner, mock_client):
        await provisioner.provision_tenant("acme-corp")

        calls = mock_client.transport.perform_request.call_args_list
        reader_call = next(c for c in calls if "stoa_gw_tenant_acme_corp" in str(c) and "roles/" in str(c))

        body = reader_call.kwargs.get("body") or reader_call[1].get("body") or reader_call[0][2]
        index_perm = body["index_permissions"][0]
        assert "audit*" in index_perm["index_patterns"]
        assert "stoa-gw-*" in index_perm["index_patterns"]

    @pytest.mark.asyncio
    async def test_viewer_role_has_dls_and_fls(self, provisioner, mock_client):
        await provisioner.provision_tenant("acme-corp")

        calls = mock_client.transport.perform_request.call_args_list
        viewer_call = next(c for c in calls if "stoa_gw_viewer_acme_corp" in str(c) and "roles/" in str(c))

        body = viewer_call.kwargs.get("body") or viewer_call[1].get("body") or viewer_call[0][2]
        index_perm = body["index_permissions"][0]
        assert "dls" in index_perm
        assert "fls" in index_perm
        for field in PII_FIELDS:
            assert f"~{field}" in index_perm["fls"]

    @pytest.mark.asyncio
    async def test_creates_role_mappings(self, provisioner, mock_client):
        await provisioner.provision_tenant("acme-corp")

        calls = mock_client.transport.perform_request.call_args_list
        mapping_calls = [c for c in calls if "rolesmapping/" in str(c)]
        assert len(mapping_calls) == 2  # reader + viewer

    @pytest.mark.asyncio
    async def test_free_tier_no_explicit_ism(self, provisioner, mock_client):
        result = await provisioner.provision_tenant("acme-corp", tier="free")

        assert "ism_policy" not in result
        # No ISM add call (free tier uses default ism_template)
        calls = mock_client.transport.perform_request.call_args_list
        ism_calls = [c for c in calls if "/_plugins/_ism/add" in str(c)]
        assert len(ism_calls) == 0

    @pytest.mark.asyncio
    async def test_pro_tier_assigns_ism_policy(self, provisioner, mock_client):
        result = await provisioner.provision_tenant("acme-corp", tier="pro")

        assert result["ism_policy"] == "gateway-logs-pro"
        calls = mock_client.transport.perform_request.call_args_list
        ism_calls = [c for c in calls if "/_plugins/_ism/add" in str(c)]
        assert len(ism_calls) == 1

    @pytest.mark.asyncio
    async def test_enterprise_tier_assigns_ism_policy(self, provisioner, mock_client):
        result = await provisioner.provision_tenant("acme-corp", tier="enterprise")

        assert result["ism_policy"] == "gateway-logs-enterprise"

    @pytest.mark.asyncio
    async def test_no_client_returns_skipped(self, provisioner_no_client):
        result = await provisioner_no_client.provision_tenant("acme-corp")
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_partial_failure(self, provisioner, mock_client):
        """If one role creation fails, the other still succeeds."""
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Fail on the second PUT (viewer role creation)
            if call_count == 2 and "roles/" in str(args):
                raise Exception("OS connection timeout")
            return {"status": "OK"}

        mock_client.transport.perform_request = AsyncMock(side_effect=side_effect)

        result = await provisioner.provision_tenant("acme-corp")
        assert result["status"] == "partial"
        assert len(result["roles_created"]) >= 1
        assert len(result["errors"]) >= 1

    @pytest.mark.asyncio
    async def test_hyphenated_tenant_id_sanitized(self, provisioner, mock_client):
        """Hyphens in tenant_id are replaced with underscores for role names."""
        result = await provisioner.provision_tenant("oasis-gunters")

        assert "stoa_gw_tenant_oasis_gunters" in result["roles_created"]
        assert "stoa_gw_viewer_oasis_gunters" in result["roles_created"]

    @pytest.mark.asyncio
    async def test_dls_uses_original_tenant_id(self, provisioner, mock_client):
        """DLS filter uses the original tenant_id (with hyphens), not sanitized."""
        await provisioner.provision_tenant("oasis-gunters")

        calls = mock_client.transport.perform_request.call_args_list
        reader_call = next(c for c in calls if "stoa_gw_tenant_oasis_gunters" in str(c) and "roles/" in str(c))
        body = reader_call.kwargs.get("body") or reader_call[1].get("body") or reader_call[0][2]
        dls = body["index_permissions"][0]["dls"]
        assert "oasis-gunters" in dls
        assert "platform" in dls


class TestDeprovisionTenant:
    @pytest.mark.asyncio
    async def test_deletes_roles_and_mappings(self, provisioner, mock_client):
        result = await provisioner.deprovision_tenant("acme-corp")

        assert result["status"] == "ok"
        assert "stoa_gw_tenant_acme_corp" in result["roles_deleted"]
        assert "stoa_gw_viewer_acme_corp" in result["roles_deleted"]

    @pytest.mark.asyncio
    async def test_no_client_returns_skipped(self, provisioner_no_client):
        result = await provisioner_no_client.deprovision_tenant("acme-corp")
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_partial_failure_on_delete(self, provisioner, mock_client):
        call_count = 0

        async def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Fail on first role DELETE
                raise Exception("role not found")
            return {"status": "OK"}

        mock_client.transport.perform_request = AsyncMock(side_effect=side_effect)

        result = await provisioner.deprovision_tenant("acme-corp")
        assert result["status"] == "partial"

    @pytest.mark.asyncio
    async def test_mapping_delete_failure_non_blocking(self, provisioner, mock_client):
        """Role mapping deletion failure doesn't prevent role deletion."""

        async def side_effect(method, path, **kwargs):
            if "rolesmapping/" in path and method == "DELETE":
                raise Exception("mapping not found")
            return {"status": "OK"}

        mock_client.transport.perform_request = AsyncMock(side_effect=side_effect)

        result = await provisioner.deprovision_tenant("acme-corp")
        # Roles should still be deleted despite mapping failures
        assert len(result["roles_deleted"]) == 2


class TestUpdateRoleMapping:
    @pytest.mark.asyncio
    async def test_updates_reader_for_tenant_admin(self, provisioner, mock_client):
        await provisioner.update_role_mapping("acme-corp", "tenant-admin", ["alice", "bob"])

        mock_client.transport.perform_request.assert_called_once()
        call = mock_client.transport.perform_request.call_args
        assert "stoa_gw_tenant_acme_corp" in str(call)

    @pytest.mark.asyncio
    async def test_updates_reader_for_devops(self, provisioner, mock_client):
        await provisioner.update_role_mapping("acme-corp", "devops", ["deploy-bot"])

        call = mock_client.transport.perform_request.call_args
        assert "stoa_gw_tenant_acme_corp" in str(call)

    @pytest.mark.asyncio
    async def test_updates_viewer_for_viewer_role(self, provisioner, mock_client):
        await provisioner.update_role_mapping("acme-corp", "viewer", ["readonly-user"])

        call = mock_client.transport.perform_request.call_args
        assert "stoa_gw_viewer_acme_corp" in str(call)

    @pytest.mark.asyncio
    async def test_no_client_noop(self, provisioner_no_client):
        # Should not raise
        await provisioner_no_client.update_role_mapping("acme-corp", "viewer", ["user"])

    @pytest.mark.asyncio
    async def test_propagates_error(self, provisioner, mock_client):
        mock_client.transport.perform_request = AsyncMock(side_effect=Exception("connection refused"))

        with pytest.raises(Exception, match="connection refused"):
            await provisioner.update_role_mapping("acme-corp", "viewer", ["user"])


class TestUpdateTier:
    @pytest.mark.asyncio
    async def test_assigns_pro_policy(self, provisioner, mock_client):
        await provisioner.update_tier("acme-corp", "pro")

        call = mock_client.transport.perform_request.call_args
        assert "/_plugins/_ism/add" in str(call)
        body = call.kwargs.get("body") or call[0][2]
        assert body["policy_id"] == "gateway-logs-pro"

    @pytest.mark.asyncio
    async def test_assigns_enterprise_policy(self, provisioner, mock_client):
        await provisioner.update_tier("acme-corp", "enterprise")

        call = mock_client.transport.perform_request.call_args
        body = call.kwargs.get("body") or call[0][2]
        assert body["policy_id"] == "gateway-logs-enterprise"

    @pytest.mark.asyncio
    async def test_unknown_tier_noop(self, provisioner, mock_client):
        await provisioner.update_tier("acme-corp", "unknown")
        mock_client.transport.perform_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_client_noop(self, provisioner_no_client):
        await provisioner_no_client.update_tier("acme-corp", "pro")

    @pytest.mark.asyncio
    async def test_index_not_found_not_error(self, provisioner, mock_client):
        """If no indices exist yet, ISM assignment should not fail."""
        mock_client.transport.perform_request = AsyncMock(
            side_effect=Exception("index_not_found_exception")
        )

        # Should not raise — index_not_found is expected for new tenants
        await provisioner.update_tier("acme-corp", "pro")


class TestSetClient:
    def test_set_client(self):
        provisioner = OpenSearchProvisioner()
        assert provisioner._client is None

        mock = MagicMock()
        provisioner.set_client(mock)
        assert provisioner._client is mock
