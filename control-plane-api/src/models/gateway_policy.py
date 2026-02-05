"""Gateway Policy SQLAlchemy models for gateway-agnostic policy management.

Policies are reusable definitions (e.g., CORS, rate limiting, JWT validation)
that can be bound to specific API+gateway combinations, entire gateways,
or all APIs for a tenant via GatewayPolicyBinding.
"""
import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.database import Base


class PolicyType(enum.StrEnum):
    """Supported gateway policy types."""
    CORS = "cors"
    RATE_LIMIT = "rate_limit"
    JWT_VALIDATION = "jwt_validation"
    IP_FILTER = "ip_filter"
    LOGGING = "logging"
    CACHING = "caching"
    TRANSFORM = "transform"


class PolicyScope(enum.StrEnum):
    """Scope of policy application."""
    API = "api"           # Specific API + gateway combo
    GATEWAY = "gateway"   # All APIs on a gateway
    TENANT = "tenant"     # All APIs for a tenant


class GatewayPolicy(Base):
    """Reusable policy definition with type-specific configuration.

    Policies are bound to targets (API, gateway, tenant) via GatewayPolicyBinding.
    The sync engine applies bound policies after successful API sync.
    """
    __tablename__ = "gateway_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    policy_type = Column(
        SQLEnum(
            PolicyType,
            name="policy_type_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    tenant_id = Column(String(255), nullable=True, index=True)
    scope = Column(
        SQLEnum(
            PolicyScope,
            name="policy_scope_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=PolicyScope.API,
        server_default="api",
    )
    config = Column(JSONB, nullable=False, default=dict)
    priority = Column(Integer, nullable=False, default=100, server_default="100")
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    bindings = relationship(
        "GatewayPolicyBinding",
        back_populates="policy",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint('name', 'tenant_id', name='uq_policy_name_tenant'),
    )

    def __repr__(self) -> str:
        return f"<GatewayPolicy {self.name} type={self.policy_type} scope={self.scope}>"


class GatewayPolicyBinding(Base):
    """Junction binding a policy to an API+gateway, gateway, or tenant.

    Nullable foreign keys determine scope:
    - api_catalog_id + gateway_instance_id: API-level binding
    - gateway_instance_id only: Gateway-level binding
    - tenant_id only: Tenant-level binding
    """
    __tablename__ = "gateway_policy_bindings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    policy_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_policies.id", ondelete="CASCADE"),
        nullable=False,
    )
    api_catalog_id = Column(
        UUID(as_uuid=True),
        ForeignKey("api_catalog.id", ondelete="CASCADE"),
        nullable=True,
    )
    gateway_instance_id = Column(
        UUID(as_uuid=True),
        ForeignKey("gateway_instances.id", ondelete="CASCADE"),
        nullable=True,
    )
    tenant_id = Column(String(255), nullable=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    policy = relationship("GatewayPolicy", back_populates="bindings")

    __table_args__ = (
        UniqueConstraint(
            'policy_id', 'api_catalog_id', 'gateway_instance_id',
            name='uq_policy_binding',
        ),
        Index('ix_policy_binding_policy', 'policy_id'),
        Index('ix_policy_binding_api', 'api_catalog_id'),
        Index('ix_policy_binding_gateway', 'gateway_instance_id'),
    )

    def __repr__(self) -> str:
        return (
            f"<GatewayPolicyBinding policy={self.policy_id} "
            f"api={self.api_catalog_id} gw={self.gateway_instance_id}>"
        )
