"""ChatTokenUsage model — daily aggregated token metering (CAB-288)."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import BigInteger, Date, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ChatTokenUsage(Base):
    """Daily token usage per tenant/user/model."""

    __tablename__ = "chat_token_usage"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "model",
            "period_date",
            name="uq_chat_token_usage_tenant_user_model_date",
        ),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    period_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    input_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
