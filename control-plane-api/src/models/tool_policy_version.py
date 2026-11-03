"""Database-managed tool policy versions; mutations advance the tenant counter."""

from sqlalchemy import BigInteger, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class ToolPolicyVersion(Base):
    """Monotonic counter retained after the last permission is removed.

    A missing row represents baseline version 1. Permission mutations create
    version 2 or atomically increment the existing row through a DB trigger.
    Apply the Alembic migration to install the mutation and monotonicity guards.
    """

    __tablename__ = "tool_policy_versions"
    __table_args__ = (CheckConstraint("version >= 1", name="ck_tool_policy_version_positive"),)

    tenant_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="1")
