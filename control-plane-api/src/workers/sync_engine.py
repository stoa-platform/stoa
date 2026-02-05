"""Gateway Sync Engine — reconciles desired vs actual state across gateways.

Implements two parallel activities:
1. Event-driven: Consumes gateway-sync-requests Kafka topic for immediate syncs
2. Periodic: Runs every SYNC_ENGINE_INTERVAL_SECONDS for reconciliation + drift detection

Pipeline: Control-Plane API -> Kafka -> SyncEngine -> Gateway Adapters -> DB update

Follows the ErrorSnapshotConsumer threading pattern for Kafka consumption
(kafka-python is synchronous) combined with an asyncio periodic loop.
"""
import asyncio
import contextlib
import json
import logging
import threading
from datetime import UTC, datetime
from uuid import UUID

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from ..adapters.registry import AdapterRegistry
from ..config import settings
from ..database import _get_session_factory
from ..models.gateway_deployment import DeploymentSyncStatus
from ..models.gateway_instance import GatewayInstanceStatus
from ..repositories.gateway_deployment import GatewayDeploymentRepository
from ..repositories.gateway_instance import GatewayInstanceRepository
from ..services.kafka_service import Topics, kafka_service

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "sync-engine"


class SyncEngine:
    """Reconciliation engine for multi-gateway deployments.

    Uses threading for Kafka consumption (kafka-python is synchronous)
    and asyncio for periodic reconciliation and adapter calls.
    """

    def __init__(self):
        self._running = False
        self._consumer: KafkaConsumer | None = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._semaphore: asyncio.Semaphore | None = None

    async def start(self) -> None:
        """Start the sync engine (event consumer + periodic loop)."""
        logger.info("Starting Sync Engine...")
        self._loop = asyncio.get_event_loop()
        self._running = True
        self._semaphore = asyncio.Semaphore(settings.SYNC_ENGINE_MAX_CONCURRENT)

        # Start Kafka consumer in a background thread
        self._thread = threading.Thread(target=self._consume_thread, daemon=True)
        self._thread.start()

        logger.info(
            "Sync Engine started (interval=%ds, max_concurrent=%d, max_retries=%d)",
            settings.SYNC_ENGINE_INTERVAL_SECONDS,
            settings.SYNC_ENGINE_MAX_CONCURRENT,
            settings.SYNC_ENGINE_RETRY_MAX,
        )

        # Run periodic reconciliation loop (blocks until _running is False)
        await self._periodic_loop()

    async def stop(self) -> None:
        """Stop the sync engine."""
        logger.info("Stopping Sync Engine...")
        self._running = False
        if self._consumer:
            self._consumer.close()
        logger.info("Sync Engine stopped")

    # ── Kafka consumer thread ──────────────────────────────────────────

    def _consume_thread(self) -> None:
        """Thread that runs the Kafka consumer for immediate sync triggers."""
        try:
            self._consumer = self._create_consumer()
            if self._consumer is None:
                logger.warning("Sync Engine Kafka consumer not available, event-driven sync disabled")
                return

            logger.info("Sync Engine Kafka consumer connected, listening on %s", Topics.GATEWAY_SYNC_REQUESTS)

            while self._running:
                try:
                    messages = self._consumer.poll(timeout_ms=1000)
                    for _topic_partition, records in messages.items():
                        for message in records:
                            if not self._running:
                                break
                            self._handle_sync_event(message)
                except Exception as e:
                    if self._running:
                        logger.error("Error polling sync messages: %s", e, exc_info=True)

        except Exception as e:
            logger.error("Error in sync engine consumer thread: %s", e, exc_info=True)
        finally:
            if self._consumer:
                self._consumer.close()

    def _create_consumer(self) -> KafkaConsumer | None:
        """Create and configure Kafka consumer for sync requests."""
        try:
            kafka_config = {
                "bootstrap_servers": settings.KAFKA_BOOTSTRAP_SERVERS.split(","),
                "group_id": CONSUMER_GROUP,
                "auto_offset_reset": "latest",
                "enable_auto_commit": True,
                "value_deserializer": lambda m: json.loads(m.decode("utf-8")),
            }

            # Add SASL config if credentials are provided
            if hasattr(settings, "KAFKA_SASL_USERNAME") and settings.KAFKA_SASL_USERNAME:
                kafka_config.update({
                    "security_protocol": "SASL_PLAINTEXT",
                    "sasl_mechanism": "SCRAM-SHA-256",
                    "sasl_plain_username": settings.KAFKA_SASL_USERNAME,
                    "sasl_plain_password": settings.KAFKA_SASL_PASSWORD,
                })

            return KafkaConsumer(Topics.GATEWAY_SYNC_REQUESTS, **kafka_config)

        except KafkaError as e:
            logger.error("Failed to create Kafka consumer for sync engine: %s", e)
            return None

    def _handle_sync_event(self, message) -> None:
        """Handle a sync request from Kafka — dispatches to async reconcile."""
        try:
            data = message.value
            payload = data.get("payload", {})
            deployment_id = payload.get("deployment_id")
            if not deployment_id:
                logger.warning("Sync event missing deployment_id: %s", data)
                return

            if self._loop:
                future = asyncio.run_coroutine_threadsafe(
                    self._reconcile_one(UUID(deployment_id)),
                    self._loop,
                )
                future.add_done_callback(self._reconcile_callback)
        except Exception as e:
            logger.error("Failed to handle sync event: %s", e, exc_info=True)

    @staticmethod
    def _reconcile_callback(future):
        """Log any exceptions from async reconcile dispatched from thread."""
        try:
            future.result()
        except Exception as e:
            logger.error("Reconcile from Kafka event failed: %s", e, exc_info=True)

    # ── Periodic reconciliation loop ───────────────────────────────────

    async def _periodic_loop(self) -> None:
        """Periodic reconciliation loop — runs every SYNC_ENGINE_INTERVAL_SECONDS."""
        while self._running:
            try:
                # Phase A: Reconcile actionable deployments
                await self._reconcile_all()

                # Phase B: Drift detection on SYNCED deployments
                await self._detect_drift()

            except Exception as e:
                logger.error("Error in periodic reconciliation: %s", e, exc_info=True)

            # Sleep in 1-second intervals to check _running flag
            for _ in range(settings.SYNC_ENGINE_INTERVAL_SECONDS):
                if not self._running:
                    return
                await asyncio.sleep(1)

    # ── Phase A: Reconcile actionable deployments ──────────────────────

    async def _reconcile_all(self) -> None:
        """Fetch all actionable deployments and reconcile them concurrently."""
        async with _get_session_factory()() as session:
            repo = GatewayDeploymentRepository(session)
            deployments = await repo.list_by_statuses([
                DeploymentSyncStatus.PENDING,
                DeploymentSyncStatus.DRIFTED,
                DeploymentSyncStatus.ERROR,
                DeploymentSyncStatus.DELETING,
            ])

            if not deployments:
                return

            logger.info("Reconciling %d deployments", len(deployments))

            # Filter out ERROR deployments that exceeded max retries
            actionable = []
            for dep in deployments:
                if (
                    dep.sync_status == DeploymentSyncStatus.ERROR
                    and dep.sync_attempts >= settings.SYNC_ENGINE_RETRY_MAX
                ):
                    logger.debug(
                        "Deployment %s exceeded max retries (%d), skipping",
                        dep.id,
                        settings.SYNC_ENGINE_RETRY_MAX,
                    )
                    continue
                actionable.append(dep)

            if not actionable:
                return

            # Dispatch bounded concurrent tasks
            tasks = [self._reconcile_one(dep.id) for dep in actionable]
            await asyncio.gather(*tasks, return_exceptions=True)

    # ── Core reconciliation for one deployment ─────────────────────────

    async def _reconcile_one(self, deployment_id: UUID) -> None:
        """Reconcile a single deployment against its gateway."""
        async with self._semaphore, _get_session_factory()() as session:
            repo = GatewayDeploymentRepository(session)
            gw_repo = GatewayInstanceRepository(session)

            deployment = await repo.get_by_id(deployment_id)
            if not deployment:
                logger.warning("Deployment %s not found, skipping", deployment_id)
                return

            gateway = await gw_repo.get_by_id(deployment.gateway_instance_id)
            if not gateway:
                logger.error(
                    "Gateway %s not found for deployment %s",
                    deployment.gateway_instance_id,
                    deployment_id,
                )
                deployment.sync_status = DeploymentSyncStatus.ERROR
                deployment.sync_error = "Gateway instance not found"
                await repo.update(deployment)
                await session.commit()
                return

            # Skip if gateway is offline
            if gateway.status == GatewayInstanceStatus.OFFLINE:
                logger.debug(
                    "Gateway %s is offline, skipping deployment %s",
                    gateway.name,
                    deployment_id,
                )
                return

            adapter = AdapterRegistry.create(
                gateway.gateway_type.value,
                config={"base_url": gateway.base_url, "auth_config": gateway.auth_config},
            )

            try:
                await adapter.connect()

                if deployment.sync_status == DeploymentSyncStatus.DELETING:
                    await self._handle_delete(deployment, adapter, repo, session)
                elif deployment.sync_status in (
                    DeploymentSyncStatus.PENDING,
                    DeploymentSyncStatus.DRIFTED,
                    DeploymentSyncStatus.ERROR,
                ):
                    await self._handle_sync(deployment, adapter, repo, session)

            except Exception as e:
                logger.error(
                    "Reconcile failed for deployment %s: %s",
                    deployment_id,
                    e,
                    exc_info=True,
                )
                deployment.sync_status = DeploymentSyncStatus.ERROR
                deployment.sync_error = str(e)[:500]
                deployment.sync_attempts += 1
                deployment.last_sync_attempt = datetime.now(UTC)
                await repo.update(deployment)
                await session.commit()
            finally:
                with contextlib.suppress(Exception):
                    await adapter.disconnect()

    async def _handle_sync(self, deployment, adapter, repo, session) -> None:
        """Handle PENDING/DRIFTED/ERROR deployment — sync API to gateway."""
        now = datetime.now(UTC)
        deployment.sync_status = DeploymentSyncStatus.SYNCING
        deployment.last_sync_attempt = now
        await repo.update(deployment)
        await session.commit()

        tenant_id = (deployment.desired_state or {}).get("tenant_id", "")
        result = await adapter.sync_api(deployment.desired_state, tenant_id)

        if result.success:
            deployment.sync_status = DeploymentSyncStatus.SYNCED
            deployment.actual_state = result.data or deployment.desired_state
            deployment.actual_at = now
            deployment.gateway_resource_id = result.resource_id or deployment.gateway_resource_id
            deployment.last_sync_success = now
            deployment.sync_error = None

            # Sync bound policies (non-blocking — failure is warned, not fatal)
            try:
                from ..repositories.gateway_policy import GatewayPolicyRepository
                policy_repo = GatewayPolicyRepository(session)
                policies = await policy_repo.get_policies_for_deployment(
                    api_catalog_id=deployment.api_catalog_id,
                    gateway_instance_id=deployment.gateway_instance_id,
                    tenant_id=tenant_id,
                )
                for policy in policies:
                    try:
                        policy_spec = {
                            "name": policy.name,
                            "type": policy.policy_type.value,
                            "config": policy.config,
                            "priority": policy.priority,
                            "api_id": deployment.gateway_resource_id,
                        }
                        await adapter.upsert_policy(policy_spec)
                    except Exception as pe:
                        logger.warning(
                            "Failed to apply policy %s to deployment %s: %s",
                            policy.id, deployment.id, pe,
                        )
            except Exception as e:
                logger.warning("Policy sync failed for deployment %s: %s", deployment.id, e)

            await repo.update(deployment)
            await session.commit()
            logger.info(
                "Synced deployment %s (resource=%s)",
                deployment.id,
                deployment.gateway_resource_id,
            )
        else:
            deployment.sync_status = DeploymentSyncStatus.ERROR
            deployment.sync_error = result.error or "Sync failed"
            deployment.sync_attempts += 1
            await repo.update(deployment)
            await session.commit()
            logger.warning("Sync failed for deployment %s: %s", deployment.id, result.error)

    async def _handle_delete(self, deployment, adapter, repo, session) -> None:
        """Handle DELETING deployment — remove API from gateway."""
        result = await adapter.delete_api(deployment.gateway_resource_id)
        if result.success:
            await repo.delete(deployment)
            await session.commit()
            logger.info("Deleted deployment %s from gateway", deployment.id)
        else:
            deployment.sync_error = result.error or "Delete failed"
            deployment.sync_attempts += 1
            deployment.last_sync_attempt = datetime.now(UTC)
            await repo.update(deployment)
            await session.commit()
            logger.warning("Delete failed for deployment %s: %s", deployment.id, result.error)

    # ── Phase B: Drift detection ───────────────────────────────────────

    async def _detect_drift(self) -> None:
        """Check SYNCED deployments for drift against gateway actual state."""
        async with _get_session_factory()() as session:
            repo = GatewayDeploymentRepository(session)
            synced = await repo.list_synced()

            if not synced:
                return

            logger.debug("Checking drift for %d synced deployments", len(synced))

            # Group by gateway to minimize adapter connections
            by_gateway: dict[UUID, list] = {}
            for dep in synced:
                by_gateway.setdefault(dep.gateway_instance_id, []).append(dep)

            gw_repo = GatewayInstanceRepository(session)

            for gw_id, deps in by_gateway.items():
                gateway = await gw_repo.get_by_id(gw_id)
                if not gateway or gateway.status == GatewayInstanceStatus.OFFLINE:
                    continue

                adapter = AdapterRegistry.create(
                    gateway.gateway_type.value,
                    config={"base_url": gateway.base_url, "auth_config": gateway.auth_config},
                )
                try:
                    await adapter.connect()
                    apis = await adapter.list_apis()

                    # Build lookup of gateway APIs by resource ID
                    gw_api_map: dict[str, dict] = {}
                    for api in apis:
                        api_id = api.get("id") or api.get("apiId") or api.get("resource_id")
                        if api_id:
                            gw_api_map[str(api_id)] = api

                    for dep in deps:
                        if not dep.gateway_resource_id:
                            continue

                        gw_api = gw_api_map.get(dep.gateway_resource_id)
                        if gw_api is None:
                            dep.sync_status = DeploymentSyncStatus.DRIFTED
                            dep.sync_error = "API not found on gateway (external deletion)"
                            await repo.update(dep)
                            await self._emit_drift_event(dep, "api_missing")
                            logger.warning(
                                "Drift detected: deployment %s API missing from gateway",
                                dep.id,
                            )
                        else:
                            gw_hash = gw_api.get("spec_hash", "")
                            desired_hash = (dep.desired_state or {}).get("spec_hash", "")
                            if gw_hash and desired_hash and gw_hash != desired_hash:
                                dep.sync_status = DeploymentSyncStatus.DRIFTED
                                dep.sync_error = (
                                    f"Spec hash mismatch: "
                                    f"desired={desired_hash[:8]}... actual={gw_hash[:8]}..."
                                )
                                await repo.update(dep)
                                await self._emit_drift_event(dep, "spec_hash_mismatch")
                                logger.warning(
                                    "Drift detected: deployment %s spec hash mismatch",
                                    dep.id,
                                )

                    await session.commit()
                except Exception as e:
                    logger.error(
                        "Drift detection failed for gateway %s: %s",
                        gateway.name,
                        e,
                        exc_info=True,
                    )
                finally:
                    with contextlib.suppress(Exception):
                        await adapter.disconnect()

    async def _emit_drift_event(self, deployment, drift_type: str) -> None:
        """Emit a drift-detected event to gateway-events topic."""
        tenant_id = (deployment.desired_state or {}).get("tenant_id", "")
        try:
            await kafka_service.publish(
                topic=Topics.GATEWAY_EVENTS,
                event_type="drift-detected",
                tenant_id=tenant_id,
                payload={
                    "deployment_id": str(deployment.id),
                    "gateway_instance_id": str(deployment.gateway_instance_id),
                    "drift_type": drift_type,
                },
            )
        except Exception as e:
            logger.warning("Failed to emit drift event: %s", e)


# Singleton instance
sync_engine = SyncEngine()
