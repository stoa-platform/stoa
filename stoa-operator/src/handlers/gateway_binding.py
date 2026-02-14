"""kopf handlers for GatewayBinding CRD (gostoa.dev/v1alpha1)."""

import logging
from datetime import UTC, datetime

import kopf

logger = logging.getLogger(__name__)

GROUP = "gostoa.dev"
VERSION = "v1alpha1"
PLURAL = "gatewaybindings"


@kopf.on.create(GROUP, VERSION, PLURAL)
async def on_gwb_create(
    spec: dict,
    name: str,
    namespace: str,
    patch: kopf.Patch,
    **_kwargs: object,
) -> dict:
    """Initialize status when a GatewayBinding is created."""
    api_name = spec.get("apiRef", {}).get("name", "unknown")
    gw_name = spec.get("gatewayRef", {}).get("name", "unknown")
    logger.info(
        "GatewayBinding created: %s/%s api=%s gateway=%s",
        namespace,
        name,
        api_name,
        gw_name,
    )
    patch.status["syncStatus"] = "pending"
    patch.status["syncAttempts"] = 0
    patch.status["lastSyncAttempt"] = datetime.now(UTC).isoformat()
    patch.status["syncError"] = ""
    return {"message": f"GatewayBinding {name} initialized (syncStatus=pending)"}


@kopf.on.update(GROUP, VERSION, PLURAL)
async def on_gwb_update(
    spec: dict,
    old: dict,
    new: dict,
    name: str,
    namespace: str,
    diff: object,
    patch: kopf.Patch,
    **_kwargs: object,
) -> dict:
    """Handle GatewayBinding spec changes — reset sync status if spec changed."""
    old_spec = old.get("spec", {})
    new_spec = new.get("spec", {})
    if old_spec != new_spec:
        logger.info(
            "GatewayBinding spec changed: %s/%s — resetting to pending",
            namespace,
            name,
        )
        patch.status["syncStatus"] = "pending"
        patch.status["syncAttempts"] = 0
        patch.status["syncError"] = ""
    else:
        logger.debug("GatewayBinding %s/%s: non-spec update, skipping", namespace, name)
    # Phase 3: will call adapter.sync_api()
    return {"message": f"GatewayBinding {name} update acknowledged"}


@kopf.on.delete(GROUP, VERSION, PLURAL)
async def on_gwb_delete(
    spec: dict,
    name: str,
    namespace: str,
    **_kwargs: object,
) -> None:
    """Handle GatewayBinding deletion."""
    api_name = spec.get("apiRef", {}).get("name", "unknown")
    gw_name = spec.get("gatewayRef", {}).get("name", "unknown")
    logger.info(
        "GatewayBinding deleted: %s/%s api=%s gateway=%s",
        namespace,
        name,
        api_name,
        gw_name,
    )
    # Phase 3: will call adapter.delete_api()


@kopf.on.resume(GROUP, VERSION, PLURAL)
async def on_gwb_resume(
    spec: dict,
    status: dict,
    name: str,
    namespace: str,
    **_kwargs: object,
) -> None:
    """Reconcile existing GatewayBindings on operator startup."""
    sync_status = status.get("syncStatus", "unknown")
    api_name = spec.get("apiRef", {}).get("name", "unknown")
    logger.info(
        "GatewayBinding resumed: %s/%s api=%s syncStatus=%s",
        namespace,
        name,
        api_name,
        sync_status,
    )
