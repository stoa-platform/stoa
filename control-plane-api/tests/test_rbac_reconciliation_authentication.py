"""Authentication and tenant isolation for the tenant reconciliation routes."""

from __future__ import annotations

from unittest.mock import patch

import pytest

ROUTES = [
    ("get", "/v1/tenants/acme/reconciliation/drift"),
    ("post", "/v1/tenants/acme/reconciliation/sync"),
    ("get", "/v1/tenants/acme/reconciliation/status"),
]
IDS = ["drift", "sync", "status"]


@pytest.fixture
def reached():
    calls: list[str] = []

    async def fake(self, tenant_id):
        calls.append(tenant_id)
        return {}

    base = "src.routers.reconciliation.ReconciliationService"
    with patch(f"{base}.check_drift", fake), patch(f"{base}.reconcile", fake), patch(f"{base}.get_status", fake):
        yield calls


@pytest.mark.parametrize(("verb", "url"), ROUTES, ids=IDS)
def test_anonymous_request_is_refused(client, reached, verb, url):
    response = getattr(client, verb)(url)
    assert response.status_code == 401, (response.status_code, reached)
    assert reached == []


@pytest.mark.parametrize(("verb", "url"), ROUTES, ids=IDS)
def test_other_tenant_is_refused(client_as_other_tenant, reached, verb, url):
    response = getattr(client_as_other_tenant, verb)(url)
    assert response.status_code == 403, (response.status_code, reached)
    assert reached == []
