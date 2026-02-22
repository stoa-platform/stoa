"""Deployment log repository — data access layer (CAB-1420)."""
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.deployment_log import DeploymentLog

logger = logging.getLogger(__name__)


class DeploymentLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, log: DeploymentLog) -> DeploymentLog:
        self.db.add(log)
        await self.db.flush()
        await self.db.refresh(log)
        return log

    async def list_by_deployment(
        self,
        deployment_id: UUID,
        tenant_id: str,
        after_seq: int = 0,
        limit: int = 200,
    ) -> list[DeploymentLog]:
        result = await self.db.execute(
            select(DeploymentLog)
            .where(
                DeploymentLog.deployment_id == deployment_id,
                DeploymentLog.tenant_id == tenant_id,
                DeploymentLog.seq > after_seq,
            )
            .order_by(DeploymentLog.seq.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def next_seq(self, deployment_id: UUID) -> int:
        result = await self.db.execute(
            select(func.coalesce(func.max(DeploymentLog.seq), 0))
            .where(DeploymentLog.deployment_id == deployment_id)
        )
        return (result.scalar() or 0) + 1
