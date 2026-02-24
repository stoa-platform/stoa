"""Pydantic schemas for billing and budget management (CAB-1457)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DepartmentBudgetCreate(BaseModel):
    """Schema for creating a department budget."""

    department_id: str = Field(..., min_length=1, max_length=255)
    department_name: str | None = Field(None, max_length=255)
    period: str = Field(default="monthly", pattern=r"^(monthly|quarterly)$")
    budget_limit_microcents: int = Field(..., ge=0)
    period_start: datetime
    warning_threshold_pct: int = Field(default=80, ge=0, le=100)
    critical_threshold_pct: int = Field(default=95, ge=0, le=100)
    enforcement: str = Field(default="disabled", pattern=r"^(enabled|disabled|warn_only)$")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "department_id": "engineering",
                "department_name": "Engineering Team",
                "period": "monthly",
                "budget_limit_microcents": 100_000_000,
                "period_start": "2026-03-01T00:00:00",
                "enforcement": "warn_only",
            }
        }
    )


class DepartmentBudgetUpdate(BaseModel):
    """Schema for updating a department budget (all fields optional)."""

    department_name: str | None = Field(None, max_length=255)
    budget_limit_microcents: int | None = Field(None, ge=0)
    warning_threshold_pct: int | None = Field(None, ge=0, le=100)
    critical_threshold_pct: int | None = Field(None, ge=0, le=100)
    enforcement: str | None = Field(None, pattern=r"^(enabled|disabled|warn_only)$")


class DepartmentBudgetResponse(BaseModel):
    """Schema for department budget response."""

    id: UUID
    tenant_id: str
    department_id: str
    department_name: str | None
    period: str
    budget_limit_microcents: int
    current_spend_microcents: int
    period_start: datetime
    warning_threshold_pct: int
    critical_threshold_pct: int
    enforcement: str
    usage_pct: float
    is_over_budget: bool
    created_by: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DepartmentBudgetListResponse(BaseModel):
    """Schema for paginated department budget list."""

    items: list[DepartmentBudgetResponse]
    total: int
    page: int
    page_size: int


class BudgetCheckResponse(BaseModel):
    """Internal response for gateway budget check (GET /internal/budgets/{dept_id}/check)."""

    over_budget: bool
    enforcement: str = "disabled"
    usage_pct: float = 0.0
    budget_limit_microcents: int = 0
    current_spend_microcents: int = 0
