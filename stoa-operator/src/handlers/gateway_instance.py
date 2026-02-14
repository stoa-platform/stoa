"""kopf handlers for GatewayInstance CRD (gostoa.dev/v1alpha1)."""

import logging
from datetime import UTC, datetime

import kopf

logger = logging.getLogger(__name__)

GROUP = "gostoa.dev"
VERSION = "v1alpha1"
PLURAL = "gatewayinstances"


@kopf.on.create(GROUP, VERSION, PLURAL)
async def on_gwi_create(
    spec: dict,
    name: str,
    namespace: str,
    patch: kopf.Patch,
    **_kwargs: object,
) -> dict:
    """Initialize status when a GatewayInstance is created."""
    gw_type = spec.get("gatewayType", "unknown")
    base_url = spec.get("baseUrl", "")
    logger.info(
        "GatewayInstance created: %s/%s type=%s url=%s",
        namespace,
        name,
        gw_type,
        base_url,
    )
    patch.status["phase"] = "offline"
    patch.status["error"] = ""
    patch.status["lastHealthCheck"] = datetime.now(UTC).isoformat()
    return {"message": f"GatewayInstance {name} initialized (phase=offline)"}


@kopf.on.update(GROUP, VERSION, PLURAL)
async def on_gwi_update(
    spec: dict,
    old: dict,
    new: dict,
    name: str,
    namespace: str,
    diff: object,
    **_kwargs: object,
) -> dict:
    """Handle GatewayInstance spec changes."""
    logger.info(
        "GatewayInstance updated: %s/%s diff=%s",
        namespace,
        name,
        diff,
    )
    # Phase 3: will call cp_client.update_gateway()
    return {"message": f"GatewayInstance {name} update acknowledged"}


@kopf.on.delete(GROUP, VERSION, PLURAL)
async def on_gwi_delete(
    spec: dict,
    name: str,
    namespace: str,
    **_kwargs: object,
) -> None:
    """Handle GatewayInstance deletion."""
    logger.info("GatewayInstance deleted: %s/%s", namespace, name)
    # Phase 3: will call cp_client.delete_gateway()


@kopf.on.resume(GROUP, VERSION, PLURAL)
async def on_gwi_resume(
    spec: dict,
    status: dict,
    name: str,
    namespace: str,
    **_kwargs: object,
) -> None:
    """Reconcile existing GatewayInstances on operator startup."""
    phase = status.get("phase", "unknown")
    logger.info(
        "GatewayInstance resumed: %s/%s phase=%s",
        namespace,
        name,
        phase,
    )
