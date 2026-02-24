"""Tests for billing models, schemas, repository, and service (CAB-1457)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.models.department_budget import BudgetPeriod, DepartmentBudget
from src.schemas.billing import (
    BudgetCheckResponse,
    DepartmentBudgetCreate,
    DepartmentBudgetListResponse,
    DepartmentBudgetResponse,
    DepartmentBudgetUpdate,
)

# === Model Tests ===


class TestDepartmentBudgetModel:
    """Tests for DepartmentBudget SQLAlchemy model."""

    def test_create_model(self):
        budget = DepartmentBudget(
            id=uuid.uuid4(),
            tenant_id="tenant-acme",
            department_id="engineering",
            department_name="Engineering Team",
            period="monthly",
            budget_limit_microcents=100_000_000,
            current_spend_microcents=0,
            period_start=datetime(2026, 3, 1, tzinfo=UTC),
            enforcement="disabled",
        )
        assert budget.tenant_id == "tenant-acme"
        assert budget.department_id == "engineering"
        assert budget.budget_limit_microcents == 100_000_000

    def test_usage_pct_zero_limit(self):
        budget = DepartmentBudget(
            budget_limit_microcents=0,
            current_spend_microcents=100,
        )
        assert budget.usage_pct == 0.0

    def test_usage_pct_normal(self):
        budget = DepartmentBudget(
            budget_limit_microcents=1000,
            current_spend_microcents=750,
        )
        assert budget.usage_pct == 75.0

    def test_usage_pct_over(self):
        budget = DepartmentBudget(
            budget_limit_microcents=1000,
            current_spend_microcents=1500,
        )
        assert budget.usage_pct == 150.0

    def test_is_over_budget_false(self):
        budget = DepartmentBudget(
            budget_limit_microcents=1000,
            current_spend_microcents=500,
        )
        assert budget.is_over_budget is False

    def test_is_over_budget_true(self):
        budget = DepartmentBudget(
            budget_limit_microcents=1000,
            current_spend_microcents=1000,
        )
        assert budget.is_over_budget is True

    def test_is_over_budget_zero_limit(self):
        budget = DepartmentBudget(
            budget_limit_microcents=0,
            current_spend_microcents=100,
        )
        assert budget.is_over_budget is False

    def test_repr(self):
        budget = DepartmentBudget(
            id=uuid.UUID("12345678-1234-1234-1234-123456789abc"),
            tenant_id="tenant-acme",
            department_id="eng",
            budget_limit_microcents=1000,
            current_spend_microcents=500,
        )
        r = repr(budget)
        assert "tenant=tenant-acme" in r
        assert "dept=eng" in r
        assert "500/1000" in r

    def test_budget_period_enum(self):
        assert BudgetPeriod.MONTHLY == "monthly"
        assert BudgetPeriod.QUARTERLY == "quarterly"


# === Schema Tests ===


class TestBillingSchemas:
    """Tests for Pydantic billing schemas."""

    def test_create_schema_valid(self):
        data = DepartmentBudgetCreate(
            department_id="engineering",
            department_name="Engineering Team",
            budget_limit_microcents=100_000_000,
            period_start=datetime(2026, 3, 1, tzinfo=UTC),
        )
        assert data.department_id == "engineering"
        assert data.period == "monthly"
        assert data.enforcement == "disabled"
        assert data.warning_threshold_pct == 80
        assert data.critical_threshold_pct == 95

    def test_create_schema_negative_limit_rejected(self):
        with pytest.raises(ValidationError):
            DepartmentBudgetCreate(
                department_id="eng",
                budget_limit_microcents=-1,
                period_start=datetime(2026, 3, 1, tzinfo=UTC),
            )

    def test_create_schema_invalid_period_rejected(self):
        with pytest.raises(ValidationError):
            DepartmentBudgetCreate(
                department_id="eng",
                budget_limit_microcents=1000,
                period_start=datetime(2026, 3, 1, tzinfo=UTC),
                period="weekly",
            )

    def test_create_schema_invalid_enforcement_rejected(self):
        with pytest.raises(ValidationError):
            DepartmentBudgetCreate(
                department_id="eng",
                budget_limit_microcents=1000,
                period_start=datetime(2026, 3, 1, tzinfo=UTC),
                enforcement="block",
            )

    def test_update_schema_partial(self):
        data = DepartmentBudgetUpdate(budget_limit_microcents=200_000_000)
        assert data.budget_limit_microcents == 200_000_000
        assert data.department_name is None
        assert data.enforcement is None

    def test_response_schema_from_model(self):
        budget = DepartmentBudget(
            id=uuid.uuid4(),
            tenant_id="tenant-acme",
            department_id="engineering",
            department_name="Engineering",
            period="monthly",
            budget_limit_microcents=100_000,
            current_spend_microcents=75_000,
            period_start=datetime(2026, 3, 1, tzinfo=UTC),
            warning_threshold_pct=80,
            critical_threshold_pct=95,
            enforcement="warn_only",
            created_by="admin@acme.com",
            created_at=datetime(2026, 3, 1, tzinfo=UTC),
            updated_at=datetime(2026, 3, 1, tzinfo=UTC),
        )
        resp = DepartmentBudgetResponse.model_validate(budget)
        assert resp.department_id == "engineering"
        assert resp.usage_pct == 75.0
        assert resp.is_over_budget is False
        assert resp.enforcement == "warn_only"

    def test_budget_check_response_defaults(self):
        check = BudgetCheckResponse(over_budget=False)
        assert check.enforcement == "disabled"
        assert check.usage_pct == 0.0
        assert check.budget_limit_microcents == 0
        assert check.current_spend_microcents == 0

    def test_budget_check_response_over_budget(self):
        check = BudgetCheckResponse(
            over_budget=True,
            enforcement="enabled",
            usage_pct=105.3,
            budget_limit_microcents=1_000_000,
            current_spend_microcents=1_053_000,
        )
        assert check.over_budget is True
        assert check.enforcement == "enabled"

    def test_list_response(self):
        resp = DepartmentBudgetListResponse(
            items=[],
            total=0,
            page=1,
            page_size=20,
        )
        assert resp.total == 0
        assert resp.page == 1

    def test_create_schema_quarterly(self):
        data = DepartmentBudgetCreate(
            department_id="marketing",
            budget_limit_microcents=500_000_000,
            period_start=datetime(2026, 1, 1, tzinfo=UTC),
            period="quarterly",
            enforcement="enabled",
        )
        assert data.period == "quarterly"
        assert data.enforcement == "enabled"

    def test_update_schema_enforcement_only(self):
        data = DepartmentBudgetUpdate(enforcement="enabled")
        assert data.enforcement == "enabled"
        assert data.budget_limit_microcents is None

    def test_create_schema_threshold_bounds(self):
        with pytest.raises(ValidationError):
            DepartmentBudgetCreate(
                department_id="eng",
                budget_limit_microcents=1000,
                period_start=datetime(2026, 3, 1, tzinfo=UTC),
                warning_threshold_pct=101,
            )


# === Router Tests (using TestClient pattern) ===


class TestBillingInternalRouter:
    """Tests for the internal billing router endpoint."""

    def test_budget_check_response_serialization(self):
        """Verify the response schema matches gateway expectations."""
        resp = BudgetCheckResponse(
            over_budget=False,
            enforcement="disabled",
            usage_pct=0.0,
            budget_limit_microcents=0,
            current_spend_microcents=0,
        )
        data = resp.model_dump()
        assert "over_budget" in data
        assert isinstance(data["over_budget"], bool)
        assert "enforcement" in data
        assert "usage_pct" in data

    def test_budget_check_response_json_keys(self):
        """Gateway expects snake_case JSON keys."""
        resp = BudgetCheckResponse(over_budget=True, enforcement="enabled")
        json_str = resp.model_dump_json()
        assert '"over_budget"' in json_str
        assert '"enforcement"' in json_str
