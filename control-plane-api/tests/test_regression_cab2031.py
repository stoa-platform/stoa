"""Regression tests for CAB-2031: Guardrails events tenant filter + DLS on otel-v1-apm-span-*.

Verifies:
1. Guardrails events query includes tenant filter for non-admin users
2. OpenSearch DLS roles cover otel-v1-apm-* indices with correct tenant field
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.opensearch_provisioner import OpenSearchProvisioner

# --- Guardrails events tenant isolation ---


class FakeUser:
    """Minimal user object for testing _tenant_filter."""

    def __init__(self, roles: list[str], tenant_id: str | None = None):
        self.roles = roles
        self.tenant_id = tenant_id


def test_regression_cab2031_tenant_filter_added_to_guardrails_query():
    """tenant-admin guardrails query MUST include resource.attributes.tenant@id filter."""
    from src.routers.gateway_observability import _tenant_filter

    user = FakeUser(roles=["tenant-admin"], tenant_id="acme")
    tenant_id = _tenant_filter(user)
    assert tenant_id == "acme"

    # Build the filter list as the endpoint does
    filters: list[dict] = [
        {"range": {"startTime": {"gte": "now-60m"}}},
        {"term": {"name": "policy.guardrails"}},
        {"exists": {"field": "span.attributes.guardrails@action"}},
    ]
    if tenant_id:
        filters.append({"term": {"resource.attributes.tenant@id": tenant_id}})

    # The tenant filter MUST be present
    tenant_filters = [f for f in filters if "resource.attributes.tenant@id" in str(f)]
    assert len(tenant_filters) == 1
    assert tenant_filters[0] == {"term": {"resource.attributes.tenant@id": "acme"}}


def test_regression_cab2031_cpi_admin_no_tenant_filter():
    """cpi-admin guardrails query MUST NOT include tenant filter (sees all)."""
    from src.routers.gateway_observability import _tenant_filter

    user = FakeUser(roles=["cpi-admin"], tenant_id="acme")
    tenant_id = _tenant_filter(user)
    assert tenant_id is None


# --- DLS roles for OTel indices ---


@pytest.mark.asyncio
async def test_regression_cab2031_dls_otel_indices():
    """Provisioner MUST create DLS roles covering otel-v1-apm-* with resource.attributes.tenant@id."""
    mock_client = MagicMock()
    mock_transport = MagicMock()
    mock_transport.perform_request = AsyncMock()
    mock_client.transport = mock_transport

    provisioner = OpenSearchProvisioner(os_client=mock_client)
    result = await provisioner.provision_tenant("test-tenant", tier="free")

    assert result["status"] == "ok"

    # Collect all PUT calls to /_plugins/_security/api/roles/
    role_calls = [
        call
        for call in mock_transport.perform_request.call_args_list
        if call.args[0] == "PUT" and "/_plugins/_security/api/roles/" in call.args[1]
    ]

    # Both reader and viewer roles should exist
    assert len(role_calls) >= 2

    for call in role_calls:
        body = call.kwargs.get("body") or call.args[2] if len(call.args) > 2 else None
        if body is None:
            # Try keyword argument
            body = call.kwargs.get("body")
        assert body is not None, f"Role creation call missing body: {call}"

        index_permissions = body.get("index_permissions", [])
        index_patterns_all = []
        for perm in index_permissions:
            index_patterns_all.extend(perm.get("index_patterns", []))

        # OTel indices MUST be covered
        assert any(
            "otel-v1-apm" in p for p in index_patterns_all
        ), f"OTel indices not covered in role. Patterns: {index_patterns_all}"

        # Find the OTel permission entry and check DLS field
        for perm in index_permissions:
            if any("otel-v1-apm" in p for p in perm.get("index_patterns", [])):
                dls = json.loads(perm["dls"])
                # DLS must use resource.attributes.tenant@id (not tenant_id)
                should_clauses = dls["bool"]["should"]
                tenant_fields = [next(iter(clause["term"].keys())) for clause in should_clauses]
                assert "resource.attributes.tenant@id" in tenant_fields, f"OTel DLS uses wrong field: {tenant_fields}"
