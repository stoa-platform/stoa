"""Promotion service — business logic for GitOps promotion flow (CAB-1706)"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.catalog import APICatalog
from ..models.gateway_deployment import DeploymentSyncStatus
from ..models.gateway_instance import GatewayInstance
from ..models.promotion import Promotion, PromotionStatus, validate_promotion_chain
from ..notifications.promotion_notifier import notify_promotion_event
from ..repositories.deployment import DeploymentRepository
from ..repositories.gateway_deployment import GatewayDeploymentRepository
from ..repositories.promotion import PromotionRepository
from ..services.environment_aliases import deployment_environment_matches
from ..services.gateway_topology import normalize_gateway_topology
from ..services.kafka_service import Topics, kafka_service

logger = logging.getLogger(__name__)


class PromotionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PromotionRepository(db)
        self.deployment_repo = DeploymentRepository(db)
        self.gw_deploy_repo = GatewayDeploymentRepository(db)

    async def create_promotion(
        self,
        tenant_id: str,
        api_id: str,
        source_deployment_id: UUID,
        target_gateway_ids: list[UUID],
        source_environment: str,
        target_environment: str,
        message: str,
        requested_by: str,
        user_id: str,
    ) -> Promotion:
        """Create a new promotion request after validating the chain."""
        validate_promotion_chain(source_environment, target_environment)

        api_catalog = await self._validate_gateway_aware_request(
            tenant_id=tenant_id,
            api_id=api_id,
            source_deployment_id=source_deployment_id,
            target_gateway_ids=target_gateway_ids,
            source_environment=source_environment,
            target_environment=target_environment,
        )

        active = await self.repo.get_active_for_target(api_catalog.api_id, target_environment)
        if active:
            raise ValueError(
                f"Active promotion already exists for {api_catalog.api_id} → {target_environment} "
                f"(id={active.id}, status={active.status})"
            )

        promotion = Promotion(
            tenant_id=tenant_id,
            api_id=api_catalog.api_id,
            source_environment=source_environment,
            target_environment=target_environment,
            source_deployment_id=source_deployment_id,
            target_gateway_ids=[str(gateway_id) for gateway_id in target_gateway_ids],
            status=PromotionStatus.PENDING.value,
            message=message,
            requested_by=requested_by,
        )
        promotion = await self.repo.create(promotion)

        logger.info(
            "Promotion created: %s → %s for api=%s tenant=%s",
            source_environment,
            target_environment,
            api_catalog.api_id,
            tenant_id,
        )

        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="promotion_created",
            resource_type="promotion",
            resource_id=str(promotion.id),
            user_id=user_id,
            details={
                "api_id": api_catalog.api_id,
                "source_environment": source_environment,
                "target_environment": target_environment,
                "source_deployment_id": str(source_deployment_id),
                "target_gateway_ids": [str(gateway_id) for gateway_id in target_gateway_ids],
            },
        )

        await notify_promotion_event(
            "promotion.pending_approval",
            {
                "tenant_id": tenant_id,
                "api_id": api_catalog.api_id,
                "source_environment": source_environment,
                "target_environment": target_environment,
                "requested_by": requested_by,
                "message": message,
                "console_url": f"https://console.{settings.BASE_DOMAIN}",
            },
        )

        return promotion

    async def _validate_gateway_aware_request(
        self,
        *,
        tenant_id: str,
        api_id: str,
        source_deployment_id: UUID,
        target_gateway_ids: list[UUID],
        source_environment: str,
        target_environment: str,
    ) -> APICatalog:
        """Validate that a promotion maps one synced source lane to equivalent target lanes."""
        if not target_gateway_ids:
            raise ValueError("Promotion requires at least one target gateway")

        source_deployment = await self.gw_deploy_repo.get_by_id(source_deployment_id)
        if not source_deployment:
            raise ValueError(f"Source gateway deployment {source_deployment_id} not found")

        result = await self.db.execute(
            select(APICatalog).where(
                APICatalog.id == source_deployment.api_catalog_id,
                APICatalog.deleted_at.is_(None),
            )
        )
        api_catalog = result.scalar_one_or_none()
        if not api_catalog:
            raise ValueError("Source gateway deployment API catalog entry not found")
        if api_catalog.tenant_id != tenant_id:
            raise ValueError("Source gateway deployment belongs to another tenant")
        if api_id not in {api_catalog.api_id, api_catalog.api_name, str(api_catalog.id)}:
            raise ValueError(f"Source gateway deployment belongs to API '{api_catalog.api_id}', not '{api_id}'")

        source_gateway = await self._get_gateway_or_raise(source_deployment.gateway_instance_id)
        self._validate_gateway_tenant(source_gateway, tenant_id)
        if not deployment_environment_matches(source_gateway.environment, source_environment):
            raise ValueError(
                f"Source gateway '{source_gateway.name}' is in environment "
                f"'{source_gateway.environment}', not '{source_environment}'"
            )

        if self._wire_value(source_deployment.sync_status) != DeploymentSyncStatus.SYNCED.value:
            raise ValueError(
                f"Source deployment {source_deployment_id} is '{self._wire_value(source_deployment.sync_status)}'. "
                "Only synced gateway deployments can be promoted."
            )

        target_gateways = []
        for target_gateway_id in target_gateway_ids:
            gateway = await self._get_gateway_or_raise(target_gateway_id)
            self._validate_gateway_tenant(gateway, tenant_id)
            if getattr(gateway, "deleted_at", None):
                raise ValueError(f"Target gateway '{gateway.name}' has been deleted")
            if getattr(gateway, "enabled", True) is False:
                raise ValueError(f"Target gateway '{gateway.name}' is disabled")
            if not deployment_environment_matches(gateway.environment, target_environment):
                raise ValueError(
                    f"Target gateway '{gateway.name}' is in environment '{gateway.environment}', "
                    f"not '{target_environment}'"
                )
            target_gateways.append(gateway)

        source_family = self._target_gateway_type_value(source_gateway)
        source_topology = self._topology_value(source_gateway)
        for gateway in target_gateways:
            target_family = self._target_gateway_type_value(gateway)
            if target_family != source_family:
                raise ValueError(
                    f"Target gateway '{gateway.name}' is '{target_family}', but the source gateway "
                    f"'{source_gateway.name}' is '{source_family}'. Select an equivalent target gateway."
                )
            target_topology = self._topology_value(gateway)
            if source_topology and target_topology and target_topology != source_topology:
                raise ValueError(
                    f"Target gateway '{gateway.name}' topology is '{target_topology}', but the source gateway "
                    f"'{source_gateway.name}' topology is '{source_topology}'."
                )

        from ..services.deployment_orchestration_service import DeploymentOrchestrationService

        orchestration_svc = DeploymentOrchestrationService(self.db)
        preflight = await orchestration_svc.preflight_api_to_gateways(api_catalog.id, target_gateway_ids)
        failed = [result for result in preflight if not result.deployable]
        if failed:
            raise ValueError(orchestration_svc._format_preflight_failure(failed))

        return api_catalog

    async def _get_gateway_or_raise(self, gateway_id: UUID) -> GatewayInstance:
        result = await self.db.execute(select(GatewayInstance).where(GatewayInstance.id == gateway_id))
        gateway = result.scalar_one_or_none()
        if not gateway:
            raise ValueError(f"Gateway {gateway_id} not found")
        return gateway

    @staticmethod
    def _validate_gateway_tenant(gateway: GatewayInstance, tenant_id: str) -> None:
        gateway_tenant = getattr(gateway, "tenant_id", None)
        if gateway_tenant and gateway_tenant != tenant_id:
            raise ValueError(f"Gateway '{gateway.name}' belongs to another tenant")

    @staticmethod
    def _wire_value(value) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _target_gateway_type_value(gateway: GatewayInstance) -> str:
        return normalize_gateway_topology(
            gateway_type=gateway.gateway_type,
            mode=gateway.mode,
            source=gateway.source,
            deployment_mode=gateway.deployment_mode,
            target_gateway_type=gateway.target_gateway_type,
            topology=gateway.topology,
            health_details=gateway.health_details,
            endpoints=gateway.endpoints,
            base_url=gateway.base_url,
            public_url=gateway.public_url,
            ui_url=gateway.ui_url,
            target_gateway_url=gateway.target_gateway_url,
            tags=gateway.tags,
            name=gateway.name,
        ).target_gateway_type

    @staticmethod
    def _topology_value(gateway: GatewayInstance) -> str:
        return normalize_gateway_topology(
            gateway_type=gateway.gateway_type,
            mode=gateway.mode,
            source=gateway.source,
            deployment_mode=gateway.deployment_mode,
            target_gateway_type=gateway.target_gateway_type,
            topology=gateway.topology,
            health_details=gateway.health_details,
            endpoints=gateway.endpoints,
            base_url=gateway.base_url,
            public_url=gateway.public_url,
            ui_url=gateway.ui_url,
            target_gateway_url=gateway.target_gateway_url,
            tags=gateway.tags,
            name=gateway.name,
        ).topology

    async def get_promotion(self, tenant_id: str, promotion_id: UUID) -> Promotion | None:
        return await self.repo.get_by_id_and_tenant(promotion_id, tenant_id)

    async def list_promotions(
        self,
        tenant_id: str,
        api_id: str | None = None,
        status: str | None = None,
        target_environment: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Promotion], int]:
        return await self.repo.list_by_tenant(
            tenant_id=tenant_id,
            api_id=api_id,
            status=status,
            target_environment=target_environment,
            page=page,
            page_size=page_size,
        )

    async def approve_promotion(
        self,
        tenant_id: str,
        promotion_id: UUID,
        approved_by: str,
        user_id: str,
    ) -> Promotion:
        """Approve a pending promotion — transitions to 'promoting'."""
        promotion = await self.repo.get_by_id_and_tenant(promotion_id, tenant_id)
        if not promotion:
            raise ValueError(f"Promotion {promotion_id} not found")
        if promotion.status != PromotionStatus.PENDING.value:
            raise ValueError(
                f"Cannot approve promotion in status '{promotion.status}' "
                f"(expected '{PromotionStatus.PENDING.value}')"
            )
        # 4-eyes principle: self-approval blocked for production promotions
        if promotion.requested_by == approved_by and promotion.target_environment == "production":
            raise ValueError(
                "Cannot approve your own promotion to production (4-eyes principle). "
                "A different team member must approve production deployments."
            )

        target_gateway_ids = self._parse_target_gateway_ids(promotion.target_gateway_ids)
        if not target_gateway_ids:
            raise ValueError(
                "Cannot approve promotion without explicit target gateways. " "Create a new gateway-aware promotion."
            )

        # Trigger deployment before the state transition so no promotion can
        # enter PROMOTING without at least one linked GatewayDeployment.
        from ..services.deployment_orchestration_service import DeploymentOrchestrationService

        orchestration_svc = DeploymentOrchestrationService(self.db)
        deployments = await orchestration_svc.auto_deploy_on_promotion(
            api_id=promotion.api_id,
            tenant_id=tenant_id,
            target_environment=promotion.target_environment,
            approved_by=approved_by,
            promotion_id=promotion.id,
            gateway_ids=target_gateway_ids,
        )
        if not deployments:
            raise ValueError(
                "Promotion approval did not create any gateway deployment. " "Check the selected target gateways."
            )

        promotion.status = PromotionStatus.PROMOTING.value
        promotion.approved_by = approved_by
        promotion = await self.repo.update(promotion)

        logger.info(
            "Promotion %s approved by %s; %d gateway deployments linked",
            promotion_id,
            approved_by,
            len(deployments),
        )

        await kafka_service.publish(
            topic=Topics.DEPLOY_REQUESTS,
            event_type="promotion-approved",
            tenant_id=tenant_id,
            payload={
                "promotion_id": str(promotion.id),
                "api_id": promotion.api_id,
                "source_environment": promotion.source_environment,
                "target_environment": promotion.target_environment,
                "approved_by": approved_by,
                "target_gateway_ids": [str(gateway_id) for gateway_id in target_gateway_ids],
                "gateway_deployment_ids": [str(getattr(deployment, "id", deployment)) for deployment in deployments],
                "gateway_deployments_created": True,
            },
            user_id=user_id,
        )

        await notify_promotion_event(
            "promotion.approved",
            {
                "api_id": promotion.api_id,
                "source_environment": promotion.source_environment,
                "target_environment": promotion.target_environment,
                "approved_by": approved_by,
            },
        )

        return promotion

    @staticmethod
    def _parse_target_gateway_ids(raw_ids: object) -> list[UUID]:
        if not raw_ids:
            return []
        if not isinstance(raw_ids, list):
            raise ValueError("Promotion target gateways must be a list")
        try:
            return [value if isinstance(value, UUID) else UUID(str(value)) for value in raw_ids]
        except ValueError as exc:
            raise ValueError("Promotion contains an invalid target gateway ID") from exc

    async def complete_promotion(
        self,
        promotion_id: UUID,
        target_deployment_id: UUID | None = None,
        spec_diff: dict | None = None,
    ) -> Promotion:
        """Mark a promotion as successfully completed."""
        promotion = await self.repo.get_by_id(promotion_id)
        if not promotion:
            raise ValueError(f"Promotion {promotion_id} not found")
        if promotion.status != PromotionStatus.PROMOTING.value:
            raise ValueError(
                f"Cannot complete promotion in status '{promotion.status}' "
                f"(expected '{PromotionStatus.PROMOTING.value}')"
            )

        if target_deployment_id is None:
            linked_deployments = await self.gw_deploy_repo.list_by_promotion(promotion_id)
            if not linked_deployments:
                raise ValueError("Cannot complete promotion without linked gateway deployments")
            not_synced = [
                dep
                for dep in linked_deployments
                if self._wire_value(dep.sync_status) != DeploymentSyncStatus.SYNCED.value
            ]
            if not_synced:
                raise ValueError("Cannot complete promotion until all linked gateway deployments are synced")
            if len(linked_deployments) == 1:
                target_deployment_id = linked_deployments[0].id

        promotion.status = PromotionStatus.PROMOTED.value
        promotion.target_deployment_id = target_deployment_id
        promotion.spec_diff = spec_diff
        promotion.completed_at = datetime.utcnow()
        promotion = await self.repo.update(promotion)

        logger.info("Promotion %s completed", promotion_id)
        return promotion

    async def fail_promotion(self, promotion_id: UUID, reason: str) -> Promotion:
        """Mark a promotion as failed."""
        promotion = await self.repo.get_by_id(promotion_id)
        if not promotion:
            raise ValueError(f"Promotion {promotion_id} not found")

        promotion.status = PromotionStatus.FAILED.value
        promotion.completed_at = datetime.utcnow()
        promotion = await self.repo.update(promotion)

        logger.warning("Promotion %s failed: %s", promotion_id, reason)
        return promotion

    async def check_promotion_completion(self, promotion_id: UUID) -> None:
        """Check if all GatewayDeployments linked to a promotion are done.

        Called after each route-sync-ack. If all deployments are SYNCED,
        completes the promotion. If any are ERROR with none still PENDING/SYNCING,
        fails the promotion.
        """
        deployments = await self.gw_deploy_repo.list_by_promotion(promotion_id)
        if not deployments:
            return  # No deployments linked — nothing to do

        statuses = [d.sync_status for d in deployments]
        pending_or_syncing = [s for s in statuses if s in (DeploymentSyncStatus.PENDING, DeploymentSyncStatus.SYNCING)]

        if pending_or_syncing:
            return  # Still waiting for some gateways

        all_synced = all(s == DeploymentSyncStatus.SYNCED for s in statuses)
        if all_synced:
            try:
                await self.complete_promotion(promotion_id)
                logger.info("Promotion %s auto-completed: all %d deployments SYNCED", promotion_id, len(deployments))
            except ValueError:
                logger.info("Promotion %s already completed or not found", promotion_id)
        else:
            # At least one ERROR, no PENDING/SYNCING remaining
            error_count = sum(1 for s in statuses if s == DeploymentSyncStatus.ERROR)
            reason = f"Partial deployment failure: {error_count}/{len(deployments)} gateways failed"
            try:
                await self.fail_promotion(promotion_id, reason)
                logger.warning("Promotion %s auto-failed: %s", promotion_id, reason)
            except ValueError:
                logger.info("Promotion %s already failed or not found", promotion_id)

    async def rollback_promotion(
        self,
        tenant_id: str,
        promotion_id: UUID,
        message: str,
        requested_by: str,
        user_id: str,
    ) -> Promotion:
        """Rollback a completed promotion — creates a reverse promotion."""
        original = await self.repo.get_by_id_and_tenant(promotion_id, tenant_id)
        if not original:
            raise ValueError(f"Promotion {promotion_id} not found")
        if original.status != PromotionStatus.PROMOTED.value:
            raise ValueError(f"Can only rollback promoted promotions (current: {original.status})")

        original.status = PromotionStatus.ROLLED_BACK.value
        await self.repo.update(original)

        rollback = Promotion(
            tenant_id=tenant_id,
            api_id=original.api_id,
            source_environment=original.target_environment,
            target_environment=original.source_environment,
            status=PromotionStatus.PROMOTING.value,
            message=message,
            requested_by=requested_by,
        )
        rollback = await self.repo.create(rollback)

        logger.info("Promotion %s rolled back → new promotion %s", promotion_id, rollback.id)

        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="promotion_rolled_back",
            resource_type="promotion",
            resource_id=str(promotion_id),
            user_id=user_id,
            details={
                "rollback_promotion_id": str(rollback.id),
                "original_source": original.source_environment,
                "original_target": original.target_environment,
            },
        )

        await notify_promotion_event(
            "promotion.rolled_back",
            {
                "api_id": original.api_id,
                "source_environment": original.source_environment,
                "target_environment": original.target_environment,
                "requested_by": requested_by,
            },
        )

        return rollback

    async def get_diff(self, tenant_id: str, promotion_id: UUID) -> dict:
        """Get the spec diff for a promotion.

        Fetches actual deployment specs from source and target environments
        and returns them alongside the stored diff summary.
        """
        promotion = await self.repo.get_by_id_and_tenant(promotion_id, tenant_id)
        if not promotion:
            raise ValueError(f"Promotion {promotion_id} not found")

        source_spec = await self._get_deployment_spec(tenant_id, promotion.api_id, promotion.source_environment)
        target_spec = await self._get_deployment_spec(tenant_id, promotion.api_id, promotion.target_environment)

        return {
            "promotion_id": promotion.id,
            "source_environment": promotion.source_environment,
            "target_environment": promotion.target_environment,
            "source_spec": source_spec,
            "target_spec": target_spec,
            "diff_summary": promotion.spec_diff,
        }

    async def _get_deployment_spec(self, tenant_id: str, api_id: str, environment: str) -> dict | None:
        """Fetch the latest successful deployment spec for an environment."""
        deployment = await self.deployment_repo.get_latest_success(
            tenant_id=tenant_id, api_id=api_id, environment=environment
        )
        if not deployment:
            return None
        return {
            "deployment_id": str(deployment.id),
            "version": deployment.version,
            "spec_hash": deployment.spec_hash,
            "commit_sha": deployment.commit_sha,
            "deployed_by": deployment.deployed_by,
            "completed_at": deployment.completed_at.isoformat() if deployment.completed_at else None,
        }
