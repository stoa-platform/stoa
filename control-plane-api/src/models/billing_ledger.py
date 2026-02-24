"""BillingLedger model — department-level tool usage metering (CAB-1457).

Stores aggregated tool call counts, token usage, and cost per department
per tool per month. Cost is in micro-cents (1 USD = 100_000_000 micro-cents)
to avoid floating-point drift.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class BillingLedger(Base):
    """Monthly tool usage and cost per department."""

    __tablename__ = "billing_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    department_id: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    period_month: Mapped[str] = mapped_column(String(7), nullable=False)  # "YYYY-MM"
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_microcents: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        UniqueConstraint(
            "department_id",
            "tool_name",
            "period_month",
            name="uq_billing_ledger_dept_tool_month",
        ),
        Index("ix_billing_ledger_dept_month", "department_id", "period_month"),
    )

    def __repr__(self) -> str:
        return f"<BillingLedger {self.department_id}/{self.tool_name} {self.period_month}>"
