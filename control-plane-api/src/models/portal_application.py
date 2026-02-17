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
    redirect_uris = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_portal_apps_owner_name", "owner_id", "name", unique=True),
        Index("ix_portal_apps_owner_status", "owner_id", "status"),
    )
