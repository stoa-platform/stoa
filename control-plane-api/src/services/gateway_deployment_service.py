"""Service layer for gateway deployment orchestration.

Extracts business logic from the gateway_deployments router and adds Kafka
event emission for the sync engine to consume.
"""

import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.repositories.gateway_deployment import GatewayDeploymentRepository
from src.repositories.gateway_instance import GatewayInstanceRepository
from src.services.kafka_service import Topics, kafka_service
from src.services.sync_step_tracker import SyncStepTracker

logger = logging.getLogger(__name__)


class GatewayDeploymentService:
    """Business logic for deploying APIs to gateways."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.deploy_repo = GatewayDeploymentRepository(db)
        self.gw_repo = GatewayInstanceRepository(db)

    @staticmethod
    def build_desired_state(api_catalog) -> dict:
        """Build desired state dict from an API catalog entry.

        Computes a SHA256 spec_hash from the OpenAPI spec or metadata.
        """
        spec_data = api_catalog.openapi_spec or api_catalog.api_metadata or {}
        spec_hash = hashlib.sha256(json.dumps(spec_data, sort_keys=True, default=str).encode()).hexdigest()

        # Extract backend_url from OpenAPI servers or api_metadata
        backend_url = ""
        metadata = api_catalog.api_metadata or {}
        if isinstance(metadata, dict):
            backend_url = metadata.get("backend_url", metadata.get("url", ""))
        if not backend_url and isinstance(spec_data, dict):
            servers = spec_data.get("servers", [])
            if servers and isinstance(servers, list) and isinstance(servers[0], dict):
                backend_url = servers[0].get("url", "")

        # Extract HTTP methods from OpenAPI spec paths
        methods: set[str] = set()
        if isinstance(spec_data, dict):
            paths = spec_data.get("paths", {})
            if isinstance(paths, dict):
                for path_item in paths.values():
                    if isinstance(path_item, dict):
                        for method in path_item:
                            if method.lower() in {"get", "post", "put", "patch", "delete", "head", "options"}:
                                methods.add(method.upper())

        return {
            "spec_hash": spec_hash,
            "version": api_catalog.version,
            "api_name": api_catalog.api_name,
            "api_id": api_catalog.api_id,
            "api_catalog_id": str(api_catalog.id),
            "tenant_id": api_catalog.tenant_id,
            "backend_url": backend_url,
            "methods": sorted(methods) if methods else ["GET", "POST", "PUT", "DELETE"],
            "activated": True,
            "openapi_spec": spec_data if spec_data else None,
        }

    async def deploy_api(
        self,
        api_catalog_id: UUID,
        gateway_instance_ids: list[UUID],
    ) -> list[GatewayDeployment]:
        """Deploy an API to one or more gateways.

        Creates or updates GatewayDeployment records with PENDING status,
        then emits Kafka events on gateway-sync-requests.

        Raises:
            ValueError: If API catalog entry or gateway not found.
        """
        result = await self.db.execute(select(APICatalog).where(APICatalog.id == api_catalog_id))
        api_catalog = result.scalar_one_or_none()
        if not api_catalog:
            raise ValueError("API catalog entry not found")

        now = datetime.now(UTC)
        deployments: list[GatewayDeployment] = []

        for gw_id in gateway_instance_ids:
            gateway = await self.gw_repo.get_by_id(gw_id)
            if not gateway:
                raise ValueError(f"Gateway instance {gw_id} not found")
            if not gateway.enabled:
                raise PermissionError(f"Gateway '{gateway.name}' is disabled. " f"Enable it before deploying.")

            existing = await self.deploy_repo.get_by_api_and_gateway(api_catalog_id, gw_id)
            if existing:
                existing.desired_state = self.build_desired_state(api_catalog)
                existing.desired_at = now
                existing.sync_status = DeploymentSyncStatus.PENDING
                existing.sync_error = None
                existing.sync_attempts = 0
                await self.deploy_repo.update(existing)
                deployments.append(existing)
            else:
                deployment = GatewayDeployment(
                    api_catalog_id=api_catalog_id,
                    gateway_instance_id=gw_id,
                    desired_state=self.build_desired_state(api_catalog),
                    desired_at=now,
                    sync_status=DeploymentSyncStatus.PENDING,
                )
                deployment = await self.deploy_repo.create(deployment)
                deployments.append(deployment)

        if settings.is_sync_engine_enabled:
            await self._emit_sync_requests(deployments, api_catalog.tenant_id)

        if settings.is_sse_enabled:
            await self._emit_sse_events(deployments, api_catalog.tenant_id)

        # Record event_emitted step for observability
        for dep in deployments:
            tracker = SyncStepTracker.from_list(dep.sync_steps or [])
            tracker.start("event_emitted")
            tracker.complete(
                "event_emitted",
                detail=f"kafka={'yes' if settings.is_sync_engine_enabled else 'no'} "
                f"sse={'yes' if settings.is_sse_enabled else 'no'}",
            )
            dep.sync_steps = tracker.to_list()
            await self.deploy_repo.update(dep)

        logger.info(
            "Deployed API %s to %d gateway(s) (mode=%s)",
            api_catalog.api_name,
            len(deployments),
            settings.DEPLOY_MODE,
        )
        return deployments

    async def undeploy(self, deployment_id: UUID) -> None:
        """Undeploy an API from a gateway.

        If the deployment has a gateway_resource_id (was synced), marks DELETING.
        Otherwise, deletes the record directly.
        """
        deployment = await self.deploy_repo.get_by_id(deployment_id)
        if not deployment:
            raise ValueError("Deployment not found")

        if deployment.gateway_resource_id:
            deployment.sync_status = DeploymentSyncStatus.DELETING
            await self.deploy_repo.update(deployment)
            await self._emit_sync_request(deployment)
        else:
            await self.deploy_repo.delete(deployment)

    async def force_sync(self, deployment_id: UUID) -> GatewayDeployment:
        """Force re-sync a deployment (reset to PENDING, emit Kafka)."""
        deployment = await self.deploy_repo.get_by_id(deployment_id)
        if not deployment:
            raise ValueError("Deployment not found")

        deployment.sync_status = DeploymentSyncStatus.PENDING
        deployment.sync_error = None
        deployment.sync_attempts = 0
        deployment.desired_generation = (deployment.desired_generation or 0) + 1
        await self.deploy_repo.update(deployment)

        await self._emit_sync_request(deployment)
        return deployment

    async def _emit_sync_requests(self, deployments: list[GatewayDeployment], tenant_id: str) -> None:
        """Emit Kafka events for a batch of deployments."""
        for dep in deployments:
            try:
                await kafka_service.publish(
                    topic=Topics.GATEWAY_SYNC_REQUESTS,
                    event_type="sync-deployment",
                    tenant_id=tenant_id or "",
                    payload={"deployment_id": str(dep.id)},
                )
            except Exception as e:
                logger.warning("Failed to emit sync request for %s: %s", dep.id, e)

    async def _emit_sync_request(self, deployment: GatewayDeployment) -> None:
        """Emit a single Kafka sync request event."""
        tenant_id = (deployment.desired_state or {}).get("tenant_id", "")
        try:
            await kafka_service.publish(
                topic=Topics.GATEWAY_SYNC_REQUESTS,
                event_type="sync-deployment",
                tenant_id=tenant_id,
                payload={"deployment_id": str(deployment.id)},
            )
        except Exception as e:
            logger.warning("Failed to emit sync request for %s: %s", deployment.id, e)

    async def _emit_sse_events(self, deployments: list[GatewayDeployment], tenant_id: str) -> None:
        """Emit SSE events to notify connected Links of pending deployments (ADR-059)."""
        from src.events.event_bus import event_bus

        for dep in deployments:
            try:
                await event_bus.publish(
                    tenant_id=tenant_id,
                    event_type="sync-deployment",
                    data={
                        "deployment_id": str(dep.id),
                        "api_catalog_id": str(dep.api_catalog_id),
                        "gateway_instance_id": str(dep.gateway_instance_id),
                        "sync_status": dep.sync_status.value,
                        "desired_state": dep.desired_state,
                    },
                    gateway_id=str(dep.gateway_instance_id),
                )
            except Exception as e:
                logger.warning("Failed to emit SSE event for deployment %s: %s", dep.id, e)
