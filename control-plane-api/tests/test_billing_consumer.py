"""Tests for billing metering consumer + billing CRUD router (CAB-1458)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.workers.billing_metering_consumer import (
    BillingMeteringConsumer,
    ToolCallMeteringEvent,
)

# ── ToolCallMeteringEvent schema ──


class TestToolCallMeteringEvent:
    def test_valid_event(self):
        evt = ToolCallMeteringEvent(
            tenant_id="t1",
            department_id="d1",
            cost_units_microcents=5000,
            token_count=100,
            tool_tier="premium",
        )
        assert evt.tenant_id == "t1"
        assert evt.department_id == "d1"
        assert evt.cost_units_microcents == 5000

    def test_defaults(self):
        evt = ToolCallMeteringEvent(tenant_id="t1")
        assert evt.department_id is None
        assert evt.cost_units_microcents == 0
        assert evt.token_count == 0
        assert evt.tool_tier == "standard"

    def test_from_dict(self):
        data = {"tenant_id": "t2", "department_id": "d2", "cost_units_microcents": 1000}
        evt = ToolCallMeteringEvent.model_validate(data)
        assert evt.tenant_id == "t2"
        assert evt.cost_units_microcents == 1000

    def test_missing_tenant_rejected(self):
        with pytest.raises(ValidationError):
            ToolCallMeteringEvent.model_validate({})


# ── BillingMeteringConsumer ──


class TestBillingMeteringConsumer:
    def test_init(self):
        consumer = BillingMeteringConsumer()
        assert consumer.TOPIC == "stoa.metering"
        assert consumer.GROUP == "billing-metering-consumer"
        assert consumer._running is False

    def test_skip_no_department(self):
        consumer = BillingMeteringConsumer()
        consumer._loop = MagicMock()
        msg = MagicMock()
        msg.value = {"tenant_id": "t1", "cost_units_microcents": 100}
        consumer._process_message_sync(msg)
        # No coroutine dispatched (department_id is None)

    def test_skip_zero_cost(self):
        consumer = BillingMeteringConsumer()
        consumer._loop = MagicMock()
        msg = MagicMock()
        msg.value = {
            "tenant_id": "t1",
            "department_id": "d1",
            "cost_units_microcents": 0,
        }
        consumer._process_message_sync(msg)
        # No coroutine dispatched (zero cost)

    @patch("src.workers.billing_metering_consumer.asyncio.run_coroutine_threadsafe")
    def test_dispatch_valid_event(self, mock_dispatch):
        consumer = BillingMeteringConsumer()
        consumer._loop = MagicMock()
        msg = MagicMock()
        msg.value = {
            "tenant_id": "t1",
            "department_id": "d1",
            "cost_units_microcents": 5000,
        }
        consumer._process_message_sync(msg)
        mock_dispatch.assert_called_once()

    def test_handle_invalid_json(self):
        consumer = BillingMeteringConsumer()
        consumer._loop = MagicMock()
        msg = MagicMock()
        msg.value = "not-a-dict"
        # Should not raise — logs warning internally
        consumer._process_message_sync(msg)

    @pytest.mark.asyncio
    async def test_handle_event_calls_record_spend(self):
        consumer = BillingMeteringConsumer()
        event = ToolCallMeteringEvent(
            tenant_id="t1",
            department_id="d1",
            cost_units_microcents=5000,
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
                tenant_id="t1",
                department_id="d1",
                amount_microcents=5000,
            )
            mock_session.commit.assert_called_once()


# ── Billing Router ──


class TestBillingRouter:
    def test_create_roundtrip(self):
        from src.schemas.billing import DepartmentBudgetCreate, DepartmentBudgetResponse

        now = datetime.now(tz=UTC)
        payload = DepartmentBudgetCreate(
            department_id="eng",
            budget_limit_microcents=100_000_000,
            period="monthly",
            period_start=now,
            enforcement="warn_only",
        )
        assert payload.department_id == "eng"
        assert payload.budget_limit_microcents == 100_000_000

        resp = DepartmentBudgetResponse(
            id=uuid4(),
            tenant_id="t1",
            department_id="eng",
            department_name="Engineering",
            budget_limit_microcents=100_000_000,
            current_spend_microcents=0,
            period="monthly",
            period_start=now,
            warning_threshold_pct=80,
            critical_threshold_pct=95,
            enforcement="warn_only",
            usage_pct=0.0,
            is_over_budget=False,
            created_by="admin@test.com",
            created_at=now,
            updated_at=now,
        )
        assert resp.department_id == "eng"

    def test_update_partial(self):
        from src.schemas.billing import DepartmentBudgetUpdate

        update = DepartmentBudgetUpdate(enforcement="enabled")
        dumped = update.model_dump(exclude_unset=True)
        assert dumped == {"enforcement": "enabled"}

    def test_list_empty(self):
        from src.schemas.billing import DepartmentBudgetListResponse

        resp = DepartmentBudgetListResponse(items=[], total=0, page=1, page_size=20)
        assert resp.total == 0
        assert len(resp.items) == 0

    def test_response_from_model_data(self):
        from src.schemas.billing import DepartmentBudgetResponse

        budget_id = uuid4()
        now = datetime.now(tz=UTC)
        data = {
            "id": budget_id,
            "tenant_id": "t1",
            "department_id": "eng",
            "department_name": "Engineering",
            "budget_limit_microcents": 50_000_000,
            "current_spend_microcents": 10_000_000,
            "period": "monthly",
            "period_start": now,
            "warning_threshold_pct": 80,
            "critical_threshold_pct": 95,
            "enforcement": "warn_only",
            "usage_pct": 20.0,
            "is_over_budget": False,
            "created_by": "admin@test.com",
            "created_at": now,
            "updated_at": now,
        }
        resp = DepartmentBudgetResponse(**data)
        assert resp.id == budget_id
        assert resp.current_spend_microcents == 10_000_000
