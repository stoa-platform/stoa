"""Repository for MCP Connector Template and OAuth Pending Session operations."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.external_mcp_server import ExternalMCPServer
from src.models.mcp_connector_template import MCPConnectorTemplate, OAuthPendingSession


class ConnectorTemplateRepository:
    """Repository for MCP Connector Template database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_all(self, enabled_only: bool = True) -> list[MCPConnectorTemplate]:
        """List all connector templates, ordered by sort_order."""
        query = select(MCPConnectorTemplate).order_by(MCPConnectorTemplate.sort_order)
        if enabled_only:
            query = query.where(MCPConnectorTemplate.enabled.is_(True))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_slug(self, slug: str) -> MCPConnectorTemplate | None:
        """Get a connector template by slug."""
        result = await self.session.execute(select(MCPConnectorTemplate).where(MCPConnectorTemplate.slug == slug))
        return result.scalar_one_or_none()

    async def get_by_id(self, template_id: UUID) -> MCPConnectorTemplate | None:
        """Get a connector template by ID."""
        result = await self.session.execute(select(MCPConnectorTemplate).where(MCPConnectorTemplate.id == template_id))
        return result.scalar_one_or_none()


class OAuthSessionRepository:
    """Repository for OAuth Pending Session operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, pending_session: OAuthPendingSession) -> OAuthPendingSession:
        """Create a new OAuth pending session."""
        self.session.add(pending_session)
        await self.session.flush()
        await self.session.refresh(pending_session)
        return pending_session

    async def get_by_state(self, state: str) -> OAuthPendingSession | None:
        """Get a pending session by state token."""
        result = await self.session.execute(select(OAuthPendingSession).where(OAuthPendingSession.state == state))
        return result.scalar_one_or_none()

    async def delete(self, pending_session: OAuthPendingSession) -> None:
        """Delete a pending session (single-use after callback)."""
        await self.session.delete(pending_session)
        await self.session.flush()

    async def cleanup_expired(self) -> int:
        """Delete expired sessions. Returns count of deleted rows."""
        now = datetime.utcnow()
        result = await self.session.execute(delete(OAuthPendingSession).where(OAuthPendingSession.expires_at < now))
        await self.session.flush()
        return result.rowcount


class ConnectorServerRepository:
    """Repository for querying ExternalMCPServer by connector_template_id."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_template_and_tenant(
        self,
        template_id: UUID,
        tenant_id: str | None,
    ) -> ExternalMCPServer | None:
        """Find an existing server connected via a specific template for a tenant."""
        conditions = [ExternalMCPServer.connector_template_id == template_id]
        if tenant_id is not None:
            conditions.append(ExternalMCPServer.tenant_id == tenant_id)
        else:
            conditions.append(ExternalMCPServer.tenant_id.is_(None))

        result = await self.session.execute(select(ExternalMCPServer).where(and_(*conditions)))
        return result.scalar_one_or_none()

    async def list_connected_template_ids(
        self,
        tenant_id: str | None,
    ) -> dict[UUID, tuple[UUID, str]]:
        """Get a mapping of connected template_id -> (server_id, health_status) for a tenant."""
        conditions = [ExternalMCPServer.connector_template_id.isnot(None)]
        if tenant_id is not None:
            conditions.append(ExternalMCPServer.tenant_id == tenant_id)
        else:
            conditions.append(ExternalMCPServer.tenant_id.is_(None))

        result = await self.session.execute(
            select(
                ExternalMCPServer.connector_template_id,
                ExternalMCPServer.id,
                ExternalMCPServer.health_status,
            ).where(and_(*conditions))
        )

        mapping: dict[UUID, tuple[UUID, str]] = {}
        for row in result.all():
            mapping[row[0]] = (row[1], row[2].value if hasattr(row[2], "value") else str(row[2]))
        return mapping
