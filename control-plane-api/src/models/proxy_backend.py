"""ProxyBackend model — internal API backends proxied through STOA Gateway (CAB-1725)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum as SQLEnum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from src.database import Base


class ProxyBackendAuthType(enum.StrEnum):
    """Authentication type for the upstream backend."""

    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2_CC = "oauth2_cc"


class ProxyBackendStatus(enum.StrEnum):
    """Backend lifecycle status."""

    ACTIVE = "active"
    DISABLED = "disabled"


class ProxyBackend(Base):
    """Internal API backend registered for proxying through STOA Gateway.

    Used for STOA's own dogfooding: n8n, Linear, GitHub, Slack, Infisical, etc.
    The gateway injects credentials so consumers never see backend API keys.
    """

    __tablename__ = "proxy_backends"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    name = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    # Backend connection
    base_url = Column(String(2048), nullable=False)
    health_endpoint = Column(String(512), nullable=True)

    # Authentication config (type + credential reference in gateway CredentialStore)
    auth_type = Column(
        SQLEnum(
            ProxyBackendAuthType,
            values_callable=lambda x: [e.value for e in x],
            name="proxy_backend_auth_type_enum",
        ),
        nullable=False,
        default=ProxyBackendAuthType.API_KEY,
    )
    credential_ref = Column(String(255), nullable=True)

    # Rate limiting
    rate_limit_rpm = Column(Integer, nullable=False, default=0)

    # Resilience
    circuit_breaker_enabled = Column(Boolean, nullable=False, default=True)
    fallback_direct = Column(Boolean, nullable=False, default=False)
    timeout_secs = Column(Integer, nullable=False, default=30)

    # Status
    status = Column(
        SQLEnum(
            ProxyBackendStatus,
            values_callable=lambda x: [e.value for e in x],
            name="proxy_backend_status_enum",
        ),
        nullable=False,
        default=ProxyBackendStatus.ACTIVE,
    )
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("ix_proxy_backends_status", "status"),
        Index("ix_proxy_backends_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<ProxyBackend {self.name} url={self.base_url} status={self.status}>"
