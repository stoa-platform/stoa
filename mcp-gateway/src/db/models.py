"""CAB-660: SQLAlchemy ORM Models for Tool Handlers.

Database models for the STOA platform MCP Gateway.
Ready Player One themed demo data support.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    String,
    Text,
    Integer,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    CheckConstraint,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, INET
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class Tenant(Base):
    """Multi-tenant organizations using the STOA platform."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        server_default="active",
    )
    settings: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="tenant")
    owned_apis: Mapped[list["API"]] = relationship("API", back_populates="owner_tenant")
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="tenant"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'archived')",
            name="ck_tenants_status",
        ),
    )


class User(Base):
    """Users reference to Keycloak."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    keycloak_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(255))
    name: Mapped[str | None] = mapped_column(String(255))
    tenant_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE")
    )
    roles: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        server_default="{}",
    )
    avatar: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="user"
    )

    __table_args__ = (
        Index("idx_users_tenant", "tenant_id"),
        Index("idx_users_keycloak", "keycloak_id"),
    )


class API(Base):
    """API Catalog."""

    __tablename__ = "apis"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        server_default="active",
    )
    version: Mapped[str | None] = mapped_column(String(32))
    owner_tenant_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("tenants.id")
    )
    access_type: Mapped[str] = mapped_column(
        String(32),
        default="public",
        server_default="public",
    )
    allowed_tenants: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        server_default="{}",
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        server_default="{}",
    )
    spec: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rate_limit: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    owner_tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="owned_apis")
    endpoints: Mapped[list["APIEndpoint"]] = relationship(
        "APIEndpoint", back_populates="api", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["Subscription"]] = relationship(
        "Subscription", back_populates="api"
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'deprecated', 'draft')",
            name="ck_apis_status",
        ),
        CheckConstraint(
            "access_type IN ('public', 'tenant', 'restricted')",
            name="ck_apis_access_type",
        ),
        Index("idx_apis_category", "category"),
        Index("idx_apis_status", "status"),
        Index("idx_apis_owner", "owner_tenant_id"),
    )


class APIEndpoint(Base):
    """API Endpoints (denormalized for quick lookup)."""

    __tablename__ = "api_endpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("apis.id", ondelete="CASCADE"), nullable=False
    )
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Relationships
    api: Mapped["API"] = relationship("API", back_populates="endpoints")

    __table_args__ = (
        UniqueConstraint("api_id", "method", "path", name="uq_endpoints_api_method_path"),
        Index("idx_endpoints_api", "api_id"),
    )


class Subscription(Base):
    """API Subscriptions."""

    __tablename__ = "mcp_subscriptions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.id")
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("tenants.id")
    )
    api_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("apis.id")
    )
    plan: Mapped[str] = mapped_column(
        String(64),
        default="free",
        server_default="free",
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        server_default="active",
    )
    api_key_hash: Mapped[str | None] = mapped_column(String(255))
    denial_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="subscriptions")
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="subscriptions")
    api: Mapped["API"] = relationship("API", back_populates="subscriptions")

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'suspended', 'cancelled', 'denied', 'pending')",
            name="ck_subscriptions_status",
        ),
        Index("idx_subs_tenant", "tenant_id"),
        Index("idx_subs_api", "api_id"),
        Index("idx_subs_user", "user_id"),
        Index("idx_subs_status", "status"),
    )


class AuditLog(Base):
    """Audit Logs."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    user_id: Mapped[str | None] = mapped_column(String(64))
    tenant_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(32))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp", postgresql_ops={"timestamp": "DESC"}),
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_tenant", "tenant_id"),
        Index("idx_audit_action", "action"),
    )


class UACContract(Base):
    """UAC Contracts (Usage and Access Control)."""

    __tablename__ = "uac_contracts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(32),
        default="active",
        server_default="active",
    )
    terms: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tenant_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        server_default="{}",
    )
    api_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        server_default="{}",
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'expired', 'pending', 'draft')",
            name="ck_uac_contracts_status",
        ),
    )
