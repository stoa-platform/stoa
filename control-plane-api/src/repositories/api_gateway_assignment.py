"""Repository for API Gateway Assignment CRUD (CAB-1888)."""

import logging
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.api_gateway_assignment import ApiGatewayAssignment
from ..models.gateway_instance import GatewayInstance

logger = logging.getLogger(__name__)


class ApiGatewayAssignmentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, assignment: ApiGatewayAssignment) -> ApiGatewayAssignment:
        self.db.add(assignment)
        await self.db.flush()
        return assignment

    async def get_by_id(self, assignment_id: UUID) -> ApiGatewayAssignment | None:
        result = await self.db.execute(
            select(ApiGatewayAssignment).where(ApiGatewayAssignment.id == assignment_id)
        )
        return result.scalar_one_or_none()

    async def list_for_api(
        self,
        api_id: UUID,
        environment: str | None = None,
    ) -> list[dict]:
        """List assignments for an API, joined with gateway info."""
        query = (
            select(
                ApiGatewayAssignment,
                GatewayInstance.name.label("gateway_name"),
                GatewayInstance.display_name.label("gateway_display_name"),
                GatewayInstance.gateway_type.label("gateway_type"),
            )
            .join(GatewayInstance, ApiGatewayAssignment.gateway_id == GatewayInstance.id)
            .where(ApiGatewayAssignment.api_id == api_id)
            .order_by(ApiGatewayAssignment.environment, GatewayInstance.name)
        )
        if environment:
            query = query.where(ApiGatewayAssignment.environment == environment)

        result = await self.db.execute(query)
        rows = result.all()
        return [
            {
                "id": row.ApiGatewayAssignment.id,
                "api_id": row.ApiGatewayAssignment.api_id,
                "gateway_id": row.ApiGatewayAssignment.gateway_id,
                "environment": row.ApiGatewayAssignment.environment,
                "auto_deploy": row.ApiGatewayAssignment.auto_deploy,
                "created_at": row.ApiGatewayAssignment.created_at,
                "gateway_name": row.gateway_name,
                "gateway_display_name": row.gateway_display_name,
                "gateway_type": row.gateway_type.value if row.gateway_type else None,
            }
            for row in rows
        ]

    async def list_auto_deploy(
        self,
        api_id: UUID,
        environment: str,
    ) -> list[ApiGatewayAssignment]:
        """Get assignments with auto_deploy=True for an API/env."""
        result = await self.db.execute(
            select(ApiGatewayAssignment).where(
                ApiGatewayAssignment.api_id == api_id,
                ApiGatewayAssignment.environment == environment,
                ApiGatewayAssignment.auto_deploy.is_(True),
            )
        )
        return list(result.scalars().all())

    async def delete_by_id(self, assignment_id: UUID) -> bool:
        result = await self.db.execute(
            delete(ApiGatewayAssignment).where(ApiGatewayAssignment.id == assignment_id)
        )
        return result.rowcount > 0

    async def count_by_gateway(self, gateway_id: UUID) -> int:
        """Count APIs assigned to a gateway (for Gateway Overview)."""
        result = await self.db.execute(
            select(func.count()).where(ApiGatewayAssignment.gateway_id == gateway_id)
        )
        return result.scalar() or 0
