"""Catalog SQLAlchemy models for API and MCP tools caching (CAB-682)"""
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import enum

from src.database import Base


class SyncType(str, enum.Enum):
    """Sync operation type"""
    FULL = "full"
    TENANT = "tenant"
    API = "api"


class SyncStatus(str, enum.Enum):
    """Sync operation status"""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class APICatalog(Base):
    """Cached API catalog entry from GitLab"""
    __tablename__ = "api_catalog"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    tenant_id = Column(String(100), nullable=False, index=True)
    api_id = Column(String(100), nullable=False)
    api_name = Column(String(255), nullable=True)
    version = Column(String(50), nullable=True)

    # Status and classification
    status = Column(String(50), default="active", nullable=False)
    category = Column(String(100), nullable=True, index=True)
    tags = Column(JSONB, default=list, nullable=False)

    # Portal visibility
    portal_published = Column(Boolean, default=False, nullable=False, index=True)

    # Content
    api_metadata = Column("metadata", JSONB, nullable=False)  # Full api.yaml content
    openapi_spec = Column(JSONB, nullable=True)  # OpenAPI spec if available

    # Git tracking
    git_path = Column(String(500), nullable=True)
    git_commit_sha = Column(String(40), nullable=True)

    # Sync tracking
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Soft delete

    # Composite unique constraint
    __table_args__ = (
        Index('ix_api_catalog_tenant_api', 'tenant_id', 'api_id', unique=True),
    )

    def __repr__(self) -> str:
        return f"<APICatalog {self.tenant_id}/{self.api_id}>"

    @property
    def is_active(self) -> bool:
        """Check if API is not soft-deleted"""
        return self.deleted_at is None


class MCPToolsCatalog(Base):
    """Cached MCP tools catalog entry from GitLab"""
    __tablename__ = "mcp_tools_catalog"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identity
    tenant_id = Column(String(100), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)
    display_name = Column(String(255), nullable=True)

    # Description
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)

    # Schemas
    input_schema = Column(JSONB, nullable=True)
    output_schema = Column(JSONB, nullable=True)

    # Additional metadata
    tool_metadata = Column("metadata", JSONB, default=dict, nullable=False)

    # Git tracking
    git_path = Column(String(500), nullable=True)
    git_commit_sha = Column(String(40), nullable=True)

    # Sync tracking
    synced_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # Soft delete

    # Composite unique constraint
    __table_args__ = (
        Index('ix_mcp_tools_tenant_tool', 'tenant_id', 'tool_name', unique=True),
    )

    def __repr__(self) -> str:
        return f"<MCPToolsCatalog {self.tenant_id}/{self.tool_name}>"

    @property
    def is_active(self) -> bool:
        """Check if tool is not soft-deleted"""
        return self.deleted_at is None


class CatalogSyncStatus(Base):
    """Tracking table for catalog sync operations"""
    __tablename__ = "catalog_sync_status"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Sync info
    sync_type = Column(String(50), nullable=False)  # 'full', 'tenant', 'api'
    status = Column(String(50), nullable=False)  # 'running', 'success', 'failed'

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Results
    items_synced = Column(Integer, default=0, nullable=False)
    errors = Column(JSONB, default=list, nullable=False)

    # Git tracking
    git_commit_sha = Column(String(40), nullable=True)

    def __repr__(self) -> str:
        return f"<CatalogSyncStatus {self.sync_type} {self.status}>"

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds"""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
