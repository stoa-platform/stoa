"""Tests for BillingService — cost computation + alert engine (CAB-1457).

Covers:
- compute_cost with standard/premium tiers, edge cases
- check_alerts with 50%/80%/100% thresholds, idempotent firing
- get_department_spend aggregation
- reset_monthly_alerts
- Webhook payload has NO PII (no user_id/email fields)
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.billing_service import (
    BASE_COST,
    LATENCY_COST_PER_MS,
    MICROCENTS_PER_USD,
    PREMIUM_MULTIPLIER,
    TOKEN_COST_PER_TOKEN,
    BillingService,
)

# ---------------------------------------------------------------------------
# compute_cost — pure function, no DB
# ---------------------------------------------------------------------------


class TestComputeCost:
    """Tests for BillingService.compute_cost."""

    def test_standard_tier_basic(self) -> None:
        """Standard tier: base + tokens + latency."""
        cost = BillingService.compute_cost(token_count=100, latency_ms=200, tool_tier="standard")
        expected = int(BASE_COST + (TOKEN_COST_PER_TOKEN * 100) + (LATENCY_COST_PER_MS * 200))
        assert cost == expected

    def test_premium_tier_doubles_cost(self) -> None:
        """Premium tier applies 2x multiplier."""
        standard = BillingService.compute_cost(token_count=100, latency_ms=200, tool_tier="standard")
        premium = BillingService.compute_cost(token_count=100, latency_ms=200, tool_tier="premium")
        assert premium == standard * PREMIUM_MULTIPLIER

    def test_zero_tokens_zero_latency(self) -> None:
        """Minimum cost is the base cost."""
        cost = BillingService.compute_cost(token_count=0, latency_ms=0, tool_tier="standard")
        assert cost == BASE_COST

    def test_large_token_count(self) -> None:
        """High token count produces proportional cost."""
        cost = BillingService.compute_cost(token_count=1_000_000, latency_ms=0, tool_tier="standard")
        expected = int(BASE_COST + TOKEN_COST_PER_TOKEN * 1_000_000)
        assert cost == expected

    def test_returns_integer(self) -> None:
        """Cost is always an integer (micro-cents)."""
        cost = BillingService.compute_cost(token_count=33, latency_ms=17, tool_tier="standard")
        assert isinstance(cost, int)

    def test_unknown_tier_treated_as_standard(self) -> None:
        """Non-'premium' tiers default to standard pricing (no multiplier)."""
        standard = BillingService.compute_cost(token_count=100, latency_ms=50, tool_tier="standard")
        unknown = BillingService.compute_cost(token_count=100, latency_ms=50, tool_tier="basic")
        assert standard == unknown


# ---------------------------------------------------------------------------
# check_alerts — async, mocked DB
# ---------------------------------------------------------------------------


def _make_budget(
    department_id: str = "engineering",
    tenant_id: uuid.UUID | None = None,
    monthly_budget_usd: float = 100.0,
    webhook_url: str = "https://hooks.example.com/billing",
    thresholds: dict | None = None,
    fired: dict | None = None,
) -> MagicMock:
    """Create a mock DepartmentBudget row."""
    budget = MagicMock()
    budget.id = uuid.uuid4()
    budget.department_id = department_id
    budget.tenant_id = tenant_id or uuid.uuid4()
    budget.monthly_budget_usd = Decimal(str(monthly_budget_usd))
    budget.alert_webhook_url = webhook_url
    budget.alert_thresholds = thresholds or {"50": False, "80": True, "100": True}
    budget.alerts_fired_this_month = fired or {}
    return budget


class TestCheckAlerts:
    """Tests for BillingService.check_alerts."""

    @pytest.mark.asyncio
    async def test_no_budget_does_nothing(self) -> None:
        """If no budget exists, no webhook is called."""
        db = AsyncMock()
        # scalar_one_or_none returns None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=result_mock)

        with patch("src.services.billing_service.httpx.AsyncClient") as mock_client:
            await BillingService.check_alerts(db, "no-dept", uuid.uuid4())
            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_fires_at_80_percent(self) -> None:
        """When spend >= 80% and 80% threshold is enabled, webhook fires."""
        budget = _make_budget(monthly_budget_usd=100.0)
        tenant_id = budget.tenant_id

        db = AsyncMock()
        # First execute returns budget, second returns spend sum
        budget_result = MagicMock()
        budget_result.scalar_one_or_none.return_value = budget

        # Spend = 85 USD = 85 * 100_000_000 microcents
        spend_result = MagicMock()
        spend_result.scalar_one.return_value = 85 * MICROCENTS_PER_USD

        db.execute = AsyncMock(side_effect=[budget_result, spend_result, MagicMock()])

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.billing_service.httpx.AsyncClient", return_value=mock_client_instance):
            await BillingService.check_alerts(db, "engineering", tenant_id)

        # Verify webhook was called
        mock_client_instance.post.assert_called_once()
        call_args = mock_client_instance.post.call_args
        payload = call_args[1]["json"]

        # Verify NO PII in payload
        assert "user_id" not in payload
        assert "email" not in payload
        assert payload["department_id"] == "engineering"
        assert payload["threshold_pct"] == 80
        assert payload["spend_usd"] == 85.0
        assert payload["budget_usd"] == 100.0

    @pytest.mark.asyncio
    async def test_idempotent_no_double_fire(self) -> None:
        """Calling check_alerts twice at same spend does not fire again."""
        budget = _make_budget(
            monthly_budget_usd=100.0,
            fired={"80": True},  # Already fired
        )

        db = AsyncMock()
        budget_result = MagicMock()
        budget_result.scalar_one_or_none.return_value = budget

        spend_result = MagicMock()
        spend_result.scalar_one.return_value = 85 * MICROCENTS_PER_USD

        db.execute = AsyncMock(side_effect=[budget_result, spend_result])

        with patch("src.services.billing_service.httpx.AsyncClient") as mock_client:
            await BillingService.check_alerts(db, "engineering", budget.tenant_id)
            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_fires_100_percent_threshold(self) -> None:
        """When spend >= 100%, the 100% threshold fires."""
        budget = _make_budget(monthly_budget_usd=50.0)

        db = AsyncMock()
        budget_result = MagicMock()
        budget_result.scalar_one_or_none.return_value = budget

        spend_result = MagicMock()
        spend_result.scalar_one.return_value = 55 * MICROCENTS_PER_USD  # 110%

        db.execute = AsyncMock(side_effect=[budget_result, spend_result, MagicMock()])

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.billing_service.httpx.AsyncClient", return_value=mock_client_instance):
            await BillingService.check_alerts(db, "engineering", budget.tenant_id)

        # Should fire for both 80% and 100% (spend is 110%)
        assert mock_client_instance.post.call_count == 2

    @pytest.mark.asyncio
    async def test_50_percent_disabled_by_default(self) -> None:
        """50% threshold is disabled by default, so no alert fires at 60% spend."""
        budget = _make_budget(monthly_budget_usd=100.0)

        db = AsyncMock()
        budget_result = MagicMock()
        budget_result.scalar_one_or_none.return_value = budget

        spend_result = MagicMock()
        spend_result.scalar_one.return_value = 60 * MICROCENTS_PER_USD  # 60%

        db.execute = AsyncMock(side_effect=[budget_result, spend_result])

        with patch("src.services.billing_service.httpx.AsyncClient") as mock_client:
            await BillingService.check_alerts(db, "engineering", budget.tenant_id)
            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_webhook_url_skips_alerts(self) -> None:
        """If webhook URL is None, alerts are skipped entirely."""
        budget = _make_budget(webhook_url=None)  # type: ignore[arg-type]

        db = AsyncMock()
        budget_result = MagicMock()
        budget_result.scalar_one_or_none.return_value = budget

        db.execute = AsyncMock(return_value=budget_result)

        with patch("src.services.billing_service.httpx.AsyncClient") as mock_client:
            await BillingService.check_alerts(db, "engineering", budget.tenant_id)
            mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_webhook_payload_has_no_pii(self) -> None:
        """Verify webhook payload contains NO user_id or email fields."""
        budget = _make_budget(monthly_budget_usd=100.0)

        db = AsyncMock()
        budget_result = MagicMock()
        budget_result.scalar_one_or_none.return_value = budget

        spend_result = MagicMock()
        spend_result.scalar_one.return_value = 90 * MICROCENTS_PER_USD

        db.execute = AsyncMock(side_effect=[budget_result, spend_result, MagicMock()])

        mock_resp = AsyncMock()
        mock_resp.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_resp)
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.billing_service.httpx.AsyncClient", return_value=mock_client_instance):
            await BillingService.check_alerts(db, "engineering", budget.tenant_id)

        payload = mock_client_instance.post.call_args[1]["json"]
        forbidden_keys = {"user_id", "email", "username", "name", "ip_address"}
        assert not forbidden_keys.intersection(payload.keys()), f"PII detected in webhook payload: {payload.keys()}"


# ---------------------------------------------------------------------------
# get_department_spend — async, mocked DB
# ---------------------------------------------------------------------------


class TestGetDepartmentSpend:
    """Tests for BillingService.get_department_spend."""

    @pytest.mark.asyncio
    async def test_returns_usd_from_microcents(self) -> None:
        """Microcents are correctly converted to USD."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 5_000_000_000  # 50 USD
        db.execute = AsyncMock(return_value=result_mock)

        spend = await BillingService.get_department_spend(db, "engineering", "2026-02")
        assert spend == 50.0

    @pytest.mark.asyncio
    async def test_zero_spend(self) -> None:
        """No ledger rows returns 0 USD."""
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 0
        db.execute = AsyncMock(return_value=result_mock)

        spend = await BillingService.get_department_spend(db, "marketing", "2026-01")
        assert spend == 0.0


# ---------------------------------------------------------------------------
# reset_monthly_alerts — async, mocked DB
# ---------------------------------------------------------------------------


class TestResetMonthlyAlerts:
    """Tests for BillingService.reset_monthly_alerts."""

    @pytest.mark.asyncio
    async def test_calls_update(self) -> None:
        """reset_monthly_alerts issues an UPDATE and flush."""
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()

        await BillingService.reset_monthly_alerts(db)

        db.execute.assert_called_once()
        db.flush.assert_called_once()
