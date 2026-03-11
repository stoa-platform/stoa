"""
Gateway Reconciler — ArgoCD as source of truth for gateway instances.

Periodically reads ArgoCD Applications with the label `stoa.dev/gateway-type`
and upserts/prunes gateway_instances rows with `source='argocd'`.

ArgoCD health status mapping:
  Healthy    → online
  Degraded   → degraded
  Progressing → online (deploying)
  Missing/Unknown/Suspended → offline

Conventions for ArgoCD Application labels:
  stoa.dev/gateway-type: "stoa" | "kong" | "gravitee" | "stoa_sidecar" | ...
  stoa.dev/gateway-mode: "edge-mcp" | "sidecar" | "proxy" | "shadow" (optional)
  stoa.dev/environment: "prod" | "staging" | "dev" (optional, defaults to "prod")
"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import _get_session_factory
from ..models.gateway_instance import GatewayInstance, GatewayInstanceStatus, GatewayType
from ..services.argocd_service import argocd_service

logger = logging.getLogger(__name__)

# ArgoCD health → DB status mapping
_HEALTH_MAP: dict[str, GatewayInstanceStatus] = {
    "Healthy": GatewayInstanceStatus.ONLINE,
    "Progressing": GatewayInstanceStatus.ONLINE,
    "Degraded": GatewayInstanceStatus.DEGRADED,
    "Suspended": GatewayInstanceStatus.OFFLINE,
    "Missing": GatewayInstanceStatus.OFFLINE,
    "Unknown": GatewayInstanceStatus.OFFLINE,
}

# Label keys on ArgoCD Applications
_LABEL_GATEWAY_TYPE = "stoa.dev/gateway-type"
_LABEL_GATEWAY_MODE = "stoa.dev/gateway-mode"
_LABEL_ENVIRONMENT = "stoa.dev/environment"

# Valid gateway type values (must match GatewayType enum)
_VALID_GATEWAY_TYPES = {e.value for e in GatewayType}


class GatewayReconciler:
    """
    Worker that periodically syncs ArgoCD Application state into the
    gateway_instances table, ensuring Console reflects reality.
    """

    def __init__(self) -> None:
        self._running = False
        self._reconcile_interval = settings.GATEWAY_RECONCILER_INTERVAL_SECONDS
        self._last_run: datetime | None = None
        self._last_error: str | None = None

    @property
    def status(self) -> dict:
        """Return reconciler health status for /health endpoint."""
        return {
            "active": self._running,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "last_error": self._last_error,
            "interval_seconds": self._reconcile_interval,
        }

    async def start(self) -> None:
        """Start the reconciler loop."""
        logger.info(
            "Starting Gateway Reconciler: interval=%ds",
            self._reconcile_interval,
        )
        self._running = True

        while self._running:
            try:
                await self._reconcile()
                self._last_run = datetime.now(UTC)
                self._last_error = None
            except Exception as e:
                self._last_error = str(e)
                logger.error("Error in gateway reconciler: %s", e, exc_info=True)

            await asyncio.sleep(self._reconcile_interval)

    async def stop(self) -> None:
        """Stop the reconciler loop."""
        logger.info("Stopping Gateway Reconciler...")
        self._running = False

    async def _reconcile(self) -> None:
        """Main reconciliation: list ArgoCD apps → upsert/prune gateway_instances."""
        # Fetch all ArgoCD applications using static token (no user token needed)
        try:
            all_apps = await argocd_service.get_applications(auth_token="")
        except Exception as e:
            logger.warning("Failed to fetch ArgoCD applications: %s", e)
            return

        # Filter to gateway apps (those with the gateway-type label)
        gateway_apps = []
        for app in all_apps:
            labels = app.get("metadata", {}).get("labels", {})
            if _LABEL_GATEWAY_TYPE in labels:
                gw_type = labels[_LABEL_GATEWAY_TYPE]
                if gw_type in _VALID_GATEWAY_TYPES:
                    gateway_apps.append(app)
                else:
                    logger.warning(
                        "ArgoCD app %s has invalid gateway-type label: %s",
                        app.get("metadata", {}).get("name"),
                        gw_type,
                    )

        # Reconcile into DB
        session_factory = _get_session_factory()
        async with session_factory() as session:
            seen_names = await self._upsert_from_argocd(session, gateway_apps)
            await self._prune_stale_argocd_entries(session, seen_names)
            await session.commit()

        logger.info(
            "Reconciliation complete: %d ArgoCD gateway apps processed",
            len(gateway_apps),
        )

    async def _upsert_from_argocd(
        self,
        session: AsyncSession,
        apps: list[dict],
    ) -> set[str]:
        """Upsert gateway_instances rows from ArgoCD applications. Returns set of instance names."""
        seen_names: set[str] = set()

        for app in apps:
            metadata = app.get("metadata", {})
            labels = metadata.get("labels", {})
            status = app.get("status", {})
            spec = app.get("spec", {})

            app_name = metadata.get("name", "")
            gw_type_str = labels.get(_LABEL_GATEWAY_TYPE, "")
            gw_mode = labels.get(_LABEL_GATEWAY_MODE)
            environment = labels.get(_LABEL_ENVIRONMENT, "prod")
            namespace = spec.get("destination", {}).get("namespace", "stoa-system")

            # Instance name = argocd app name (stable across rollouts)
            instance_name = f"argocd-{app_name}"
            seen_names.add(instance_name)

            # Map ArgoCD health status
            health_status_str = status.get("health", {}).get("status", "Unknown")
            db_status = _HEALTH_MAP.get(health_status_str, GatewayInstanceStatus.OFFLINE)

            sync_status = status.get("sync", {}).get("status", "Unknown")
            revision = status.get("sync", {}).get("revision", "")

            # Build base_url from namespace/app convention
            base_url = f"http://{app_name}.{namespace}.svc.cluster.local"

            # Check if entry exists
            stmt = select(GatewayInstance).where(
                GatewayInstance.name == instance_name,
                GatewayInstance.deleted_at.is_(None),
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            now = datetime.now(UTC)

            if existing:
                # Update health + sync info (don't overwrite heartbeat-enriched fields)
                existing.status = db_status
                existing.last_health_check = now
                existing.health_details = {
                    **(existing.health_details or {}),
                    "argocd_health": health_status_str,
                    "argocd_sync": sync_status,
                    "argocd_revision": revision[:8] if revision else "",
                    "reconciled_at": now.isoformat(),
                }
                if gw_mode:
                    existing.mode = gw_mode
                logger.debug("Updated gateway instance %s: %s", instance_name, db_status.value)
            else:
                # Create new entry
                new_instance = GatewayInstance(
                    name=instance_name,
                    display_name=app_name.replace("-", " ").title(),
                    gateway_type=GatewayType(gw_type_str),
                    environment=environment,
                    base_url=base_url,
                    auth_config={},
                    status=db_status,
                    last_health_check=now,
                    mode=gw_mode,
                    source="argocd",
                    capabilities=[],
                    tags=["argocd-managed"],
                    health_details={
                        "argocd_health": health_status_str,
                        "argocd_sync": sync_status,
                        "argocd_revision": revision[:8] if revision else "",
                        "reconciled_at": now.isoformat(),
                    },
                )
                session.add(new_instance)
                logger.info("Created gateway instance %s from ArgoCD app %s", instance_name, app_name)

        return seen_names

    async def _prune_stale_argocd_entries(
        self,
        session: AsyncSession,
        active_names: set[str],
    ) -> None:
        """Soft-delete argocd-sourced entries that no longer exist in ArgoCD."""
        stmt = select(GatewayInstance).where(
            GatewayInstance.source == "argocd",
            GatewayInstance.deleted_at.is_(None),
        )
        result = await session.execute(stmt)
        argocd_instances = result.scalars().all()

        now = datetime.now(UTC)
        pruned = 0

        for instance in argocd_instances:
            if instance.name not in active_names:
                instance.deleted_at = now
                instance.deleted_by = "gateway-reconciler"
                instance.status = GatewayInstanceStatus.OFFLINE
                instance.health_details = {
                    **(instance.health_details or {}),
                    "offline_reason": "argocd_app_deleted",
                    "pruned_at": now.isoformat(),
                }
                pruned += 1
                logger.info("Pruned gateway instance %s: ArgoCD app no longer exists", instance.name)

        if pruned:
            logger.info("Pruned %d stale argocd gateway instances", pruned)


# Global instance
gateway_reconciler = GatewayReconciler()
