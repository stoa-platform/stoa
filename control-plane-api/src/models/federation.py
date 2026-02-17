"""Federation models for enterprise MCP multi-account orchestration (CAB-1313/CAB-1361)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.database import Base


class MasterAccountStatus(enum.StrEnum):
    """Master account lifecycle status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DISABLED = "disabled"


class SubAccountType(enum.StrEnum):
    """Sub-account type — developer (human) or agent (AI)."""

    DEVELOPER = "developer"
    AGENT = "agent"


class SubAccountStatus(enum.StrEnum):
    """Sub-account lifecycle status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class MasterAccount(Base):
    """Enterprise federation master account.

    A master account aggregates N developer/agent sub-accounts with
    delegated auth and tool allow-lists. One master per tenant name.
    """

    __tablename__ = "master_accounts"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant ownership
    tenant_id = Column(String(255), nullable=False, index=True)

    # Identity
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    # Status
    status = Column(
        SQLEnum(
            MasterAccountStatus,
            values_callable=lambda x: [e.value for e in x],
            name="master_account_status_enum",
        ),
        nullable=False,
        default=MasterAccountStatus.ACTIVE,
    )

    # Quotas
    max_sub_accounts = Column(Integer, nullable=False, default=10)
    quota_config = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Audit
    created_by = Column(String(255), nullable=True)

    # Relationships
    sub_accounts = relationship("SubAccount", back_populates="master_account", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_master_accounts_tenant_name", "tenant_id", "name", unique=True),
        Index("ix_master_accounts_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<MasterAccount {self.id} name={self.name} tenant={self.tenant_id}>"


class SubAccount(Base):
    """Federation sub-account — developer or AI agent with delegated access.

    Each sub-account has an API key (SHA-256 hashed) and optionally a
    Keycloak client for Token Exchange. The plaintext key is returned
    only once at creation.
    """

    __tablename__ = "sub_accounts"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Parent
    master_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("master_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tenant (denormalized for query performance)
    tenant_id = Column(String(255), nullable=False, index=True)

    # Identity
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    account_type = Column(
        SQLEnum(
            SubAccountType,
            values_callable=lambda x: [e.value for e in x],
            name="sub_account_type_enum",
        ),
        nullable=False,
        default=SubAccountType.DEVELOPER,
    )

    # Status
    status = Column(
        SQLEnum(
            SubAccountStatus,
            values_callable=lambda x: [e.value for e in x],
            name="sub_account_status_enum",
        ),
        nullable=False,
        default=SubAccountStatus.ACTIVE,
    )

    # API key (hashed)
    api_key_hash = Column(String(512), nullable=True)
    api_key_prefix = Column(String(20), nullable=True)

    # Keycloak integration
    kc_client_id = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Audit
    created_by = Column(String(255), nullable=True)

    # Relationships
    master_account = relationship("MasterAccount", back_populates="sub_accounts")
    allowed_tools = relationship("SubAccountTool", back_populates="sub_account", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_sub_accounts_master_name", "master_account_id", "name", unique=True),
        Index("ix_sub_accounts_tenant_status", "tenant_id", "status"),
        Index("ix_sub_accounts_key_prefix", "api_key_prefix"),
    )

    def __repr__(self) -> str:
        return f"<SubAccount {self.id} name={self.name} type={self.account_type}>"


class SubAccountTool(Base):
    """Tool allow-list entry for a sub-account.

    Junction table linking sub-accounts to the tools they can access.
    Phase 1 creates the table; Phase 2 (gateway routing) uses it.
    """

    __tablename__ = "sub_account_tools"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Parent
    sub_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sub_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Tool reference
    tool_name = Column(String(255), nullable=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    sub_account = relationship("SubAccount", back_populates="allowed_tools")

    # Indexes
    __table_args__ = (Index("ix_sub_account_tools_unique", "sub_account_id", "tool_name", unique=True),)

    def __repr__(self) -> str:
        return f"<SubAccountTool {self.id} sub_account={self.sub_account_id} tool={self.tool_name}>"
