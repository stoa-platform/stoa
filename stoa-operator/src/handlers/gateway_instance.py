"""kopf handlers for GatewayInstance CRD (gostoa.dev/v1alpha1)."""

import logging
import time
from datetime import UTC, datetime

import httpx
import kopf

from src.config import settings
from src.cp_client import cp_client
from src.metrics import DRIFT_DETECTED_TOTAL, RESOURCES_MANAGED, record_reconciliation

logger = logging.getLogger(__name__)

GROUP = "gostoa.dev"
VERSION = "v1alpha1"
PLURAL = "gatewayinstances"


def _spec_to_registration(spec: dict, name: str) -> dict:
    """Map CRD spec to CP API gateway registration payload."""
    return {
        "name": name,
        "display_name": spec.get("displayName", name),
        "gateway_type": spec.get("gatewayType", "stoa"),
        "base_url": spec.get("baseUrl", ""),
        "environment": spec.get("environment", "dev"),
        "mode": spec.get("mode", "edge-mcp"),
    }


@kopf.on.create(GROUP, VERSION, PLURAL)
async def on_gwi_create(
    spec: dict,
    name: str,
    namespace: str,
    patch: kopf.Patch,
    **_kwargs: object,
) -> dict:
    """Register gateway in CP API when a GatewayInstance is created."""
    start = time.monotonic()
    gw_type = spec.get("gatewayType", "unknown")
    base_url = spec.get("baseUrl", "")
    logger.info(
        "GatewayInstance created: %s/%s type=%s url=%s",
        namespace,
        name,
        gw_type,
        base_url,
    )

    try:
        await cp_client.connect()
        result = await cp_client.register_gateway(_spec_to_registration(spec, name))
        gw_id = result.get("id", "")
        patch.status["cpGatewayId"] = gw_id
        patch.status["error"] = ""
        patch.status["lastHealthCheck"] = datetime.now(UTC).isoformat()

        # Trigger health check to determine phase
        try:
            health = await cp_client.health_check_gateway(gw_id)
            patch.status["phase"] = health.get("status", "offline")
        except httpx.HTTPStatusError:
            patch.status["phase"] = "offline"

        RESOURCES_MANAGED.labels(kind="gwi").inc()
        record_reconciliation("gwi", "create", "success", time.monotonic() - start)
        return {"message": f"GatewayInstance {name} registered (id={gw_id})"}

    except httpx.HTTPStatusError as exc:
        msg = f"CP API error: {exc.response.status_code} — {exc.response.text}"
        logger.error("GWI create failed for %s: %s", name, msg)
        patch.status["phase"] = "error"
        patch.status["error"] = msg
        record_reconciliation("gwi", "create", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=30) from exc
    except httpx.RequestError as exc:
        msg = f"CP API unreachable: {exc}"
        logger.error("GWI create failed for %s: %s", name, msg)
        patch.status["phase"] = "error"
        patch.status["error"] = msg
        record_reconciliation("gwi", "create", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=60) from exc
    finally:
        await cp_client.close()


@kopf.on.update(GROUP, VERSION, PLURAL)
async def on_gwi_update(
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
    """Update gateway in CP API when spec changes."""
    start = time.monotonic()
    old_spec = old.get("spec", {})
    new_spec = new.get("spec", {})
    if old_spec == new_spec:
        logger.debug("GWI %s/%s: non-spec update, skipping", namespace, name)
        return {"message": f"GatewayInstance {name} update skipped (no spec change)"}

    gw_id = status.get("cpGatewayId", "")
    if not gw_id:
        logger.warning("GWI %s has no cpGatewayId — cannot update, will re-register", name)
        raise kopf.TemporaryError("Missing cpGatewayId — waiting for create handler", delay=15)

    logger.info("GatewayInstance updated: %s/%s cpGatewayId=%s", namespace, name, gw_id)

    try:
        await cp_client.connect()
        await cp_client.update_gateway(gw_id, _spec_to_registration(spec, name))

        # Re-trigger health check
        try:
            health = await cp_client.health_check_gateway(gw_id)
            patch.status["phase"] = health.get("status", "offline")
        except httpx.HTTPStatusError:
            patch.status["phase"] = "offline"

        patch.status["error"] = ""
        patch.status["lastHealthCheck"] = datetime.now(UTC).isoformat()
        record_reconciliation("gwi", "update", "success", time.monotonic() - start)
        return {"message": f"GatewayInstance {name} updated in CP API"}

    except httpx.HTTPStatusError as exc:
        msg = f"CP API error: {exc.response.status_code} — {exc.response.text}"
        logger.error("GWI update failed for %s: %s", name, msg)
        patch.status["error"] = msg
        record_reconciliation("gwi", "update", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=30) from exc
    except httpx.RequestError as exc:
        msg = f"CP API unreachable: {exc}"
        logger.error("GWI update failed for %s: %s", name, msg)
        patch.status["error"] = msg
        record_reconciliation("gwi", "update", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=60) from exc
    finally:
        await cp_client.close()


@kopf.on.delete(GROUP, VERSION, PLURAL)
async def on_gwi_delete(
    spec: dict,
    name: str,
    namespace: str,
    status: dict,
    **_kwargs: object,
) -> None:
    """Delete gateway from CP API when CRD is deleted."""
    start = time.monotonic()
    gw_id = status.get("cpGatewayId", "")
    logger.info("GatewayInstance deleted: %s/%s cpGatewayId=%s", namespace, name, gw_id)

    if not gw_id:
        logger.info("GWI %s has no cpGatewayId — nothing to delete", name)
        return

    try:
        await cp_client.connect()
        await cp_client.delete_gateway(gw_id)
        logger.info("Gateway %s deleted from CP API", gw_id)
        RESOURCES_MANAGED.labels(kind="gwi").dec()
        record_reconciliation("gwi", "delete", "success", time.monotonic() - start)
    except httpx.HTTPStatusError as exc:
        msg = f"CP API error on delete: {exc.response.status_code}"
        logger.error("GWI delete failed for %s: %s", name, msg)
        record_reconciliation("gwi", "delete", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=30) from exc
    except httpx.RequestError as exc:
        msg = f"CP API unreachable: {exc}"
        logger.error("GWI delete failed for %s: %s", name, msg)
        record_reconciliation("gwi", "delete", "error", time.monotonic() - start)
        raise kopf.TemporaryError(msg, delay=60) from exc
    finally:
        await cp_client.close()


@kopf.on.resume(GROUP, VERSION, PLURAL)
async def on_gwi_resume(
    spec: dict,
    status: dict,
    name: str,
    namespace: str,
    patch: kopf.Patch,
    **_kwargs: object,
) -> None:
    """Reconcile existing GatewayInstances on operator startup."""
    start = time.monotonic()
    gw_id = status.get("cpGatewayId", "")
    phase = status.get("phase", "unknown")
    logger.info(
        "GatewayInstance resumed: %s/%s phase=%s cpGatewayId=%s",
        namespace,
        name,
        phase,
        gw_id,
    )

    try:
        await cp_client.connect()

        if gw_id:
            # Verify gateway still exists in CP API
            try:
                await cp_client.get_gateway(gw_id)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.warning("Gateway %s not found in CP API — re-registering", gw_id)
                    result = await cp_client.register_gateway(_spec_to_registration(spec, name))
                    gw_id = result.get("id", "")
                    patch.status["cpGatewayId"] = gw_id
                else:
                    raise

            # Health check
            try:
                health = await cp_client.health_check_gateway(gw_id)
                patch.status["phase"] = health.get("status", "offline")
            except httpx.HTTPStatusError:
                patch.status["phase"] = "offline"
        else:
            # No cpGatewayId — register for the first time
            result = await cp_client.register_gateway(_spec_to_registration(spec, name))
            gw_id = result.get("id", "")
            patch.status["cpGatewayId"] = gw_id
            patch.status["phase"] = "offline"

        patch.status["error"] = ""
        patch.status["lastHealthCheck"] = datetime.now(UTC).isoformat()
        RESOURCES_MANAGED.labels(kind="gwi").inc()
        record_reconciliation("gwi", "resume", "success", time.monotonic() - start)

    except httpx.HTTPStatusError as exc:
        msg = f"CP API error: {exc.response.status_code}"
        logger.error("GWI resume failed for %s: %s", name, msg)
        patch.status["error"] = msg
        record_reconciliation("gwi", "resume", "error", time.monotonic() - start)
    except httpx.RequestError as exc:
        msg = f"CP API unreachable: {exc}"
        logger.error("GWI resume failed for %s: %s", name, msg)
        patch.status["error"] = msg
        record_reconciliation("gwi", "resume", "error", time.monotonic() - start)
    finally:
        await cp_client.close()


@kopf.on.timer(GROUP, VERSION, PLURAL, interval=settings.RECONCILE_INTERVAL_SECONDS)
async def on_gwi_timer(
    spec: dict,
    status: dict,
    name: str,
    namespace: str,
    patch: kopf.Patch,
    **_kwargs: object,
) -> None:
    """Periodic health check for GatewayInstance resources."""
    start = time.monotonic()
    gw_id = status.get("cpGatewayId", "")
    if not gw_id:
        logger.debug("GWI timer %s/%s: no cpGatewayId, skipping", namespace, name)
        return

    previous_phase = status.get("phase", "unknown")

    try:
        await cp_client.connect()
        health = await cp_client.health_check_gateway(gw_id)
        current_phase = health.get("status", "offline")

        if previous_phase == "online" and current_phase != "online":
            logger.warning(
                "GWI drift: %s/%s phase %s → %s", namespace, name, previous_phase, current_phase
            )
            DRIFT_DETECTED_TOTAL.labels(kind="gwi", drift_type="health_degraded").inc()
        elif previous_phase != "online" and current_phase == "online":
            logger.info("GWI recovery: %s/%s phase %s → online", namespace, name, previous_phase)

        patch.status["phase"] = current_phase
        patch.status["lastHealthCheck"] = datetime.now(UTC).isoformat()
        patch.status["error"] = ""
        record_reconciliation("gwi", "timer", "success", time.monotonic() - start)

    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        msg = f"Timer health check failed: {exc}"
        logger.warning("GWI timer error for %s/%s: %s", namespace, name, msg)
        patch.status["error"] = msg
        record_reconciliation("gwi", "timer", "error", time.monotonic() - start)
    finally:
        await cp_client.close()
