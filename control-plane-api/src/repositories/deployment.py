"""Deployment repository — data access layer (CAB-1353)"""
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.deployment import Deployment, DeploymentStatus

logger = logging.getLogger(__name__)


class DeploymentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, deployment: Deployment) -> Deployment:
        self.db.add(deployment)
        await self.db.flush()
        await self.db.refresh(deployment)
        return deployment

    async def get_by_id(self, deployment_id: UUID) -> Deployment | None:
        result = await self.db.execute(
            select(Deployment).where(Deployment.id == deployment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant(
        self, deployment_id: UUID, tenant_id: str
    ) -> Deployment | None:
        result = await self.db.execute(
            select(Deployment).where(
                Deployment.id == deployment_id,
                Deployment.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def update(self, deployment: Deployment) -> Deployment:
        await self.db.flush()
        await self.db.refresh(deployment)
        return deployment

    async def list_by_tenant(
        self,
        tenant_id: str,
        api_id: str | None = None,
        environment: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Deployment], int]:
        query = select(Deployment).where(Deployment.tenant_id == tenant_id)
        count_query = select(func.count()).select_from(Deployment).where(
            Deployment.tenant_id == tenant_id
        )

        if api_id:
            query = query.where(Deployment.api_id == api_id)
            count_query = count_query.where(Deployment.api_id == api_id)
        if environment:
            query = query.where(Deployment.environment == environment)
            count_query = count_query.where(Deployment.environment == environment)
        if status:
            query = query.where(Deployment.status == status)
            count_query = count_query.where(Deployment.status == status)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Deployment.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get_latest_success(
        self, tenant_id: str, api_id: str, environment: str
    ) -> Deployment | None:
        result = await self.db.execute(
            select(Deployment)
            .where(
                Deployment.tenant_id == tenant_id,
                Deployment.api_id == api_id,
                Deployment.environment == environment,
                Deployment.status == DeploymentStatus.SUCCESS.value,
            )
            .order_by(Deployment.completed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_environment_summary(
        self, tenant_id: str, environment: str
    ) -> list[Deployment]:
        """Get latest deployment per api_id in an environment."""
        subquery = (
            select(
                Deployment.api_id,
                func.max(Deployment.created_at).label("latest"),
            )
            .where(
                Deployment.tenant_id == tenant_id,
                Deployment.environment == environment,
            )
            .group_by(Deployment.api_id)
            .subquery()
        )
        result = await self.db.execute(
            select(Deployment).join(
                subquery,
                (Deployment.api_id == subquery.c.api_id)
                & (Deployment.created_at == subquery.c.latest),
            )
        )
        return list(result.scalars().all())
