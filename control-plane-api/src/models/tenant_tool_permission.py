"""Tenant-level tool permission model for fine-grained access control (CAB-1980).

Allows tenant admins to allow/deny specific MCP tools per tenant.
Checked at tool invocation time (/v1/mcp/tools/call) before execution.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class TenantToolPermission(Base):
    """Per-tenant, per-tool permission override.

    When a row exists with allowed=False, the tool is denied for that tenant.
    Absence of a row means the tool is allowed (default-allow).
    """

    __tablename__ = "tenant_tool_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    mcp_server_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Audit fields
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        Index(
            "uq_tenant_server_tool",
            "tenant_id",
            "mcp_server_id",
            "tool_name",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TenantToolPermission tenant={self.tenant_id} "
            f"tool={self.tool_name} allowed={self.allowed}>"
        )
