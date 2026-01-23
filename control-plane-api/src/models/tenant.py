"""Tenant SQLAlchemy model.

Model for multi-tenant management stored in the database.
"""
from sqlalchemy import Column, String, Text, DateTime, JSON
from sqlalchemy.sql import func
import enum

from src.database import Base


class TenantStatus(str, enum.Enum):
    """Tenant status enum."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class Tenant(Base):
    """Tenant model - represents an organization/tenant in the platform."""
    __tablename__ = "tenants"

    # Primary key - slug-style identifier (e.g., "oasis-gunters")
    id = Column(String(64), primary_key=True)

    # Display name (e.g., "OASIS Gunters")
    name = Column(String(255), nullable=False)

    # Optional description
    description = Column(Text, nullable=True)

    # Status: active, suspended, archived
    status = Column(String(32), default=TenantStatus.ACTIVE.value, nullable=False)

    # Tenant settings (JSON) - quotas, features, etc.
    settings = Column(JSON, default=dict, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Tenant(id='{self.id}', name='{self.name}', status='{self.status}')>"

    def to_dict(self) -> dict:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.name,  # Alias for compatibility
            "description": self.description or "",
            "status": self.status,
            "settings": self.settings or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
