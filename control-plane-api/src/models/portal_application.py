"""Portal Application model (CAB-1306)."""

import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from ..database import Base


class PortalAppStatus(enum.StrEnum):
    """Status of a portal application."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


class SecurityProfile(enum.StrEnum):
    """Security profile for a portal application (CAB-1744).

    Curated auth combinations — each profile maps to specific
    Keycloak client config and gateway auth chain enforcement.
    """

    API_KEY = "api_key"
    OAUTH2_PUBLIC = "oauth2_public"
    OAUTH2_CONFIDENTIAL = "oauth2_confidential"
    FAPI_BASELINE = "fapi_baseline"
    FAPI_ADVANCED = "fapi_advanced"


class PortalApplication(Base):
    """Portal application — user-managed OAuth client with Keycloak backing."""

    __tablename__ = "portal_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=True, index=True)
    keycloak_client_id = Column(String(255), nullable=True)
    keycloak_client_uuid = Column(String(255), nullable=True)
    status = Column(
        SQLEnum(
            PortalAppStatus,
            values_callable=lambda x: [e.value for e in x],
            name="portal_app_status_enum",
        ),
        nullable=False,
        default=PortalAppStatus.ACTIVE,
    )
    security_profile = Column(
        SQLEnum(
            SecurityProfile,
            values_callable=lambda x: [e.value for e in x],
            name="security_profile_enum",
        ),
        nullable=False,
        default=SecurityProfile.OAUTH2_PUBLIC,
        server_default="oauth2_public",
    )
    redirect_uris = Column(JSONB, nullable=False, default=list)
    api_key_hash = Column(String(64), nullable=True)
    api_key_prefix = Column(String(12), nullable=True)
    jwks_uri = Column(String(2048), nullable=True)
    jwks_data = Column(JSONB, nullable=True)  # Inline JWKS (from PEM upload or JWK JSON)
    environment = Column(String(50), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_portal_apps_owner_name", "owner_id", "name", unique=True),
        Index("ix_portal_apps_owner_status", "owner_id", "status"),
    )
