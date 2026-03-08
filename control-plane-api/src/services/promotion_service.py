"""Promotion service — business logic for GitOps promotion flow (CAB-1706)"""

import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.promotion import Promotion, PromotionStatus, validate_promotion_chain
from ..repositories.deployment import DeploymentRepository
from ..repositories.promotion import PromotionRepository
from ..services.kafka_service import Topics, kafka_service

logger = logging.getLogger(__name__)


class PromotionService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PromotionRepository(db)
        self.deployment_repo = DeploymentRepository(db)

    async def create_promotion(
        self,
        tenant_id: str,
        api_id: str,
        source_environment: str,
        target_environment: str,
        message: str,
        requested_by: str,
        user_id: str,
    ) -> Promotion:
        """Create a new promotion request after validating the chain."""
        validate_promotion_chain(source_environment, target_environment)

        active = await self.repo.get_active_for_target(api_id, target_environment)
        if active:
            raise ValueError(
                f"Active promotion already exists for {api_id} → {target_environment} "
                f"(id={active.id}, status={active.status})"
            )

        promotion = Promotion(
            tenant_id=tenant_id,
            api_id=api_id,
            source_environment=source_environment,
            target_environment=target_environment,
            status=PromotionStatus.PENDING.value,
            message=message,
            requested_by=requested_by,
        )
        promotion = await self.repo.create(promotion)

        logger.info(
            "Promotion created: %s → %s for api=%s tenant=%s",
            source_environment,
            target_environment,
            api_id,
            tenant_id,
        )

        await kafka_service.emit_audit_event(
            tenant_id=tenant_id,
            action="promotion_created",
            resource_type="promotion",
            resource_id=str(promotion.id),
            user_id=user_id,
            details={
                "api_id": api_id,
                "source_environment": source_environment,
                "target_environment": target_environment,
            },
        )

        return promotion

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
        if (
            promotion.requested_by == approved_by
            and promotion.target_environment == "production"
        ):
            raise ValueError(
                "Cannot approve your own promotion to production (4-eyes principle). "
                "A different team member must approve production deployments."
            )

        promotion.status = PromotionStatus.PROMOTING.value
        promotion.approved_by = approved_by
        promotion = await self.repo.update(promotion)

        logger.info("Promotion %s approved by %s", promotion_id, approved_by)

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
            },
            user_id=user_id,
        )

        return promotion

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
