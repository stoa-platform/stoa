"""SQLAlchemy persistence adapter for API lifecycle operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import APICatalog
from src.models.gateway_deployment import GatewayDeployment
from src.models.gateway_instance import GatewayInstance
from src.models.promotion import Promotion, PromotionStatus
from src.services.catalog_api_definition import environment_matches

from .ports import GatewayDeploymentSnapshot, GatewayDeploymentSyncStep, GatewayTarget, PromotionSnapshot


class SqlAlchemyApiLifecycleRepository:
    """Persistence adapter backed by the existing control-plane models."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_api_by_id(self, tenant_id: str, api_id: str) -> APICatalog | None:
        stmt = select(APICatalog).where(
            APICatalog.tenant_id == tenant_id,
            APICatalog.api_id == api_id,
            APICatalog.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_api_by_name_version(self, tenant_id: str, api_name: str, version: str) -> APICatalog | None:
        stmt = select(APICatalog).where(
            APICatalog.tenant_id == tenant_id,
            APICatalog.api_name == api_name,
            APICatalog.version == version,
            APICatalog.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_api_catalog(self, api: APICatalog) -> APICatalog:
        self.session.add(api)
        await self.session.flush()
        await self.session.refresh(api)
        return api

    async def save_api_catalog(self, api: APICatalog) -> APICatalog:
        self.session.add(api)
        await self.session.flush()
        await self.session.refresh(api)
        return api

    async def list_gateway_deployments(self, api_catalog_id: UUID) -> list[GatewayDeploymentSnapshot]:
        stmt = (
            select(GatewayDeployment, GatewayInstance)
            .join(GatewayInstance, GatewayDeployment.gateway_instance_id == GatewayInstance.id)
            .where(
                GatewayDeployment.api_catalog_id == api_catalog_id,
                GatewayInstance.deleted_at.is_(None),
            )
            .order_by(GatewayInstance.environment, GatewayInstance.name)
        )
        result = await self.session.execute(stmt)
        deployments: list[GatewayDeploymentSnapshot] = []
        for deployment, gateway in result.all():
            deployments.append(
                GatewayDeploymentSnapshot(
                    id=deployment.id,
                    environment=gateway.environment,
                    gateway_instance_id=gateway.id,
                    gateway_name=gateway.name,
                    gateway_type=str(gateway.gateway_type),
                    sync_status=str(deployment.sync_status),
                    desired_generation=deployment.desired_generation,
                    synced_generation=deployment.synced_generation,
                    gateway_resource_id=deployment.gateway_resource_id,
                    public_url=gateway.public_url,
                    sync_error=deployment.sync_error,
                    last_sync_attempt=deployment.last_sync_attempt,
                    last_sync_success=deployment.last_sync_success,
                    policy_sync_status=str(deployment.policy_sync_status) if deployment.policy_sync_status else None,
                    policy_sync_error=deployment.policy_sync_error,
                    sync_steps=_sync_steps_from_model(deployment.sync_steps),
                )
            )
        return deployments

    async def get_gateway_target(self, tenant_id: str, gateway_instance_id: UUID) -> GatewayTarget | None:
        stmt = select(GatewayInstance).where(
            GatewayInstance.id == gateway_instance_id,
            GatewayInstance.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        gateway = result.scalar_one_or_none()
        if not gateway:
            return None
        if gateway.tenant_id not in (None, tenant_id):
            return None
        return _gateway_target_from_model(gateway)

    async def list_gateway_targets(self, tenant_id: str, environment: str) -> list[GatewayTarget]:
        stmt = select(GatewayInstance).where(
            GatewayInstance.deleted_at.is_(None),
            GatewayInstance.enabled.is_(True),
        )
        result = await self.session.execute(stmt)
        gateways = [
            gateway
            for gateway in result.scalars().all()
            if gateway.tenant_id in (None, tenant_id) and environment_matches(gateway.environment, environment)
        ]
        return [_gateway_target_from_model(gateway) for gateway in gateways]

    async def get_gateway_deployment(self, api_catalog_id: UUID, gateway_instance_id: UUID) -> GatewayDeployment | None:
        stmt = select(GatewayDeployment).where(
            GatewayDeployment.api_catalog_id == api_catalog_id,
            GatewayDeployment.gateway_instance_id == gateway_instance_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_gateway_deployment(self, deployment: GatewayDeployment) -> GatewayDeployment:
        self.session.add(deployment)
        await self.session.flush()
        await self.session.refresh(deployment)
        return deployment

    async def save_gateway_deployment(self, deployment: GatewayDeployment) -> GatewayDeployment:
        self.session.add(deployment)
        await self.session.flush()
        await self.session.refresh(deployment)
        return deployment

    async def list_promotions(self, tenant_id: str, api_id: str) -> list[PromotionSnapshot]:
        stmt = (
            select(Promotion)
            .where(
                Promotion.tenant_id == tenant_id,
                Promotion.api_id == api_id,
            )
            .order_by(Promotion.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return [
            PromotionSnapshot(
                id=promotion.id,
                source_environment=promotion.source_environment,
                target_environment=promotion.target_environment,
                status=str(promotion.status),
                message=promotion.message,
                requested_by=promotion.requested_by,
                approved_by=promotion.approved_by,
                completed_at=promotion.completed_at,
            )
            for promotion in result.scalars().all()
        ]

    async def get_active_promotion(
        self,
        tenant_id: str,
        api_id: str,
        source_environment: str,
        target_environment: str,
    ) -> Promotion | None:
        stmt = (
            select(Promotion)
            .where(
                Promotion.tenant_id == tenant_id,
                Promotion.api_id == api_id,
                Promotion.source_environment == source_environment,
                Promotion.target_environment == target_environment,
                Promotion.status.in_([PromotionStatus.PENDING.value, PromotionStatus.PROMOTING.value]),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_promoted_promotion(
        self,
        tenant_id: str,
        api_id: str,
        source_environment: str,
        target_environment: str,
    ) -> Promotion | None:
        stmt = (
            select(Promotion)
            .where(
                Promotion.tenant_id == tenant_id,
                Promotion.api_id == api_id,
                Promotion.source_environment == source_environment,
                Promotion.target_environment == target_environment,
                Promotion.status == PromotionStatus.PROMOTED.value,
            )
            .order_by(Promotion.completed_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_promotion_for_target_deployment(
        self,
        tenant_id: str,
        api_id: str,
        target_environment: str,
        target_deployment_id: UUID,
    ) -> Promotion | None:
        stmt = (
            select(Promotion)
            .where(
                Promotion.tenant_id == tenant_id,
                Promotion.api_id == api_id,
                Promotion.target_environment == target_environment,
                Promotion.target_deployment_id == target_deployment_id,
                Promotion.status.in_([PromotionStatus.PENDING.value, PromotionStatus.PROMOTING.value]),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_promotion(self, promotion: Promotion) -> Promotion:
        self.session.add(promotion)
        await self.session.flush()
        await self.session.refresh(promotion)
        return promotion

    async def save_promotion(self, promotion: Promotion) -> Promotion:
        self.session.add(promotion)
        await self.session.flush()
        await self.session.refresh(promotion)
        return promotion


def _gateway_target_from_model(gateway: GatewayInstance) -> GatewayTarget:
    gateway_type = getattr(gateway.gateway_type, "value", gateway.gateway_type)
    return GatewayTarget(
        id=gateway.id,
        name=gateway.name,
        display_name=gateway.display_name,
        gateway_type=str(gateway_type),
        environment=gateway.environment,
        tenant_id=gateway.tenant_id,
        enabled=bool(gateway.enabled),
        public_url=gateway.public_url,
    )


def _sync_steps_from_model(raw_steps: object) -> list[GatewayDeploymentSyncStep]:
    if not isinstance(raw_steps, list):
        return []

    steps: list[GatewayDeploymentSyncStep] = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            continue
        name = raw_step.get("name")
        status = raw_step.get("status")
        if not isinstance(name, str) or not isinstance(status, str):
            continue
        detail = raw_step.get("detail")
        started_at = raw_step.get("started_at")
        completed_at = raw_step.get("completed_at")
        steps.append(
            GatewayDeploymentSyncStep(
                name=name,
                status=status,
                detail=detail if isinstance(detail, str) else None,
                started_at=started_at if isinstance(started_at, str) else None,
                completed_at=completed_at if isinstance(completed_at, str) else None,
            )
        )
    return steps
