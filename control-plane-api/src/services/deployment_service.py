"""Deployment service — business logic for deployment lifecycle (CAB-1353)"""
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.deployment import Deployment, DeploymentStatus
from src.repositories.deployment import DeploymentRepository
from src.services.kafka_service import Topics, kafka_service

logger = logging.getLogger(__name__)


class DeploymentService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DeploymentRepository(db)

    async def create_deployment(
        self, tenant_id: str, api_id: str, api_name: str,
        environment: str, version: str, deployed_by: str,
        user_id: str, gateway_id: str | None = None,
    ) -> Deployment:
        deployment = Deployment(
            tenant_id=tenant_id, api_id=api_id, api_name=api_name,
            environment=environment, version=version,
            status=DeploymentStatus.PENDING.value,
            deployed_by=deployed_by, gateway_id=gateway_id,
        )
        deployment = await self.repo.create(deployment)
        await kafka_service.publish(
            topic=Topics.DEPLOY_REQUESTS, event_type="deploy-request",
            tenant_id=tenant_id,
            payload={"deployment_id": str(deployment.id), "api_id": api_id,
                     "api_name": api_name, "environment": environment,
                     "version": version, "requested_by": deployed_by},
            user_id=user_id,
        )
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id, action="create_deployment",
            resource_type="deployment", resource_id=str(deployment.id),
            user_id=user_id,
            details={"api_id": api_id, "environment": environment, "version": version},
        )
        from src.services.webhook_service import emit_deployment_started
        await emit_deployment_started(self.db, deployment)
        return deployment

    async def rollback_deployment(
        self, tenant_id: str, deployment_id: UUID, target_version: str | None,
        deployed_by: str, user_id: str,
    ) -> Deployment:
        original = await self.repo.get_by_id_and_tenant(deployment_id, tenant_id)
        if not original:
            raise ValueError(f"Deployment {deployment_id} not found")
        if not target_version:
            prev = await self.repo.get_latest_success(tenant_id, original.api_id, original.environment)
            target_version = prev.version if prev else "previous"
        rollback = Deployment(
            tenant_id=tenant_id, api_id=original.api_id, api_name=original.api_name,
            environment=original.environment, version=target_version,
            status=DeploymentStatus.PENDING.value, deployed_by=deployed_by,
            rollback_of=deployment_id, rollback_version=target_version,
        )
        rollback = await self.repo.create(rollback)
        await kafka_service.publish(
            topic=Topics.DEPLOY_REQUESTS, event_type="rollback-request",
            tenant_id=tenant_id,
            payload={"rollback_id": str(rollback.id),
                     "original_deployment_id": str(deployment_id),
                     "target_version": target_version, "requested_by": deployed_by},
            user_id=user_id,
        )
        await kafka_service.emit_audit_event(
            tenant_id=tenant_id, action="rollback_deployment",
            resource_type="deployment", resource_id=str(deployment_id),
            user_id=user_id,
            details={"rollback_id": str(rollback.id), "target_version": target_version},
        )
        return rollback

    async def update_status(
        self, tenant_id: str, deployment_id: UUID, status: str,
        error_message: str | None = None, spec_hash: str | None = None,
        commit_sha: str | None = None, metadata: dict | None = None,
    ) -> Deployment:
        deployment = await self.repo.get_by_id_and_tenant(deployment_id, tenant_id)
        if not deployment:
            raise ValueError(f"Deployment {deployment_id} not found")
        deployment.status = status
        deployment.updated_at = datetime.utcnow()
        if error_message is not None:
            deployment.error_message = error_message
        if spec_hash is not None:
            deployment.spec_hash = spec_hash
        if commit_sha is not None:
            deployment.commit_sha = commit_sha
        if status in (DeploymentStatus.SUCCESS.value, DeploymentStatus.FAILED.value,
                      DeploymentStatus.ROLLED_BACK.value):
            deployment.completed_at = datetime.utcnow()
        if status == DeploymentStatus.IN_PROGRESS.value:
            deployment.attempt_count += 1
        deployment = await self.repo.update(deployment)
        if status == DeploymentStatus.SUCCESS.value:
            from src.services.webhook_service import emit_deployment_succeeded
            await emit_deployment_succeeded(self.db, deployment)
        elif status == DeploymentStatus.FAILED.value:
            from src.services.webhook_service import emit_deployment_failed
            await emit_deployment_failed(self.db, deployment)
        elif status == DeploymentStatus.ROLLED_BACK.value:
            from src.services.webhook_service import emit_deployment_rolled_back
            await emit_deployment_rolled_back(self.db, deployment)
        return deployment

    async def list_deployments(
        self, tenant_id: str, api_id: str | None = None,
        environment: str | None = None, status: str | None = None,
        page: int = 1, page_size: int = 50,
    ) -> tuple[list[Deployment], int]:
        return await self.repo.list_by_tenant(
            tenant_id, api_id=api_id, environment=environment,
            status=status, page=page, page_size=page_size,
        )

    async def get_deployment(self, tenant_id: str, deployment_id: UUID) -> Deployment | None:
        return await self.repo.get_by_id_and_tenant(deployment_id, tenant_id)

    async def get_environment_status(
        self, tenant_id: str, environment: str,
    ) -> tuple[list[Deployment], bool]:
        deployments = await self.repo.get_environment_summary(tenant_id, environment)
        healthy = all(d.status == DeploymentStatus.SUCCESS.value for d in deployments) if deployments else True
        return deployments, healthy
