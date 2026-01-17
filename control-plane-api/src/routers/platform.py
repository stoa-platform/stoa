"""Platform Status API Router - GitOps Observability (CAB-654)

Provides endpoints for monitoring platform component status via Argo CD.
Enables the Console to display real-time sync status and health.
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..auth.dependencies import get_current_user, User
from ..auth.rbac import require_role
from ..services.argocd_service import argocd_service
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/platform", tags=["Platform"])


# ============================================================================
# Response Models
# ============================================================================

class ComponentStatus(BaseModel):
    """Status of a single platform component."""
    name: str
    display_name: str
    sync_status: str  # Synced, OutOfSync, Unknown
    health_status: str  # Healthy, Progressing, Degraded, Suspended, Missing, Unknown
    revision: str  # Short git commit hash
    last_sync: Optional[str] = None
    message: Optional[str] = None


class GitOpsStatus(BaseModel):
    """Overall GitOps sync status."""
    status: str  # healthy, degraded, syncing
    components: List[ComponentStatus]
    checked_at: str


class PlatformEvent(BaseModel):
    """Platform deployment event."""
    id: Optional[int] = None
    component: str
    event_type: str  # sync, deploy, rollback
    status: str  # success, failed, in_progress
    revision: str
    message: Optional[str] = None
    timestamp: str
    actor: Optional[str] = None


class ExternalLinks(BaseModel):
    """External tool URLs for quick access."""
    argocd: str
    grafana: str
    prometheus: str
    logs: str


class DiffResource(BaseModel):
    """Resource diff for OutOfSync applications."""
    name: str
    namespace: Optional[str] = None
    kind: str
    group: Optional[str] = None
    status: str
    health: Optional[str] = None
    diff: Optional[str] = None


class ApplicationDiffResponse(BaseModel):
    """Diff response for an application."""
    application: str
    total_resources: int
    diff_count: int
    resources: List[DiffResource]


class PlatformStatusResponse(BaseModel):
    """Complete platform status response."""
    gitops: GitOpsStatus
    events: List[PlatformEvent]
    external_links: ExternalLinks
    timestamp: str


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/status", response_model=PlatformStatusResponse)
async def get_platform_status(
    user: User = Depends(get_current_user),
):
    """
    Get current platform status including GitOps sync state and recent events.

    Returns:
        - GitOps sync status for all platform components
        - Recent deployment events

    Required Role: Any authenticated user (cpi-admin sees all details)
    """
    try:
        # Check if ArgoCD is connected
        if not argocd_service._client:
            try:
                await argocd_service.connect()
            except Exception as e:
                logger.warning(f"ArgoCD not available: {e}")
                # Return mock status when ArgoCD is not available
                return _get_mock_status()

        # Get platform status from ArgoCD
        status_data = await argocd_service.get_platform_status()

        # Get recent events for the first few apps
        events = []
        for component in status_data.get("components", [])[:3]:
            try:
                app_events = await argocd_service.get_application_events(
                    component["name"], limit=5
                )
                for event in app_events[:2]:  # Max 2 events per component
                    events.append(PlatformEvent(
                        id=event.get("id"),
                        component=component["name"],
                        event_type="sync",
                        status="success" if component["sync_status"] == "Synced" else "in_progress",
                        revision=event.get("revision", ""),
                        message=None,
                        timestamp=event.get("deployed_at", datetime.utcnow().isoformat() + "Z"),
                        actor=None,
                    ))
            except Exception as e:
                logger.debug(f"Could not get events for {component['name']}: {e}")

        # Sort events by timestamp (most recent first)
        events.sort(key=lambda x: x.timestamp, reverse=True)

        return PlatformStatusResponse(
            gitops=GitOpsStatus(
                status=status_data["status"],
                components=[
                    ComponentStatus(**comp) for comp in status_data["components"]
                ],
                checked_at=status_data["checked_at"],
            ),
            events=events[:10],  # Limit to 10 most recent events
            external_links=ExternalLinks(
                argocd=settings.ARGOCD_URL,
                grafana=settings.GRAFANA_URL,
                prometheus=settings.PROMETHEUS_URL,
                logs=settings.LOGS_URL,
            ),
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

    except Exception as e:
        logger.error(f"Failed to get platform status: {e}")
        # Return degraded status on error
        return _get_mock_status(error=str(e))


@router.get("/components", response_model=List[ComponentStatus])
async def list_platform_components(
    user: User = Depends(get_current_user),
):
    """
    List all platform components and their status.

    Returns a list of all monitored Argo CD applications.
    """
    try:
        if not argocd_service._client:
            await argocd_service.connect()

        status_data = await argocd_service.get_platform_status()
        return [ComponentStatus(**comp) for comp in status_data["components"]]

    except Exception as e:
        logger.error(f"Failed to list components: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list components: {str(e)}")


@router.get("/components/{name}", response_model=ComponentStatus)
async def get_component_status(
    name: str,
    user: User = Depends(get_current_user),
):
    """
    Get detailed status for a specific platform component.

    Args:
        name: Component/application name
    """
    try:
        if not argocd_service._client:
            await argocd_service.connect()

        status = await argocd_service.get_application_sync_status(name)

        return ComponentStatus(
            name=status["name"],
            display_name=status["name"],
            sync_status=status["sync_status"],
            health_status=status["health_status"],
            revision=status["revision"][:8] if status["revision"] else "",
            last_sync=status.get("operation_state", {}).get("finishedAt"),
            message=None,
        )

    except Exception as e:
        logger.error(f"Failed to get component {name}: {e}")
        raise HTTPException(status_code=404, detail=f"Component {name} not found")


@router.post("/components/{name}/sync")
async def sync_component(
    name: str,
    user: User = Depends(require_role(["cpi-admin", "devops"])),
):
    """
    Trigger a sync for a platform component.

    Requires cpi-admin or devops role.

    Args:
        name: Component/application name
    """
    try:
        if not argocd_service._client:
            await argocd_service.connect()

        result = await argocd_service.sync_application(name)

        return {
            "message": f"Sync triggered for {name}",
            "operation": result.get("status", {}).get("operationState", {}).get("phase"),
        }

    except Exception as e:
        logger.error(f"Failed to sync component {name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to sync: {str(e)}")


@router.get("/events", response_model=List[PlatformEvent])
async def list_platform_events(
    user: User = Depends(get_current_user),
    component: Optional[str] = Query(None, description="Filter by component name"),
    limit: int = Query(20, ge=1, le=100, description="Maximum events to return"),
):
    """
    List recent platform events.

    Args:
        component: Optional filter by component name
        limit: Maximum number of events to return
    """
    try:
        if not argocd_service._client:
            await argocd_service.connect()

        events = []
        app_names = [component] if component else settings.argocd_platform_apps_list

        for app_name in app_names:
            try:
                app_events = await argocd_service.get_application_events(app_name, limit=limit)
                for event in app_events:
                    events.append(PlatformEvent(
                        id=event.get("id"),
                        component=app_name,
                        event_type="sync",
                        status="success",
                        revision=event.get("revision", ""),
                        message=None,
                        timestamp=event.get("deployed_at", datetime.utcnow().isoformat() + "Z"),
                        actor=None,
                    ))
            except Exception as e:
                logger.debug(f"Could not get events for {app_name}: {e}")

        # Sort by timestamp and limit
        events.sort(key=lambda x: x.timestamp, reverse=True)
        return events[:limit]

    except Exception as e:
        logger.error(f"Failed to list events: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list events: {str(e)}")


@router.get("/components/{name}/diff", response_model=ApplicationDiffResponse)
async def get_component_diff(
    name: str,
    user: User = Depends(get_current_user),
):
    """
    Get diff for an OutOfSync component.

    Returns the differences between the desired state (Git) and
    the live state (Kubernetes cluster).

    Args:
        name: Component/application name
    """
    try:
        if not argocd_service._client:
            await argocd_service.connect()

        diff_result = await argocd_service.get_application_diff(name)

        resources = []
        for resource in diff_result.get("resources", []):
            resources.append(DiffResource(
                name=resource.get("name", ""),
                namespace=resource.get("namespace"),
                kind=resource.get("kind", ""),
                group=resource.get("group"),
                status=resource.get("status", ""),
                health=resource.get("health"),
                diff=resource.get("diff"),
            ))

        return ApplicationDiffResponse(
            application=name,
            total_resources=diff_result.get("total_resources", 0),
            diff_count=diff_result.get("diff_count", 0),
            resources=resources,
        )

    except Exception as e:
        logger.error(f"Failed to get diff for {name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get diff: {str(e)}")


# ============================================================================
# Helper Functions
# ============================================================================

def _get_mock_status(error: Optional[str] = None) -> PlatformStatusResponse:
    """
    Return mock status when ArgoCD is not available.

    Used for development/testing or when ArgoCD connection fails.
    """
    now = datetime.utcnow().isoformat() + "Z"

    # Default components for mock status
    components = [
        ComponentStatus(
            name="stoa-control-plane",
            display_name="Control Plane API",
            sync_status="Unknown" if error else "Synced",
            health_status="Unknown" if error else "Healthy",
            revision="HEAD",
            last_sync=now,
            message=error if error else None,
        ),
        ComponentStatus(
            name="stoa-console",
            display_name="Console UI",
            sync_status="Unknown" if error else "Synced",
            health_status="Unknown" if error else "Healthy",
            revision="HEAD",
            last_sync=now,
            message=None,
        ),
        ComponentStatus(
            name="stoa-portal",
            display_name="Developer Portal",
            sync_status="Unknown" if error else "Synced",
            health_status="Unknown" if error else "Healthy",
            revision="HEAD",
            last_sync=now,
            message=None,
        ),
        ComponentStatus(
            name="stoa-mcp-gateway",
            display_name="MCP Gateway",
            sync_status="Unknown" if error else "Synced",
            health_status="Unknown" if error else "Healthy",
            revision="HEAD",
            last_sync=now,
            message=None,
        ),
    ]

    return PlatformStatusResponse(
        gitops=GitOpsStatus(
            status="unknown" if error else "healthy",
            components=components,
            checked_at=now,
        ),
        events=[],
        external_links=ExternalLinks(
            argocd=settings.ARGOCD_URL,
            grafana=settings.GRAFANA_URL,
            prometheus=settings.PROMETHEUS_URL,
            logs=settings.LOGS_URL,
        ),
        timestamp=now,
    )
