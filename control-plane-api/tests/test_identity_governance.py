"""Unit tests for Identity Governance service (CAB-1483).

Tests:
- SCIM→Roles resolution
- OAuth metadata validation
- Protocol mapper generation
- DCR client registration (mocked DB + Keycloak)
- DCR client revocation
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.oauth_client import OAuthClient, OAuthClientStatus
from src.services.identity_governance import (
    ALLOWED_GRANT_TYPES,
    DEFAULT_ROLES_MATRIX,
    IdentityGovernanceService,
    build_protocol_mappers,
    resolve_product_roles,
    validate_oauth_metadata,
)

# ============ resolve_product_roles ============


class TestResolveProductRoles:
    def test_single_group(self):
        roles = resolve_product_roles(["api-readers"])
        assert roles == ["api:read"]

    def test_multiple_groups(self):
        roles = resolve_product_roles(["api-readers", "billing-users"])
        assert roles == ["api:read", "billing:read"]

    def test_overlapping_groups_deduplicated(self):
        roles = resolve_product_roles(["api-readers", "api-writers"])
        assert roles == ["api:read", "api:write"]

    def test_unknown_group_ignored(self):
        roles = resolve_product_roles(["unknown-group", "api-readers"])
        assert roles == ["api:read"]

    def test_empty_groups(self):
        roles = resolve_product_roles([])
        assert roles == []

    def test_custom_matrix(self):
        custom = {"dev": ["dev:read", "dev:write"]}
        roles = resolve_product_roles(["dev"], roles_matrix=custom)
        assert roles == ["dev:read", "dev:write"]

    def test_admin_group_gets_all_api_roles(self):
        roles = resolve_product_roles(["api-admins"])
        assert "api:admin" in roles
        assert "api:read" in roles
        assert "api:write" in roles


# ============ validate_oauth_metadata ============


class TestValidateOAuthMetadata:
    def test_none_metadata_ok(self):
        assert validate_oauth_metadata(None) == []

    def test_valid_grant_types(self):
        assert validate_oauth_metadata({"grant_types": ["client_credentials"]}) == []

    def test_invalid_grant_type(self):
        errors = validate_oauth_metadata({"grant_types": ["password"]})
        assert len(errors) == 1
        assert "Invalid grant_types" in errors[0]

    def test_https_redirect_uri(self):
        assert validate_oauth_metadata({"redirect_uris": ["https://app.example.com/callback"]}) == []

    def test_http_redirect_uri_rejected(self):
        errors = validate_oauth_metadata({"redirect_uris": ["http://insecure.com/callback"]})
        assert len(errors) == 1
        assert "HTTPS" in errors[0]

    def test_multiple_errors(self):
        errors = validate_oauth_metadata(
            {
                "grant_types": ["password"],
                "redirect_uris": ["http://bad.com"],
            }
        )
        assert len(errors) == 2


# ============ build_protocol_mappers ============


class TestBuildProtocolMappers:
    def test_tenant_id_mapper_always_present(self):
        mappers = build_protocol_mappers("acme", [])
        assert len(mappers) == 1
        assert mappers[0]["name"] == "tenant_id"
        assert mappers[0]["config"]["claim.value"] == "acme"

    def test_product_roles_mapper(self):
        mappers = build_protocol_mappers("acme", ["api:read", "api:write"])
        assert len(mappers) == 2
        roles_mapper = mappers[1]
        assert roles_mapper["name"] == "product_roles"
        assert roles_mapper["config"]["jsonType.label"] == "JSON"
        assert '"api:read"' in roles_mapper["config"]["claim.value"]

    def test_mapper_targets_access_token(self):
        mappers = build_protocol_mappers("t1", ["r1"])
        for m in mappers:
            assert m["config"]["access.token.claim"] == "true"
            assert m["config"]["id.token.claim"] == "false"


# ============ IdentityGovernanceService ============


class TestIdentityGovernanceService:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return IdentityGovernanceService(db=mock_db)

    @pytest.mark.asyncio
    async def test_register_client_no_keycloak(self, service, mock_db):
        """Register a client without Keycloak integration (DB-only)."""
        # Mock repo to return None for duplicate check, and pass-through for create
        with (
            patch.object(service.repo, "get_by_keycloak_client_id", return_value=None),
            patch.object(service.repo, "create", side_effect=lambda c: c),
            patch.object(service.audit, "record_event", return_value=AsyncMock()),
        ):
            client = await service.register_client(
                tenant_id="acme",
                client_name="billing-svc",
                product_roles=["api:read"],
            )
            assert client.tenant_id == "acme"
            assert client.client_name == "billing-svc"
            assert client.product_roles == ["api:read"]
            assert client.keycloak_client_id == "acme-billing-svc"
            assert client.status == OAuthClientStatus.ACTIVE.value

    @pytest.mark.asyncio
    async def test_register_client_duplicate_rejected(self, service):
        """Duplicate client_id raises ValueError."""
        existing = MagicMock(spec=OAuthClient)
        with patch.object(service.repo, "get_by_keycloak_client_id", return_value=existing):
            with pytest.raises(ValueError, match="already registered"):
                await service.register_client(
                    tenant_id="acme",
                    client_name="dup-svc",
                )

    @pytest.mark.asyncio
    async def test_register_client_invalid_metadata(self, service):
        """Invalid OAuth metadata raises ValueError."""
        with pytest.raises(ValueError, match="Invalid oauth_metadata"):
            await service.register_client(
                tenant_id="acme",
                client_name="bad-svc",
                oauth_metadata={"grant_types": ["password"]},
            )

    @pytest.mark.asyncio
    async def test_revoke_client(self, service):
        """Revoke sets status to REVOKED."""
        mock_client = MagicMock(spec=OAuthClient)
        mock_client.id = "c1"
        mock_client.tenant_id = "acme"
        mock_client.keycloak_uuid = None
        mock_client.keycloak_client_id = "acme-svc"

        with (
            patch.object(service.repo, "get_by_id", return_value=mock_client),
            patch.object(service.repo, "update_status", return_value=mock_client),
            patch.object(service.audit, "record_event", return_value=AsyncMock()),
        ):
            result = await service.revoke_client(client_id="c1", tenant_id="acme")
            assert result is True

    @pytest.mark.asyncio
    async def test_revoke_client_wrong_tenant(self, service):
        """Revoke fails if tenant doesn't match."""
        mock_client = MagicMock(spec=OAuthClient)
        mock_client.tenant_id = "other-tenant"

        with patch.object(service.repo, "get_by_id", return_value=mock_client):
            result = await service.revoke_client(client_id="c1", tenant_id="acme")
            assert result is False

    @pytest.mark.asyncio
    async def test_revoke_client_not_found(self, service):
        """Revoke fails if client doesn't exist."""
        with patch.object(service.repo, "get_by_id", return_value=None):
            result = await service.revoke_client(client_id="nonexistent", tenant_id="acme")
            assert result is False
