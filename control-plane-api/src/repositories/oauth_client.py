"""Repository for OAuth client CRUD operations (CAB-1483)."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.oauth_client import OAuthClient, OAuthClientStatus

logger = logging.getLogger(__name__)


class OAuthClientRepository:
    """Data access layer for oauth_clients table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, client: OAuthClient) -> OAuthClient:
        """Insert a new OAuth client record."""
        self.session.add(client)
        await self.session.flush()
        await self.session.refresh(client)
        return client

    async def get_by_id(self, client_id: str) -> OAuthClient | None:
        """Get an OAuth client by primary key."""
        stmt = select(OAuthClient).where(OAuthClient.id == client_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_keycloak_client_id(self, keycloak_client_id: str) -> OAuthClient | None:
        """Get an OAuth client by its Keycloak client_id."""
        stmt = select(OAuthClient).where(OAuthClient.keycloak_client_id == keycloak_client_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: str,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[OAuthClient], int]:
        """List OAuth clients for a tenant with pagination."""
        base = select(OAuthClient).where(OAuthClient.tenant_id == tenant_id)
        if status:
            base = base.where(OAuthClient.status == status)

        # Count
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar() or 0

        # Paginate
        stmt = base.order_by(OAuthClient.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def update_status(self, client_id: str, status: OAuthClientStatus) -> OAuthClient | None:
        """Update the status of an OAuth client (e.g., revoke)."""
        client = await self.get_by_id(client_id)
        if not client:
            return None
        client.status = status.value
        await self.session.flush()
        await self.session.refresh(client)
        return client

    async def delete(self, client_id: str) -> bool:
        """Soft-delete an OAuth client by setting status to REVOKED."""
        client = await self.get_by_id(client_id)
        if not client:
            return False
        client.status = OAuthClientStatus.REVOKED.value
        await self.session.flush()
        return True
