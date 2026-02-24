"""DepartmentBudget SQLAlchemy model for chargeback and budget enforcement (CAB-1457)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Enum as SQLEnum, Index, String
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class BudgetPeriod(enum.StrEnum):
    """Budget period type."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class DepartmentBudget(Base):
    """Per-department monthly/quarterly budget for cost tracking and enforcement.

    The gateway queries this via /internal/budgets/{department_id}/check to
    enforce spend limits in real-time (fail-open: no record = allow).
    """

    __tablename__ = "department_budgets"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dimensions
    tenant_id = Column(String(255), nullable=False)
    department_id = Column(String(255), nullable=False)
    department_name = Column(String(255), nullable=True)

    # Budget configuration
    period = Column(
        SQLEnum(BudgetPeriod, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=BudgetPeriod.MONTHLY,
    )
    budget_limit_microcents = Column(BigInteger, nullable=False, default=0)

    # Current spend tracking (updated by metering consumer)
    current_spend_microcents = Column(BigInteger, nullable=False, default=0)
    period_start = Column(DateTime, nullable=False)

    # Alert thresholds (percentage of budget)
    warning_threshold_pct = Column(BigInteger, nullable=False, default=80)
    critical_threshold_pct = Column(BigInteger, nullable=False, default=95)

    # Enforcement
    enforcement = Column(
        SQLEnum("enabled", "disabled", "warn_only", name="budget_enforcement_enum", create_type=True),
        nullable=False,
        default="disabled",
    )

    # Audit
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes for common queries
    __table_args__ = (
        Index("ix_dept_budgets_tenant_dept", "tenant_id", "department_id"),
        Index("ix_dept_budgets_tenant_id", "tenant_id"),
        Index("ix_dept_budgets_dept_id", "department_id"),
        Index("ix_dept_budgets_period_start", "period_start"),
    )

    @property
    def usage_pct(self) -> float:
        """Current usage as percentage of budget limit."""
        if self.budget_limit_microcents <= 0:
            return 0.0
        return (self.current_spend_microcents / self.budget_limit_microcents) * 100

    @property
    def is_over_budget(self) -> bool:
        """Whether current spend exceeds the budget limit."""
        return self.current_spend_microcents >= self.budget_limit_microcents and self.budget_limit_microcents > 0

    def __repr__(self) -> str:
        return (
            f"<DepartmentBudget {self.id} tenant={self.tenant_id} "
            f"dept={self.department_id} spend={self.current_spend_microcents}/{self.budget_limit_microcents}>"
        )
