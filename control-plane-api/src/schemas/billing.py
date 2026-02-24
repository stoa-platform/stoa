"""Pydantic schemas for billing endpoints (CAB-1457).

Department-level billing: budgets, charges, and budget-check responses.
No PII fields (no user_id, email) — billing is department-aggregate only.
"""

from pydantic import BaseModel, ConfigDict, Field


class BudgetSetRequest(BaseModel):
    """Request to create or update a department budget."""

    monthly_budget_usd: float = Field(..., gt=0, description="Monthly budget ceiling in USD")
    alert_webhook_url: str | None = Field(None, description="Webhook URL for budget alerts (encrypted at rest)")
    alert_thresholds: dict | None = Field(
        None,
        description='Threshold → enabled map, e.g. {"50": false, "80": true, "100": true}',
    )


class ChargeItem(BaseModel):
    """Single tool charge line item within a department's monthly bill."""

    tool_name: str
    tool_calls: int
    token_count: int
    cost_usd: float


class BudgetResponse(BaseModel):
    """Current budget status for a department."""

    department_id: str
    tenant_id: str
    monthly_budget_usd: float
    current_spend_usd: float
    remaining_usd: float
    pct_used: float
    period_month: str

    model_config = ConfigDict(from_attributes=True)


class DepartmentChargesResponse(BaseModel):
    """Itemized charges for a department in a billing period."""

    department_id: str
    period_month: str
    charges: list[ChargeItem]
    total_cost_usd: float


class BudgetCheckResponse(BaseModel):
    """Quick budget check result for gating tool calls."""

    department_id: str
    over_budget: bool
    pct_used: float
