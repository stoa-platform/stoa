"""Promotion repository — data access layer (CAB-1706)"""
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.promotion import Promotion

logger = logging.getLogger(__name__)


class PromotionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, promotion: Promotion) -> Promotion:
        self.db.add(promotion)
        await self.db.flush()
        await self.db.refresh(promotion)
        return promotion

    async def get_by_id(self, promotion_id: UUID) -> Promotion | None:
        result = await self.db.execute(
            select(Promotion).where(Promotion.id == promotion_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant(
        self, promotion_id: UUID, tenant_id: str
    ) -> Promotion | None:
        result = await self.db.execute(
            select(Promotion).where(
                Promotion.id == promotion_id,
                Promotion.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def update(self, promotion: Promotion) -> Promotion:
        await self.db.flush()
        await self.db.refresh(promotion)
        return promotion

    async def list_by_tenant(
        self,
        tenant_id: str,
        api_id: str | None = None,
        status: str | None = None,
        target_environment: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Promotion], int]:
        query = select(Promotion).where(Promotion.tenant_id == tenant_id)
        count_query = (
            select(func.count())
            .select_from(Promotion)
            .where(Promotion.tenant_id == tenant_id)
        )

        if api_id:
            query = query.where(Promotion.api_id == api_id)
            count_query = count_query.where(Promotion.api_id == api_id)
        if status:
            query = query.where(Promotion.status == status)
            count_query = count_query.where(Promotion.status == status)
        if target_environment:
            query = query.where(
                Promotion.target_environment == target_environment
            )
            count_query = count_query.where(
                Promotion.target_environment == target_environment
            )

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = (
            query.order_by(Promotion.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def get_active_for_target(
        self, api_id: str, target_environment: str
    ) -> Promotion | None:
        """Check if there is an active (pending/promoting) promotion for this target."""
        result = await self.db.execute(
            select(Promotion).where(
                Promotion.api_id == api_id,
                Promotion.target_environment == target_environment,
                Promotion.status.in_(["pending", "promoting"]),
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_promoted(
        self, tenant_id: str, api_id: str, target_environment: str
    ) -> Promotion | None:
        """Get the most recent successful promotion to a target environment."""
        result = await self.db.execute(
            select(Promotion)
            .where(
                Promotion.tenant_id == tenant_id,
                Promotion.api_id == api_id,
                Promotion.target_environment == target_environment,
                Promotion.status == "promoted",
            )
            .order_by(Promotion.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
