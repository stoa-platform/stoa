"""Pydantic schemas for LLM budget and provider config (CAB-1491)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LlmProviderCreate(BaseModel):
    """Schema for creating an LLM provider configuration."""

    provider_name: str = Field(..., min_length=1, max_length=100)
    display_name: str | None = Field(None, max_length=255)
    default_model: str | None = Field(None, max_length=100)
    cost_per_input_token: Decimal = Field(default=Decimal("0"), ge=0)
    cost_per_output_token: Decimal = Field(default=Decimal("0"), ge=0)
    status: str = Field(default="active", pattern=r"^(active|inactive|rate_limited)$")


class LlmProviderResponse(BaseModel):
    """Schema for LLM provider response."""

    id: UUID
    tenant_id: str
    provider_name: str
    display_name: str | None
    default_model: str | None
    cost_per_input_token: Decimal
    cost_per_output_token: Decimal
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LlmBudgetCreate(BaseModel):
    """Schema for creating an LLM budget."""

    monthly_limit_usd: Decimal = Field(..., ge=0)
    alert_threshold_pct: int = Field(default=80, ge=0, le=100)


class LlmBudgetUpdate(BaseModel):
    """Schema for updating an LLM budget (all fields optional)."""

    monthly_limit_usd: Decimal | None = Field(None, ge=0)
    alert_threshold_pct: int | None = Field(None, ge=0, le=100)


class LlmBudgetResponse(BaseModel):
    """Schema for LLM budget response."""

    id: UUID
    tenant_id: str
    monthly_limit_usd: Decimal
    current_spend_usd: Decimal
    alert_threshold_pct: int
    usage_pct: float
    remaining_usd: Decimal
    is_over_budget: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SpendSummaryResponse(BaseModel):
    """Summary of current spend vs budget."""

    tenant_id: str
    monthly_limit_usd: Decimal
    current_spend_usd: Decimal
    remaining_usd: Decimal
    usage_pct: float
    is_over_budget: bool
