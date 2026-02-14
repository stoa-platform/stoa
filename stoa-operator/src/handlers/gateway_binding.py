"""kopf handlers for GatewayBinding CRD (gostoa.dev/v1alpha1)."""

import logging
import time
from datetime import UTC, datetime

import httpx
import kopf

from src.cp_client import cp_client
from src.metrics import RESOURCES_MANAGED, record_reconciliation

logger = logging.getLogger(__name__)

GROUP = "gostoa.dev"
VERSION = "v1alpha1"
PLURAL = "gatewaybindings"


async def _resolve_gateway_id(gw_name: str) -> str:
    """Resolve a gatewayRef name to a CP API gateway_instance_id."""
    gw = await cp_client.get_gateway_by_name(gw_name)
    if not gw:
        raise kopf.TemporaryError(
            f"Gateway '{gw_name}' not found in CP API — waiting for GWI registration",
            delay=30,
        )
    return gw["id"]


async def _resolve_catalog_id(api_name: str) -> str:
    """Resolve an apiRef name to a CP API catalog entry id."""
    entries = await cp_client.get_catalog_entries()
    for entry in entries:
        if entry.get("api_name") == api_name:
            return entry["id"]
    raise kopf.PermanentError(f"API '{api_name}' not found in catalog — cannot deploy")


@kopf.on.create(GROUP, VERSION, PLURAL)
async def on_gwb_create(
    spec: dict,
    name: str,
    namespace: str,
    patch: kopf.Patch,
    **_kwargs: object,
) -> dict:
    """Create deployment in CP API when a GatewayBinding is created."""
    start = time.monotonic()
    api_name = spec.get("apiRef", {}).get("name", "unknown")
    gw_name = spec.get("gatewayRef", {}).get("name", "unknown")
    logger.info(
        "GatewayBinding created: %s/%s api=%s gateway=%s",
        namespace,
        name,
        api_name,
        gw_name,
    )

    try:
        await cp_client.connect()

        gateway_id = await _resolve_gateway_id(gw_name)
        catalog_id = await _resolve_catalog_id(api_name)

        deployments = await cp_client.create_deployment(catalog_id, [gateway_id])
        deployment_id = deployments[0].get("id", "") if deployments else ""

        patch.status["gatewayResourceId"] = deployment_id
        patch.status["syncStatus"] = "synced"
        patch.status["syncAttempts"] = 1
        patch.status["lastSyncAttempt"] = datetime.now(UTC).isoformat()
        patch.status["syncError"] = ""
        RESOURCES_MANAGED.labels(kind="gwb").inc()
        record_reconciliation("gwb", "create", "success", time.monotonic() - start)
        return {"message": f"GatewayBinding {name} deployed (deployment={deployment_id})"}

    except (kopf.TemporaryError, kopf.PermanentError):
        record_reconciliation("gwb", "create", "error", time.monotonic() - start)
        raise
    except httpx.HTTPStatusError as exc:
        msg = f"CP API error: {exc.response.status_code} — {exc.response.text}"
        logger.error("GWB create failed for %s: %s", name, msg)
        patch.status["syncStatus"] = "error"
        patch.status["syncError"] = msg
        patch.status["syncAttempts"] = (patch.status.get("syncAttempts") or 0) + 1
        patch.status["lastSyncAttempt"] = datetime.now(UTC).isoformat()
        record_reconciliation("gwb", "create", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=30) from exc
    except httpx.RequestError as exc:
        msg = f"CP API unreachable: {exc}"
        logger.error("GWB create failed for %s: %s", name, msg)
        patch.status["syncStatus"] = "error"
        patch.status["syncError"] = msg
        patch.status["lastSyncAttempt"] = datetime.now(UTC).isoformat()
        record_reconciliation("gwb", "create", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=60) from exc
    finally:
        await cp_client.close()


@kopf.on.update(GROUP, VERSION, PLURAL)
async def on_gwb_update(
    spec: dict,
    old: dict,
    new: dict,
    name: str,
    namespace: str,
    status: dict,
    diff: object,
    patch: kopf.Patch,
    **_kwargs: object,
) -> dict:
    """Force re-sync deployment when GatewayBinding spec changes."""
    start = time.monotonic()
    old_spec = old.get("spec", {})
    new_spec = new.get("spec", {})
    if old_spec == new_spec:
        logger.debug("GWB %s/%s: non-spec update, skipping", namespace, name)
        return {"message": f"GatewayBinding {name} update skipped (no spec change)"}

    deployment_id = status.get("gatewayResourceId", "")
    if not deployment_id:
        logger.warning("GWB %s has no gatewayResourceId — waiting for create", name)
        raise kopf.TemporaryError(
            "Missing gatewayResourceId — waiting for create handler", delay=15
        )

    logger.info(
        "GatewayBinding spec changed: %s/%s — triggering re-sync",
        namespace,
        name,
    )

    try:
        await cp_client.connect()
        await cp_client.force_sync_deployment(deployment_id)

        patch.status["syncStatus"] = "synced"
        patch.status["syncAttempts"] = (status.get("syncAttempts") or 0) + 1
        patch.status["lastSyncAttempt"] = datetime.now(UTC).isoformat()
        patch.status["syncError"] = ""
        record_reconciliation("gwb", "update", "success", time.monotonic() - start)
        return {"message": f"GatewayBinding {name} re-synced"}

    except httpx.HTTPStatusError as exc:
        msg = f"CP API error: {exc.response.status_code} — {exc.response.text}"
        logger.error("GWB update failed for %s: %s", name, msg)
        patch.status["syncStatus"] = "error"
        patch.status["syncError"] = msg
        patch.status["syncAttempts"] = (status.get("syncAttempts") or 0) + 1
        patch.status["lastSyncAttempt"] = datetime.now(UTC).isoformat()
        record_reconciliation("gwb", "update", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=30) from exc
    except httpx.RequestError as exc:
        msg = f"CP API unreachable: {exc}"
        logger.error("GWB update failed for %s: %s", name, msg)
        patch.status["syncStatus"] = "error"
        patch.status["syncError"] = msg
        patch.status["lastSyncAttempt"] = datetime.now(UTC).isoformat()
        record_reconciliation("gwb", "update", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=60) from exc
    finally:
        await cp_client.close()


@kopf.on.delete(GROUP, VERSION, PLURAL)
async def on_gwb_delete(
    spec: dict,
    name: str,
    namespace: str,
    status: dict,
    **_kwargs: object,
) -> None:
    """Delete deployment from CP API when CRD is deleted."""
    start = time.monotonic()
    deployment_id = status.get("gatewayResourceId", "")
    api_name = spec.get("apiRef", {}).get("name", "unknown")
    gw_name = spec.get("gatewayRef", {}).get("name", "unknown")
    logger.info(
        "GatewayBinding deleted: %s/%s api=%s gateway=%s deployment=%s",
        namespace,
        name,
        api_name,
        gw_name,
        deployment_id,
    )

    if not deployment_id:
        logger.info("GWB %s has no gatewayResourceId — nothing to delete", name)
        return

    try:
        await cp_client.connect()
        await cp_client.delete_deployment(deployment_id)
        logger.info("Deployment %s deleted from CP API", deployment_id)
        RESOURCES_MANAGED.labels(kind="gwb").dec()
        record_reconciliation("gwb", "delete", "success", time.monotonic() - start)
    except httpx.HTTPStatusError as exc:
        msg = f"CP API error on delete: {exc.response.status_code}"
        logger.error("GWB delete failed for %s: %s", name, msg)
        record_reconciliation("gwb", "delete", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=30) from exc
    except httpx.RequestError as exc:
        msg = f"CP API unreachable: {exc}"
        logger.error("GWB delete failed for %s: %s", name, msg)
        record_reconciliation("gwb", "delete", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=60) from exc
    finally:
        await cp_client.close()


@kopf.on.resume(GROUP, VERSION, PLURAL)
async def on_gwb_resume(
    spec: dict,
    status: dict,
    name: str,
    namespace: str,
    patch: kopf.Patch,
    **_kwargs: object,
) -> None:
    """Reconcile existing GatewayBindings on operator startup."""
    start = time.monotonic()
    deployment_id = status.get("gatewayResourceId", "")
    sync_status = status.get("syncStatus", "unknown")
    api_name = spec.get("apiRef", {}).get("name", "unknown")
    logger.info(
        "GatewayBinding resumed: %s/%s api=%s syncStatus=%s deployment=%s",
        namespace,
        name,
        api_name,
        sync_status,
        deployment_id,
    )

    try:
        await cp_client.connect()

        if deployment_id:
            # Verify deployment still exists
            try:
                dep = await cp_client.get_deployment(deployment_id)
                patch.status["syncStatus"] = dep.get("sync_status", sync_status)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.warning("Deployment %s not found — re-creating", deployment_id)
                    gw_name = spec.get("gatewayRef", {}).get("name", "unknown")
                    gateway_id = await _resolve_gateway_id(gw_name)
                    catalog_id = await _resolve_catalog_id(api_name)
                    deployments = await cp_client.create_deployment(catalog_id, [gateway_id])
                    new_id = deployments[0].get("id", "") if deployments else ""
                    patch.status["gatewayResourceId"] = new_id
                    patch.status["syncStatus"] = "synced"
                else:
                    raise
        else:
            # No deployment yet — create one
            gw_name = spec.get("gatewayRef", {}).get("name", "unknown")
            gateway_id = await _resolve_gateway_id(gw_name)
            catalog_id = await _resolve_catalog_id(api_name)
            deployments = await cp_client.create_deployment(catalog_id, [gateway_id])
            new_id = deployments[0].get("id", "") if deployments else ""
            patch.status["gatewayResourceId"] = new_id
            patch.status["syncStatus"] = "synced"

        patch.status["syncError"] = ""
        patch.status["lastSyncAttempt"] = datetime.now(UTC).isoformat()
        RESOURCES_MANAGED.labels(kind="gwb").inc()
        record_reconciliation("gwb", "resume", "success", time.monotonic() - start)

    except (kopf.TemporaryError, kopf.PermanentError):
        record_reconciliation("gwb", "resume", "error", time.monotonic() - start)
        raise
    except httpx.HTTPStatusError as exc:
        msg = f"CP API error: {exc.response.status_code}"
        logger.error("GWB resume failed for %s: %s", name, msg)
        patch.status["syncError"] = msg
        record_reconciliation("gwb", "resume", "error", time.monotonic() - start)
    except httpx.RequestError as exc:
        msg = f"CP API unreachable: {exc}"
        logger.error("GWB resume failed for %s: %s", name, msg)
        patch.status["syncError"] = msg
        record_reconciliation("gwb", "resume", "error", time.monotonic() - start)
    finally:
        await cp_client.close()
