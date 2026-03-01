"""LLM Budget and Provider Config SQLAlchemy models (CAB-1491, CAB-1487)."""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class LlmProviderStatus(enum.StrEnum):
    """Status of an LLM provider configuration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    RATE_LIMITED = "rate_limited"


class LlmProvider(Base):
    """LLM provider configuration per tenant.

    Tracks which LLM providers (OpenAI, Anthropic, etc.) a tenant has configured,
    along with model preferences and cost parameters.
    """

    __tablename__ = "llm_providers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False)
    provider_name = Column(String(100), nullable=False)
    display_name = Column(String(255), nullable=True)
    default_model = Column(String(100), nullable=True)
    cost_per_input_token = Column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    cost_per_output_token = Column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    status = Column(
        SQLEnum(LlmProviderStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=LlmProviderStatus.ACTIVE,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_llm_providers_tenant_id", "tenant_id"),
        Index("ix_llm_providers_tenant_provider", "tenant_id", "provider_name", unique=True),
    )

    def __repr__(self) -> str:
        return f"<LlmProvider {self.id} tenant={self.tenant_id} provider={self.provider_name}>"


class LlmBudget(Base):
    """Monthly LLM spend budget per tenant.

    Tracks budget limits and current spending for LLM API calls.
    The gateway queries this to enforce spend limits in real-time.
    """

    __tablename__ = "llm_budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False, unique=True)
    monthly_limit_usd = Column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    current_spend_usd = Column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    alert_threshold_pct = Column(Integer, nullable=False, default=80)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (Index("ix_llm_budgets_tenant_id", "tenant_id"),)

    @property
    def usage_pct(self) -> float:
        """Current usage as percentage of monthly limit."""
        if not self.monthly_limit_usd or self.monthly_limit_usd <= 0:
            return 0.0
        return float((self.current_spend_usd / self.monthly_limit_usd) * 100)

    @property
    def remaining_usd(self) -> Decimal:
        """Remaining budget in USD."""
        return max(Decimal("0"), self.monthly_limit_usd - self.current_spend_usd)

    @property
    def is_over_budget(self) -> bool:
        """Whether current spend exceeds the monthly limit."""
        return self.current_spend_usd >= self.monthly_limit_usd and self.monthly_limit_usd > 0

    def __repr__(self) -> str:
        return (
            f"<LlmBudget {self.id} tenant={self.tenant_id} " f"spend={self.current_spend_usd}/{self.monthly_limit_usd}>"
        )


class LlmSpendEvent(Base):
    """Audit log of individual LLM spend events (CAB-1487).

    Captures per-request cost data for analytics and anomaly detection.
    Written by the service layer when recording spend; never modified after insert.
    """

    __tablename__ = "llm_spend_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(255), nullable=False)
    provider_name = Column(String(100), nullable=False)
    model = Column(String(100), nullable=True)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    latency_seconds = Column(Numeric(8, 4), nullable=True)
    cached = Column(Integer, nullable=False, default=0)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_llm_spend_events_tenant_id", "tenant_id"),
        Index("ix_llm_spend_events_created_at", "created_at"),
        Index("ix_llm_spend_events_tenant_created", "tenant_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<LlmSpendEvent {self.id} tenant={self.tenant_id} provider={self.provider_name} cost={self.cost_usd}>"
