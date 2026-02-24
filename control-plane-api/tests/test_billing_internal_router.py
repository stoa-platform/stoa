"""Tests for billing internal router — GET /v1/internal/budgets/{department_id}/check (CAB-1457)."""

from unittest.mock import AsyncMock, patch

from src.schemas.billing import BudgetCheckResponse

# ── Helpers ──


def _make_budget_check_response(**overrides) -> BudgetCheckResponse:
    defaults = {
        "over_budget": False,
        "enforcement": "warn_only",
        "usage_pct": 42.5,
        "budget_limit_microcents": 100_000_000,
        "current_spend_microcents": 42_500_000,
    }
    defaults.update(overrides)
    return BudgetCheckResponse(**defaults)


# ── Tests ──


class TestCheckDepartmentBudget:
    """Tests for GET /v1/internal/budgets/{department_id}/check."""

    def test_check_budget_not_over(self, client_as_tenant_admin):
        """Returns over_budget=false when department is under budget."""
        mock_result = _make_budget_check_response(over_budget=False, usage_pct=42.5)

        with patch(
            "src.services.billing_service.BillingService.check_budget",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client_as_tenant_admin.get("/v1/internal/budgets/engineering/check")
        assert response.status_code == 200
        data = response.json()
        assert data["over_budget"] is False
        assert data["usage_pct"] == 42.5
        assert data["enforcement"] == "warn_only"

    def test_check_budget_over_budget(self, client_as_tenant_admin):
        """Returns over_budget=true when department exceeded the limit."""
        mock_result = _make_budget_check_response(
            over_budget=True,
            usage_pct=110.0,
            enforcement="enabled",
            current_spend_microcents=110_000_000,
        )

        with patch(
            "src.services.billing_service.BillingService.check_budget",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client_as_tenant_admin.get("/v1/internal/budgets/marketing/check")
        assert response.status_code == 200
        data = response.json()
        assert data["over_budget"] is True
        assert data["usage_pct"] == 110.0

    def test_check_budget_no_budget_configured(self, client_as_tenant_admin):
        """Fail-open: returns over_budget=false when no budget exists (404 scenario → default response)."""
        mock_result = _make_budget_check_response(
            over_budget=False,
            enforcement="disabled",
            usage_pct=0.0,
            budget_limit_microcents=0,
            current_spend_microcents=0,
        )

        with patch(
            "src.services.billing_service.BillingService.check_budget",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client_as_tenant_admin.get("/v1/internal/budgets/unknown-dept/check")
        assert response.status_code == 200
        data = response.json()
        assert data["over_budget"] is False
        assert data["enforcement"] == "disabled"

    def test_check_budget_service_exception_returns_500(self, app_with_tenant_admin):
        """Unhandled service exceptions return 500 (router has no try/except)."""
        from fastapi.testclient import TestClient

        with (
            patch(
                "src.services.billing_service.BillingService.check_budget",
                new_callable=AsyncMock,
                side_effect=Exception("DB connection failed"),
            ),
            TestClient(app_with_tenant_admin, raise_server_exceptions=False) as c,
        ):
            response = c.get("/v1/internal/budgets/engineering/check")
        assert response.status_code == 500

    def test_check_budget_department_id_in_path(self, client_as_tenant_admin):
        """Department ID is correctly passed from path to service."""
        mock_result = _make_budget_check_response()

        with patch(
            "src.services.billing_service.BillingService.check_budget",
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_svc:
            client_as_tenant_admin.get("/v1/internal/budgets/data-team/check")
            mock_svc.assert_called_once_with("data-team")

    def test_check_budget_response_schema(self, client_as_tenant_admin):
        """Response contains all BudgetCheckResponse fields."""
        mock_result = _make_budget_check_response(
            over_budget=False,
            enforcement="warn_only",
            usage_pct=75.0,
            budget_limit_microcents=50_000_000,
            current_spend_microcents=37_500_000,
        )

        with patch(
            "src.services.billing_service.BillingService.check_budget",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            response = client_as_tenant_admin.get("/v1/internal/budgets/ops/check")
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) >= {
            "over_budget",
            "enforcement",
            "usage_pct",
            "budget_limit_microcents",
            "current_spend_microcents",
        }
