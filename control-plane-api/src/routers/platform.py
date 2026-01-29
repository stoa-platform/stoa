"""Platform Status API Router - GitOps Observability (CAB-654)

Provides endpoints for monitoring platform component status via Argo CD.
Enables the Console to display real-time sync status and health.

Uses OIDC authentication - forwards user's Keycloak token to ArgoCD.
"""
import asyncio
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from ..auth.dependencies import get_current_user, User
from ..auth.rbac import require_role
from ..services.argocd_service import argocd_service
from ..services.cache_service import TTLCache
from ..config import settings

# CAB-687: In-memory cache for platform status (Council obligation #3 - 30s TTL)
_platform_status_cache = TTLCache(default_ttl_seconds=30, max_size=10)

security = HTTPBearer()

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
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Get current platform status including GitOps sync state and recent events.

    Returns:
        - GitOps sync status for all platform components
        - Recent deployment events

    Required Role: Any authenticated user (cpi-admin sees all details)
    """
    auth_token = credentials.credentials

    try:
        # Check if ArgoCD service is configured
        if not argocd_service.is_connected:
            logger.warning("ArgoCD service not configured")
            return _get_mock_status()

        # CAB-687: Check in-memory cache first (Council obligation #3)
        cached = await _platform_status_cache.get("platform:status")
        if cached is not None:
            return cached

        # CAB-687: Run health check and platform status in parallel
        # include_events=True avoids redundant API calls for events
        health_result, status_data = await asyncio.gather(
            argocd_service.health_check(auth_token),
            argocd_service.get_platform_status(auth_token, include_events=True),
            return_exceptions=True,
        )

        # Handle health check failure
        if isinstance(health_result, Exception) or not health_result:
            logger.warning("ArgoCD health check failed")
            return _get_mock_status(error="ArgoCD not reachable")

        # Handle status fetch failure
        if isinstance(status_data, Exception):
            logger.error(f"Failed to get platform status: {status_data}")
            return _get_mock_status(error=str(status_data))

        # Build events from already-fetched app data (no extra API calls)
        events = []
        app_events_map = status_data.get("events", {})
        for component in status_data.get("components", [])[:3]:
            comp_events = app_events_map.get(component["name"], [])
            for event in comp_events[:2]:  # Max 2 events per component
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

        # Sort events by timestamp (most recent first)
        events.sort(key=lambda x: x.timestamp, reverse=True)

        response = PlatformStatusResponse(
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

        # Cache successful response for 30s
        await _platform_status_cache.set("platform:status", response)

        return response

    except Exception as e:
        logger.error(f"Failed to get platform status: {e}")
        # Return degraded status on error
        return _get_mock_status(error=str(e))


@router.get("/components", response_model=List[ComponentStatus])
async def list_platform_components(
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    List all platform components and their status.

    Returns a list of all monitored Argo CD applications.
    """
    auth_token = credentials.credentials

    try:
        status_data = await argocd_service.get_platform_status(auth_token)
        return [ComponentStatus(**comp) for comp in status_data["components"]]

    except Exception as e:
        logger.error(f"Failed to list components: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list components: {str(e)}")


@router.get("/components/{name}", response_model=ComponentStatus)
async def get_component_status(
    name: str,
    user: User = Depends(get_current_user),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Get detailed status for a specific platform component.

    Args:
        name: Component/application name
    """
    auth_token = credentials.credentials

    try:
        status = await argocd_service.get_application_sync_status(auth_token, name)

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
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Trigger a sync for a platform component.

    Requires cpi-admin or devops role.

    Args:
        name: Component/application name
    """
    auth_token = credentials.credentials

    try:
        result = await argocd_service.sync_application(auth_token, name)

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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    component: Optional[str] = Query(None, description="Filter by component name"),
    limit: int = Query(20, ge=1, le=100, description="Maximum events to return"),
):
    """
    List recent platform events.

    Args:
        component: Optional filter by component name
        limit: Maximum number of events to return
    """
    auth_token = credentials.credentials

    try:
        app_names = [component] if component else settings.argocd_platform_apps_list

        # CAB-687: Fetch events for all apps in parallel
        results = await asyncio.gather(
            *[argocd_service.get_application_events(auth_token, name, limit=limit) for name in app_names],
            return_exceptions=True,
        )

        events = []
        for app_name, result in zip(app_names, results):
            if isinstance(result, Exception):
                logger.debug(f"Could not get events for {app_name}: {result}")
                continue
            for event in result:
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
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Get diff for an OutOfSync component.

    Returns the differences between the desired state (Git) and
    the live state (Kubernetes cluster).

    Args:
        name: Component/application name
    """
    auth_token = credentials.credentials

    try:
        diff_result = await argocd_service.get_application_diff(auth_token, name)

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
