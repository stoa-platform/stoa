"""Integration tests for billing pipeline — metering → chargeback (CAB-1459).

Covers:
- Billing CRUD router (/v1/tenants/{tenant_id}/budgets) with RBAC
- Internal budget check endpoint (/v1/internal/budgets/{dept_id}/check)
- Full consumer → service → response cycle
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

SVC_PATH = "src.routers.billing.BillingService"
INTERNAL_SVC_PATH = "src.routers.billing_internal.BillingService"


def _mock_budget(**overrides):
    """Build a MagicMock that mimics a DepartmentBudget ORM object."""
    mock = MagicMock()
    defaults = {
        "id": uuid4(),
        "tenant_id": "acme",
        "department_id": "engineering",
        "department_name": "Engineering",
        "period": "monthly",
        "budget_limit_microcents": 100_000_000,
        "current_spend_microcents": 25_000_000,
        "period_start": datetime.now(tz=UTC),
        "warning_threshold_pct": 80,
        "critical_threshold_pct": 95,
        "enforcement": "warn_only",
        "usage_pct": 25.0,
        "is_over_budget": False,
        "created_by": "admin@acme.com",
        "created_at": datetime.now(tz=UTC),
        "updated_at": datetime.now(tz=UTC),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _budget_response(**overrides):
    """Build a DepartmentBudgetResponse dict."""
    from src.schemas.billing import DepartmentBudgetResponse

    budget = _mock_budget(**overrides)
    return DepartmentBudgetResponse.model_validate(budget)


def _budget_list_response(items=None, total=0, page=1, page_size=20):
    """Build a DepartmentBudgetListResponse."""
    from src.schemas.billing import DepartmentBudgetListResponse

    return DepartmentBudgetListResponse(
        items=items or [],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── Billing CRUD Router ──


class TestCreateBudget:
    """POST /v1/tenants/{tenant_id}/budgets"""

    def test_create_success(self, client_as_tenant_admin, mock_db_session):
        resp_data = _budget_response()
        with patch(SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.create_budget.return_value = resp_data
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/budgets",
                json={
                    "department_id": "engineering",
                    "budget_limit_microcents": 100_000_000,
                    "period": "monthly",
                    "period_start": datetime.now(tz=UTC).isoformat(),
                },
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["department_id"] == "engineering"
        assert body["budget_limit_microcents"] == 100_000_000

    def test_create_other_tenant_forbidden(self, client_as_other_tenant):
        resp = client_as_other_tenant.post(
            "/v1/tenants/acme/budgets",
            json={
                "department_id": "eng",
                "budget_limit_microcents": 1000,
                "period": "monthly",
                "period_start": datetime.now(tz=UTC).isoformat(),
            },
        )
        assert resp.status_code == 403

    def test_create_cpi_admin_cross_tenant(self, client_as_cpi_admin, mock_db_session):
        resp_data = _budget_response(tenant_id="other-tenant")
        with patch(SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.create_budget.return_value = resp_data
            resp = client_as_cpi_admin.post(
                "/v1/tenants/other-tenant/budgets",
                json={
                    "department_id": "eng",
                    "budget_limit_microcents": 50_000_000,
                    "period": "monthly",
                    "period_start": datetime.now(tz=UTC).isoformat(),
                },
            )
        assert resp.status_code == 201


class TestListBudgets:
    """GET /v1/tenants/{tenant_id}/budgets"""

    def test_list_empty(self, client_as_tenant_admin, mock_db_session):
        with patch(SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.list_budgets.return_value = _budget_list_response()
            resp = client_as_tenant_admin.get("/v1/tenants/acme/budgets")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_with_items(self, client_as_tenant_admin, mock_db_session):
        items = [_budget_response(), _budget_response(department_id="sales")]
        with patch(SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.list_budgets.return_value = _budget_list_response(items=items, total=2)
            resp = client_as_tenant_admin.get("/v1/tenants/acme/budgets")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_list_other_tenant_forbidden(self, client_as_other_tenant):
        resp = client_as_other_tenant.get("/v1/tenants/acme/budgets")
        assert resp.status_code == 403

    def test_list_pagination(self, client_as_tenant_admin, mock_db_session):
        with patch(SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.list_budgets.return_value = _budget_list_response(page=2, page_size=5)
            resp = client_as_tenant_admin.get("/v1/tenants/acme/budgets?page=2&page_size=5")
        assert resp.status_code == 200
        mock_svc.list_budgets.assert_called_once_with("acme", 2, 5)


class TestGetBudget:
    """GET /v1/tenants/{tenant_id}/budgets/{budget_id}"""

    def test_get_success(self, client_as_tenant_admin, mock_db_session):
        budget_id = uuid4()
        resp_data = _budget_response(id=budget_id)
        with patch(SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.get_budget.return_value = resp_data
            resp = client_as_tenant_admin.get(f"/v1/tenants/acme/budgets/{budget_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == str(budget_id)

    def test_get_not_found(self, client_as_tenant_admin, mock_db_session):
        budget_id = uuid4()
        with patch(SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.get_budget.side_effect = ValueError("not found")
            resp = client_as_tenant_admin.get(f"/v1/tenants/acme/budgets/{budget_id}")
        assert resp.status_code == 404

    def test_get_other_tenant_forbidden(self, client_as_other_tenant):
        resp = client_as_other_tenant.get(f"/v1/tenants/acme/budgets/{uuid4()}")
        assert resp.status_code == 403


class TestUpdateBudget:
    """PUT /v1/tenants/{tenant_id}/budgets/{budget_id}"""

    def test_update_enforcement(self, client_as_tenant_admin, mock_db_session):
        budget_id = uuid4()
        resp_data = _budget_response(id=budget_id, enforcement="enabled")
        with patch(SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_budget.return_value = resp_data
            resp = client_as_tenant_admin.put(
                f"/v1/tenants/acme/budgets/{budget_id}",
                json={"enforcement": "enabled"},
            )
        assert resp.status_code == 200
        assert resp.json()["enforcement"] == "enabled"

    def test_update_not_found(self, client_as_tenant_admin, mock_db_session):
        budget_id = uuid4()
        with patch(SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.update_budget.side_effect = ValueError("not found")
            resp = client_as_tenant_admin.put(
                f"/v1/tenants/acme/budgets/{budget_id}",
                json={"enforcement": "enabled"},
            )
        assert resp.status_code == 404


class TestDeleteBudget:
    """DELETE /v1/tenants/{tenant_id}/budgets/{budget_id}"""

    def test_delete_success(self, client_as_tenant_admin, mock_db_session):
        budget_id = uuid4()
        budget_obj = _mock_budget(id=budget_id, tenant_id="acme")
        with patch(SVC_PATH) as mock_cls:
            mock_svc = MagicMock()
            mock_svc.repo = AsyncMock()
            mock_svc.repo.get_by_id = AsyncMock(return_value=budget_obj)
            mock_svc.repo.delete = AsyncMock()
            mock_cls.return_value = mock_svc
            resp = client_as_tenant_admin.delete(f"/v1/tenants/acme/budgets/{budget_id}")
        assert resp.status_code == 204

    def test_delete_not_found(self, client_as_tenant_admin, mock_db_session):
        budget_id = uuid4()
        with patch(SVC_PATH) as mock_cls:
            mock_svc = MagicMock()
            mock_svc.repo = AsyncMock()
            mock_svc.repo.get_by_id = AsyncMock(return_value=None)
            mock_cls.return_value = mock_svc
            resp = client_as_tenant_admin.delete(f"/v1/tenants/acme/budgets/{budget_id}")
        assert resp.status_code == 404

    def test_delete_wrong_tenant(self, client_as_tenant_admin, mock_db_session):
        budget_id = uuid4()
        budget_obj = _mock_budget(id=budget_id, tenant_id="other-tenant")
        with patch(SVC_PATH) as mock_cls:
            mock_svc = MagicMock()
            mock_svc.repo = AsyncMock()
            mock_svc.repo.get_by_id = AsyncMock(return_value=budget_obj)
            mock_cls.return_value = mock_svc
            resp = client_as_tenant_admin.delete(f"/v1/tenants/acme/budgets/{budget_id}")
        assert resp.status_code == 404


# ── Internal Budget Check (Gateway Endpoint) ──


class TestBudgetCheck:
    """GET /v1/internal/budgets/{department_id}/check"""

    def test_no_budget_fail_open(self, client):
        """No budget configured → over_budget=false (fail-open design)."""
        from src.schemas.billing import BudgetCheckResponse

        resp_data = BudgetCheckResponse(over_budget=False, enforcement="disabled")
        with patch(INTERNAL_SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.check_budget.return_value = resp_data
            resp = client.get("/v1/internal/budgets/eng-dept/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["over_budget"] is False
        assert body["enforcement"] == "disabled"

    def test_under_budget(self, client):
        """Budget exists, under limit → over_budget=false."""
        from src.schemas.billing import BudgetCheckResponse

        resp_data = BudgetCheckResponse(
            over_budget=False,
            enforcement="enabled",
            usage_pct=45.0,
            budget_limit_microcents=100_000_000,
            current_spend_microcents=45_000_000,
        )
        with patch(INTERNAL_SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.check_budget.return_value = resp_data
            resp = client.get("/v1/internal/budgets/eng-dept/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["over_budget"] is False
        assert body["usage_pct"] == 45.0

    def test_over_budget_enforcement_enabled(self, client):
        """Budget exists, over limit, enforcement=enabled → over_budget=true."""
        from src.schemas.billing import BudgetCheckResponse

        resp_data = BudgetCheckResponse(
            over_budget=True,
            enforcement="enabled",
            usage_pct=110.0,
            budget_limit_microcents=100_000_000,
            current_spend_microcents=110_000_000,
        )
        with patch(INTERNAL_SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.check_budget.return_value = resp_data
            resp = client.get("/v1/internal/budgets/eng-dept/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["over_budget"] is True
        assert body["enforcement"] == "enabled"

    def test_over_budget_enforcement_disabled(self, client):
        """Budget over limit but enforcement=disabled → over_budget=false."""
        from src.schemas.billing import BudgetCheckResponse

        resp_data = BudgetCheckResponse(
            over_budget=False,
            enforcement="disabled",
            usage_pct=120.0,
            budget_limit_microcents=100_000_000,
            current_spend_microcents=120_000_000,
        )
        with patch(INTERNAL_SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.check_budget.return_value = resp_data
            resp = client.get("/v1/internal/budgets/eng-dept/check")
        assert resp.status_code == 200
        body = resp.json()
        assert body["over_budget"] is False

    def test_no_auth_required(self, client):
        """Internal endpoint requires no auth (gateway-facing)."""
        from src.schemas.billing import BudgetCheckResponse

        resp_data = BudgetCheckResponse(over_budget=False, enforcement="disabled")
        with patch(INTERNAL_SVC_PATH) as mock_cls:
            mock_svc = AsyncMock()
            mock_cls.return_value = mock_svc
            mock_svc.check_budget.return_value = resp_data
            # Using base client (no auth overrides) — should still work
            resp = client.get("/v1/internal/budgets/test-dept/check")
        assert resp.status_code == 200


# ── Metering Pipeline Integration ──


class TestMeteringPipeline:
    """Integration: metering event → consumer → BillingService.record_spend."""

    @pytest.mark.asyncio
    async def test_full_pipeline_event_to_spend(self):
        """Valid metering event flows through consumer to record_spend."""
        from src.workers.billing_metering_consumer import (
            BillingMeteringConsumer,
            ToolCallMeteringEvent,
        )

        consumer = BillingMeteringConsumer()
        event = ToolCallMeteringEvent(
            tenant_id="acme",
            department_id="engineering",
            cost_units_microcents=15000,
            token_count=500,
            tool_tier="premium",
        )

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.workers.billing_metering_consumer._get_session_factory",
                return_value=mock_session_factory,
            ),
            patch("src.workers.billing_metering_consumer.BillingService") as mock_svc_cls,
        ):
            mock_svc = AsyncMock()
            mock_svc_cls.return_value = mock_svc
            await consumer._handle_event(event)

            mock_svc.record_spend.assert_called_once_with(
                tenant_id="acme",
                department_id="engineering",
                amount_microcents=15000,
            )
            mock_session.commit.assert_called_once()

    def test_consumer_filters_no_department(self):
        """Events without department_id are silently skipped."""
        from src.workers.billing_metering_consumer import BillingMeteringConsumer

        consumer = BillingMeteringConsumer()
        consumer._loop = MagicMock()
        msg = MagicMock()
        msg.value = {"tenant_id": "acme", "cost_units_microcents": 5000}

        with patch("src.workers.billing_metering_consumer.asyncio.run_coroutine_threadsafe") as mock_dispatch:
            consumer._process_message_sync(msg)
            mock_dispatch.assert_not_called()

    def test_consumer_filters_zero_cost(self):
        """Events with zero cost are silently skipped."""
        from src.workers.billing_metering_consumer import BillingMeteringConsumer

        consumer = BillingMeteringConsumer()
        consumer._loop = MagicMock()
        msg = MagicMock()
        msg.value = {
            "tenant_id": "acme",
            "department_id": "eng",
            "cost_units_microcents": 0,
        }

        with patch("src.workers.billing_metering_consumer.asyncio.run_coroutine_threadsafe") as mock_dispatch:
            consumer._process_message_sync(msg)
            mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_record_spend_error_does_not_propagate(self):
        """Consumer gracefully handles BillingService errors."""
        from src.workers.billing_metering_consumer import (
            BillingMeteringConsumer,
            ToolCallMeteringEvent,
        )

        consumer = BillingMeteringConsumer()
        event = ToolCallMeteringEvent(
            tenant_id="acme",
            department_id="eng",
            cost_units_microcents=1000,
        )

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "src.workers.billing_metering_consumer._get_session_factory",
                return_value=mock_session_factory,
            ),
            patch("src.workers.billing_metering_consumer.BillingService") as mock_svc_cls,
        ):
            mock_svc = AsyncMock()
            mock_svc_cls.return_value = mock_svc
            mock_svc.record_spend.side_effect = RuntimeError("DB connection lost")

            # Should not raise — consumer logs warning internally
            await consumer._handle_event(event)
