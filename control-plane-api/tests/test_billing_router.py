"""Tests for Billing Router — CAB-1458

Covers: POST/GET/PUT/DELETE /v1/tenants/{tenant_id}/budgets
RBAC: cpi-admin can access any tenant; own tenant only for others.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

BILLING_SVC_PATH = "src.routers.billing.BillingService"


def _mock_budget(**overrides):
    """Build a MagicMock that mimics a DepartmentBudget ORM object."""
    bid = uuid4()
    now = datetime.utcnow()
    mock = MagicMock()
    defaults = {
        "id": bid,
        "tenant_id": "acme",
        "department_id": "engineering",
        "department_name": "Engineering Team",
        "period": "monthly",
        "budget_limit_microcents": 100_000_000,
        "current_spend_microcents": 20_000_000,
        "period_start": now,
        "warning_threshold_pct": 80,
        "critical_threshold_pct": 95,
        "enforcement": "warn_only",
        "usage_pct": 20.0,
        "is_over_budget": False,
        "created_by": "admin@acme.com",
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _mock_budget_response(budget):
    """Build a DepartmentBudgetResponse from a budget mock."""
    from src.schemas.billing import DepartmentBudgetResponse

    return DepartmentBudgetResponse(
        id=budget.id,
        tenant_id=budget.tenant_id,
        department_id=budget.department_id,
        department_name=budget.department_name,
        period=budget.period,
        budget_limit_microcents=budget.budget_limit_microcents,
        current_spend_microcents=budget.current_spend_microcents,
        period_start=budget.period_start,
        warning_threshold_pct=budget.warning_threshold_pct,
        critical_threshold_pct=budget.critical_threshold_pct,
        enforcement=budget.enforcement,
        usage_pct=budget.usage_pct,
        is_over_budget=budget.is_over_budget,
        created_by=budget.created_by,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


_VALID_BUDGET_PAYLOAD = {
    "department_id": "engineering",
    "department_name": "Engineering Team",
    "period": "monthly",
    "budget_limit_microcents": 100_000_000,
    "period_start": "2026-03-01T00:00:00",
    "warning_threshold_pct": 80,
    "critical_threshold_pct": 95,
    "enforcement": "warn_only",
}


# ============== RBAC ==============


class TestBillingRBAC:
    """Verify tenant access guard blocks cross-tenant access."""

    def test_create_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.post("/v1/tenants/acme/budgets", json=_VALID_BUDGET_PAYLOAD)

        assert resp.status_code == 403
        assert "denied" in resp.json()["detail"].lower()

    def test_list_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/tenants/acme/budgets")

        assert resp.status_code == 403

    def test_get_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get(f"/v1/tenants/acme/budgets/{uuid4()}")

        assert resp.status_code == 403

    def test_cpi_admin_can_access_any_tenant(self, app_with_cpi_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.list_budgets = AsyncMock(return_value=MagicMock(items=[], total=0, page=1, page_size=20))

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/budgets")

        assert resp.status_code == 200


# ============== Create Budget ==============


class TestCreateBudget:
    """POST /v1/tenants/{tenant_id}/budgets"""

    def test_create_success(self, app_with_tenant_admin, mock_db_session):
        budget = _mock_budget()
        budget_resp = _mock_budget_response(budget)
        mock_svc = MagicMock()
        mock_svc.create_budget = AsyncMock(return_value=budget_resp)

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.post("/v1/tenants/acme/budgets", json=_VALID_BUDGET_PAYLOAD)

        assert resp.status_code == 201
        data = resp.json()
        assert data["department_id"] == "engineering"
        assert data["tenant_id"] == "acme"

    def test_create_validates_required_fields(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/tenants/acme/budgets", json={})

        assert resp.status_code == 422

    def test_create_invalid_period(self, app_with_tenant_admin, mock_db_session):
        payload = {**_VALID_BUDGET_PAYLOAD, "period": "weekly"}
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/tenants/acme/budgets", json=payload)

        assert resp.status_code == 422

    def test_create_invalid_enforcement(self, app_with_tenant_admin, mock_db_session):
        payload = {**_VALID_BUDGET_PAYLOAD, "enforcement": "strict_mode"}
        with TestClient(app_with_tenant_admin) as client:
            resp = client.post("/v1/tenants/acme/budgets", json=payload)

        assert resp.status_code == 422


# ============== List Budgets ==============


class TestListBudgets:
    """GET /v1/tenants/{tenant_id}/budgets"""

    def test_list_empty(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.list_budgets = AsyncMock(return_value=MagicMock(items=[], total=0, page=1, page_size=20))

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/budgets")

        assert resp.status_code == 200

    def test_list_with_results(self, app_with_tenant_admin, mock_db_session):
        budget = _mock_budget()
        budget_resp = _mock_budget_response(budget)
        mock_svc = MagicMock()
        mock_svc.list_budgets = AsyncMock(return_value=MagicMock(items=[budget_resp], total=1, page=1, page_size=20))

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/budgets")

        assert resp.status_code == 200

    def test_list_passes_pagination_params(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.list_budgets = AsyncMock(return_value=MagicMock(items=[], total=0, page=2, page_size=5))

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get("/v1/tenants/acme/budgets?page=2&page_size=5")

        assert resp.status_code == 200
        mock_svc.list_budgets.assert_called_once_with("acme", 2, 5)


# ============== Get Budget ==============


class TestGetBudget:
    """GET /v1/tenants/{tenant_id}/budgets/{budget_id}"""

    def test_get_success(self, app_with_tenant_admin, mock_db_session):
        bid = uuid4()
        budget = _mock_budget(id=bid)
        budget_resp = _mock_budget_response(budget)
        mock_svc = MagicMock()
        mock_svc.get_budget = AsyncMock(return_value=budget_resp)

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/budgets/{bid}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["department_id"] == "engineering"

    def test_get_404_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.get_budget = AsyncMock(side_effect=ValueError("Budget not found"))

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.get(f"/v1/tenants/acme/budgets/{uuid4()}")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_invalid_uuid(self, app_with_tenant_admin, mock_db_session):
        with TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/tenants/acme/budgets/not-a-uuid")

        assert resp.status_code == 422


# ============== Update Budget ==============


class TestUpdateBudget:
    """PUT /v1/tenants/{tenant_id}/budgets/{budget_id}"""

    def test_update_success(self, app_with_tenant_admin, mock_db_session):
        bid = uuid4()
        budget = _mock_budget(id=bid, budget_limit_microcents=200_000_000)
        budget_resp = _mock_budget_response(budget)
        mock_svc = MagicMock()
        mock_svc.update_budget = AsyncMock(return_value=budget_resp)

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.put(
                f"/v1/tenants/acme/budgets/{bid}",
                json={"budget_limit_microcents": 200_000_000},
            )

        assert resp.status_code == 200

    def test_update_404_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.update_budget = AsyncMock(side_effect=ValueError("Budget not found"))

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.put(
                f"/v1/tenants/acme/budgets/{uuid4()}",
                json={"budget_limit_microcents": 200_000_000},
            )

        assert resp.status_code == 404


# ============== Delete Budget ==============


class TestDeleteBudget:
    """DELETE /v1/tenants/{tenant_id}/budgets/{budget_id}"""

    def test_delete_success(self, app_with_tenant_admin, mock_db_session):
        bid = uuid4()
        budget = _mock_budget(id=bid, tenant_id="acme")
        mock_svc = MagicMock()
        mock_svc.repo = MagicMock()
        mock_svc.repo.get_by_id = AsyncMock(return_value=budget)
        mock_svc.repo.delete = AsyncMock(return_value=None)

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.delete(f"/v1/tenants/acme/budgets/{bid}")

        assert resp.status_code == 204

    def test_delete_404_not_found(self, app_with_tenant_admin, mock_db_session):
        mock_svc = MagicMock()
        mock_svc.repo = MagicMock()
        mock_svc.repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.delete(f"/v1/tenants/acme/budgets/{uuid4()}")

        assert resp.status_code == 404

    def test_delete_404_wrong_tenant(self, app_with_tenant_admin, mock_db_session):
        bid = uuid4()
        budget = _mock_budget(id=bid, tenant_id="other-tenant")
        mock_svc = MagicMock()
        mock_svc.repo = MagicMock()
        mock_svc.repo.get_by_id = AsyncMock(return_value=budget)

        with (
            patch(BILLING_SVC_PATH, return_value=mock_svc),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.delete(f"/v1/tenants/acme/budgets/{bid}")

        assert resp.status_code == 404
