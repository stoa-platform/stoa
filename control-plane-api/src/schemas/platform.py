"""Pydantic schemas for Platform Status endpoints (CAB-654).

Provides models for GitOps observability and platform health status.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


# ============== Enums ==============

class ComponentHealthEnum(str, Enum):
    """Component health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class GitOpsSyncStatusEnum(str, Enum):
    """ArgoCD sync status."""
    SYNCED = "Synced"
    OUT_OF_SYNC = "OutOfSync"
    UNKNOWN = "Unknown"
    NOT_FOUND = "NotFound"
    ERROR = "Error"


class GitOpsHealthStatusEnum(str, Enum):
    """ArgoCD health status."""
    HEALTHY = "Healthy"
    DEGRADED = "Degraded"
    PROGRESSING = "Progressing"
    SUSPENDED = "Suspended"
    MISSING = "Missing"
    UNKNOWN = "Unknown"


class PlatformEventTypeEnum(str, Enum):
    """Platform event types."""
    SYNC_STARTED = "sync_started"
    SYNC_COMPLETED = "sync_completed"
    SYNC_FAILED = "sync_failed"
    DRIFT_DETECTED = "drift_detected"
    HEALTH_CHANGED = "health_changed"


class PlatformEventSeverityEnum(str, Enum):
    """Platform event severity."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


# ============== Component Status ==============

class ComponentStatus(BaseModel):
    """Health status for a platform component."""
    name: str = Field(..., description="Component name")
    status: ComponentHealthEnum = Field(..., description="Health status")
    message: Optional[str] = Field(None, description="Status message or details")
    last_check: datetime = Field(..., description="Last health check timestamp")
    external_url: Optional[str] = Field(None, description="Link to external dashboard/UI")

    model_config = ConfigDict(from_attributes=True)


# ============== GitOps Status ==============

class GitOpsAppStatus(BaseModel):
    """Status of a single ArgoCD application."""
    name: str = Field(..., description="Application name")
    display_name: Optional[str] = Field(None, description="Human-readable display name")
    sync_status: str = Field(..., description="Sync status (Synced, OutOfSync, Unknown)")
    health_status: str = Field(..., description="Health status (Healthy, Degraded, etc.)")
    revision: Optional[str] = Field(None, description="Current Git revision (short)")
    last_sync: Optional[datetime] = Field(None, description="Last sync timestamp")
    message: Optional[str] = Field(None, description="Status message")
    namespace: Optional[str] = Field(None, description="Target namespace")
    project: Optional[str] = Field(None, description="ArgoCD project")

    model_config = ConfigDict(from_attributes=True)


class GitOpsSummary(BaseModel):
    """Aggregated GitOps sync summary."""
    total_apps: int = Field(..., description="Total number of applications")
    synced_count: int = Field(..., description="Number of synced applications")
    out_of_sync_count: int = Field(..., description="Number of out-of-sync applications")
    healthy_count: int = Field(..., description="Number of healthy applications")
    degraded_count: int = Field(..., description="Number of degraded applications")
    apps: List[GitOpsAppStatus] = Field(default_factory=list, description="Application status list")
    argocd_url: str = Field(..., description="ArgoCD URL for external links")

    model_config = ConfigDict(from_attributes=True)


# ============== Platform Events ==============

class PlatformEvent(BaseModel):
    """Platform event for recent activity timeline."""
    timestamp: datetime = Field(..., description="Event timestamp")
    type: str = Field(..., description="Event type")
    severity: str = Field(..., description="Event severity (info, warning, error)")
    application: str = Field(..., description="Related application name")
    message: str = Field(..., description="Event message")
    details: Optional[Dict] = Field(None, description="Additional event details")

    model_config = ConfigDict(from_attributes=True)


# ============== External Links ==============

class ExternalLink(BaseModel):
    """External tool link."""
    name: str = Field(..., description="Link name")
    url: str = Field(..., description="Link URL")
    icon: Optional[str] = Field(None, description="Icon name (lucide icon)")
    description: Optional[str] = Field(None, description="Link description")


# ============== Main Response Models ==============

class PlatformStatusResponse(BaseModel):
    """Complete platform status response."""
    components: List[ComponentStatus] = Field(..., description="Component health status")
    gitops: GitOpsSummary = Field(..., description="GitOps sync summary")
    recent_events: List[PlatformEvent] = Field(default_factory=list, description="Recent platform events")
    external_links: Dict[str, str] = Field(..., description="External tool URLs")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")

    model_config = ConfigDict(from_attributes=True)


class GitOpsSyncRequest(BaseModel):
    """Request to trigger GitOps sync."""
    prune: bool = Field(False, description="Prune resources no longer in Git")
    revision: Optional[str] = Field(None, description="Specific revision to sync to")


class GitOpsSyncResponse(BaseModel):
    """Response from triggering GitOps sync."""
    status: str = Field(..., description="Sync status (triggered, failed)")
    application: str = Field(..., description="Application name")
    message: Optional[str] = Field(None, description="Status message")
    operation: Optional[Dict] = Field(None, description="Operation details")


class GitOpsDiffResource(BaseModel):
    """Resource diff for an OutOfSync application."""
    name: str = Field(..., description="Resource name")
    namespace: Optional[str] = Field(None, description="Resource namespace")
    kind: str = Field(..., description="Resource kind (Deployment, Service, etc.)")
    group: Optional[str] = Field(None, description="API group")
    status: str = Field(..., description="Resource status")
    health: Optional[str] = Field(None, description="Resource health status")
    diff: Optional[str] = Field(None, description="Diff content")


class GitOpsDiffResponse(BaseModel):
    """Diff response for an application."""
    application: str = Field(..., description="Application name")
    total_resources: int = Field(..., description="Total managed resources")
    diff_count: int = Field(..., description="Number of resources with differences")
    resources: List[GitOpsDiffResource] = Field(default_factory=list, description="Resources with diffs")
