"""Internal gateway endpoints require a valid X-Gateway-Key (fail-closed).

Covers the four read endpoints polled by stoa-gateway and stoa-connect:
route table, API catalog, expanded catalog and department budget check.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import settings

VALID_KEY = "test-gateway-key"

INTERNAL_READ_ENDPOINTS = [
    "/v1/internal/gateways/routes",
    "/v1/internal/catalog/apis",
    "/v1/internal/catalog/apis/expanded",
    "/v1/internal/budgets/eng-dept/check",
]


@pytest.fixture
def backends():
    """Stub the data layer so an authorised call can succeed."""
    from src.schemas.billing import BudgetCheckResponse

    catalog_repo = MagicMock()
    catalog_repo.get_portal_apis = AsyncMock(return_value=([], 0))
    budget_svc = AsyncMock()
    budget_svc.check_budget.return_value = BudgetCheckResponse(over_budget=False, enforcement="disabled")
    with (
        patch("src.routers.gateway_internal.GatewayDeploymentRepository") as deploy_repo,
        patch("src.routers.portal.CatalogRepository", return_value=catalog_repo),
        patch("src.routers.billing_internal.BillingService", return_value=budget_svc),
    ):
        deploy_repo.return_value.list_by_statuses = AsyncMock(return_value=[])
        yield


@pytest.mark.parametrize("path", INTERNAL_READ_ENDPOINTS)
def test_missing_key_is_rejected(client, backends, monkeypatch, path):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", VALID_KEY)
    resp = client.get(path)
    assert resp.status_code == 401


@pytest.mark.parametrize("path", INTERNAL_READ_ENDPOINTS)
def test_wrong_key_is_rejected(client, backends, monkeypatch, path):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", VALID_KEY)
    resp = client.get(path, headers={"X-Gateway-Key": "not-the-key"})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", INTERNAL_READ_ENDPOINTS)
def test_empty_key_header_is_rejected(client, backends, monkeypatch, path):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", VALID_KEY)
    resp = client.get(path, headers={"X-Gateway-Key": ""})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", INTERNAL_READ_ENDPOINTS)
def test_no_configured_keys_fails_closed(client, backends, monkeypatch, path):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
    resp = client.get(path, headers={"X-Gateway-Key": VALID_KEY})
    assert resp.status_code == 503


@pytest.mark.parametrize("path", INTERNAL_READ_ENDPOINTS)
def test_valid_key_is_accepted(client, backends, monkeypatch, path):
    monkeypatch.setattr(settings, "GATEWAY_API_KEYS", f"other-key,{VALID_KEY}")
    resp = client.get(path, headers={"X-Gateway-Key": VALID_KEY})
    assert resp.status_code == 200
