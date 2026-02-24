"""DepartmentBudget model — per-department monthly budget + alert config (CAB-1457).

Stores the monthly budget ceiling, webhook URL for alerts (Fernet-encrypted),
and the thresholds at which alerts fire. alerts_fired_this_month tracks
which thresholds have already been notified to prevent double-firing.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

# Default alert thresholds: 50% informational (off), 80% warning (on), 100% critical (on)
_DEFAULT_THRESHOLDS: dict = {"50": False, "80": True, "100": True}


class DepartmentBudget(Base):
    """Monthly budget and alert configuration per department."""

    __tablename__ = "department_budgets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    department_id: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_budget_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    alert_webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    alert_thresholds: Mapped[dict] = mapped_column(JSON, default=lambda: _DEFAULT_THRESHOLDS.copy())
    alerts_fired_this_month: Mapped[dict] = mapped_column(JSON, default=dict)
    period_month: Mapped[str | None] = mapped_column(String(7), nullable=True)  # "YYYY-MM"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (UniqueConstraint("tenant_id", "department_id", name="uq_department_budgets_tenant_dept"),)

    def __repr__(self) -> str:
        return f"<DepartmentBudget {self.department_id} ${self.monthly_budget_usd}/mo>"
