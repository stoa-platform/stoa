"""ArgoCD Admin router — sync, diff, and platform status (CAB-1706 W3)

Exposes ArgoCD operations to cpi-admin users only.
Uses the global argocd_service singleton (static API token).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth.dependencies import User, get_current_user
from ..services.argocd_service import argocd_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/admin/argocd", tags=["ArgoCD Admin"])


# ---------------------------------------------------------------------------
# Schemas (prefixed to avoid OpenAPI name collision with platform.py)
# ---------------------------------------------------------------------------


class ArgoCDSyncRequest(BaseModel):
    revision: str = Field("HEAD", description="Git revision to sync to")
    prune: bool = Field(False, description="Prune resources no longer in Git")


class ArgoCDSyncResponse(BaseModel):
    application: str
    status: str
    message: str


class ArgoCDDiffResource(BaseModel):
    name: str | None = None
    namespace: str | None = None
    kind: str | None = None
    group: str | None = None
    status: str | None = None
    health: str | None = None
    diff: dict | None = None


class ArgoCDDiffResponse(BaseModel):
    application: str
    total_resources: int
    diff_count: int
    resources: list[ArgoCDDiffResource]


class ArgoCDPlatformStatusResponse(BaseModel):
    status: str
    components: list[dict]
    checked_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_cpi_admin(user: User) -> None:
    if "cpi-admin" not in user.roles:
        raise HTTPException(status_code=403, detail="cpi-admin role required")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/sync/{app_name}", response_model=ArgoCDSyncResponse)
async def trigger_sync(
    app_name: str,
    request: ArgoCDSyncRequest | None = None,
    user: User = Depends(get_current_user),
):
    """Trigger an ArgoCD sync for an application. cpi-admin only."""
    _require_cpi_admin(user)

    body = request or ArgoCDSyncRequest()
    try:
        await argocd_service.sync_application(
            auth_token="",
            name=app_name,
            revision=body.revision,
            prune=body.prune,
        )
        logger.info("ArgoCD sync triggered for %s by %s", app_name, user.username)
        return ArgoCDSyncResponse(
            application=app_name,
            status="syncing",
            message=f"Sync triggered for {app_name} at revision {body.revision}",
        )
    except Exception as e:
        logger.error("ArgoCD sync failed for %s: %s", app_name, e)
        raise HTTPException(status_code=502, detail=f"ArgoCD sync failed: {e}")


@router.get("/diff/{app_name}", response_model=ArgoCDDiffResponse)
async def get_application_diff(
    app_name: str,
    user: User = Depends(get_current_user),
):
    """Get diff between desired and live state. cpi-admin only."""
    _require_cpi_admin(user)

    try:
        diff = await argocd_service.get_application_diff(auth_token="", name=app_name)
        return ArgoCDDiffResponse(**diff)
    except Exception as e:
        logger.error("ArgoCD diff failed for %s: %s", app_name, e)
        raise HTTPException(status_code=502, detail=f"ArgoCD diff failed: {e}")


@router.get("/status", response_model=ArgoCDPlatformStatusResponse)
async def get_platform_status(
    user: User = Depends(get_current_user),
):
    """Get aggregated platform status for all ArgoCD applications. cpi-admin only."""
    _require_cpi_admin(user)

    try:
        status = await argocd_service.get_platform_status(auth_token="")
        return ArgoCDPlatformStatusResponse(**status)
    except Exception as e:
        logger.error("ArgoCD status failed: %s", e)
        raise HTTPException(status_code=502, detail=f"ArgoCD status failed: {e}")
