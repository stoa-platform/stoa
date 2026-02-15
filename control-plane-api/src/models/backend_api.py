"""Backend API model for SaaS self-service MCP exposure (CAB-1188/CAB-1249)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.database import Base


class BackendApiAuthType(enum.StrEnum):
    """Authentication type for the backend API."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2_CC = "oauth2_cc"


class BackendApiStatus(enum.StrEnum):
    """Backend API lifecycle status."""

    DRAFT = "draft"
    ACTIVE = "active"
    DISABLED = "disabled"


class BackendApi(Base):
    """Backend API registered by a tenant for MCP exposure.

    Represents a backend API that a tenant registers in the Console to expose
    as MCP tools via the STOA Gateway. The tenant provides the OpenAPI spec
    (URL or inline), backend credentials, and approval settings.

    Flow: Register → Fetch OpenAPI → Generate MCP tools → Expose via Gateway
    """

    __tablename__ = "backend_apis"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Tenant ownership
    tenant_id = Column(String(255), nullable=False, index=True)

    # Identity
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    # Backend connection
    backend_url = Column(String(2048), nullable=False)

    # OpenAPI spec
    openapi_spec_url = Column(String(2048), nullable=True)
    openapi_spec = Column(JSONB, nullable=True)
    spec_hash = Column(String(64), nullable=True)

    # Authentication for the backend (encrypted at-rest via Fernet)
    auth_type = Column(
        SQLEnum(
            BackendApiAuthType,
            values_callable=lambda x: [e.value for e in x],
            name="backend_api_auth_type_enum",
        ),
        nullable=False,
        default=BackendApiAuthType.NONE,
    )
    auth_config_encrypted = Column(Text, nullable=True)

    # MCP tool generation
    tool_count = Column(Integer, nullable=False, default=0)
    last_synced_at = Column(DateTime, nullable=True)

    # Status
    status = Column(
        SQLEnum(
            BackendApiStatus,
            values_callable=lambda x: [e.value for e in x],
            name="backend_api_status_enum",
        ),
        nullable=False,
        default=BackendApiStatus.DRAFT,
    )

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Audit
    created_by = Column(String(255), nullable=True)

    # Indexes
    __table_args__ = (
        Index("ix_backend_apis_tenant_name", "tenant_id", "name", unique=True),
        Index("ix_backend_apis_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<BackendApi {self.id} name={self.name} tenant={self.tenant_id}>"
