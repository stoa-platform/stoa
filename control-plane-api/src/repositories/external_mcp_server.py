# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Repository for External MCP Server CRUD operations.

Reference: External MCP Server Registration Plan
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.orm import selectinload
from typing import Optional, List, Tuple
from datetime import datetime
from uuid import UUID

from src.models.external_mcp_server import (
    ExternalMCPServer,
    ExternalMCPServerTool,
    ExternalMCPHealthStatus,
)


class ExternalMCPServerRepository:
    """Repository for External MCP Server database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, server: ExternalMCPServer) -> ExternalMCPServer:
        """Create a new external MCP server."""
        self.session.add(server)
        await self.session.flush()
        await self.session.refresh(server)
        return server

    async def get_by_id(self, server_id: UUID) -> Optional[ExternalMCPServer]:
        """Get server by ID with tools."""
        result = await self.session.execute(
            select(ExternalMCPServer)
            .options(selectinload(ExternalMCPServer.tools))
            .where(ExternalMCPServer.id == server_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[ExternalMCPServer]:
        """Get server by name."""
        result = await self.session.execute(
            select(ExternalMCPServer)
            .options(selectinload(ExternalMCPServer.tools))
            .where(ExternalMCPServer.name == name)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        tenant_id: Optional[str] = None,
        enabled_only: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[ExternalMCPServer], int]:
        """List all external MCP servers (admin)."""
        query = select(ExternalMCPServer).options(selectinload(ExternalMCPServer.tools))

        # Filter by tenant (null = platform-wide servers included)
        if tenant_id:
            query = query.where(
                or_(
                    ExternalMCPServer.tenant_id.is_(None),  # Platform-wide servers
                    ExternalMCPServer.tenant_id == tenant_id,  # Tenant's own servers
                )
            )

        if enabled_only:
            query = query.where(ExternalMCPServer.enabled == True)  # noqa: E712

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Paginate
        query = query.order_by(ExternalMCPServer.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        servers = result.scalars().all()

        return list(servers), total

    async def list_enabled_with_tools(self) -> List[ExternalMCPServer]:
        """List all enabled servers with their tools (for MCP Gateway)."""
        result = await self.session.execute(
            select(ExternalMCPServer)
            .options(selectinload(ExternalMCPServer.tools))
            .where(ExternalMCPServer.enabled == True)  # noqa: E712
            .order_by(ExternalMCPServer.name)
        )
        return list(result.scalars().all())

    async def update(self, server: ExternalMCPServer) -> ExternalMCPServer:
        """Update an external MCP server."""
        server.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(server)
        return server

    async def delete(self, server: ExternalMCPServer) -> None:
        """Delete an external MCP server (cascades to tools)."""
        await self.session.delete(server)
        await self.session.flush()

    async def update_health_status(
        self,
        server_id: UUID,
        status: ExternalMCPHealthStatus,
        error: Optional[str] = None,
    ) -> Optional[ExternalMCPServer]:
        """Update server health status after test-connection."""
        server = await self.get_by_id(server_id)
        if not server:
            return None

        server.health_status = status
        server.last_health_check = datetime.utcnow()
        if status == ExternalMCPHealthStatus.UNHEALTHY:
            server.sync_error = error
        else:
            server.sync_error = None

        server.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(server)
        return server

    async def sync_tools(
        self,
        server_id: UUID,
        tools: List[ExternalMCPServerTool],
    ) -> Tuple[int, int]:
        """
        Sync tools from external server.

        Returns tuple of (synced_count, removed_count).
        """
        server = await self.get_by_id(server_id)
        if not server:
            return 0, 0

        now = datetime.utcnow()
        existing_tool_names = {tool.name for tool in server.tools}
        incoming_tool_names = {tool.name for tool in tools}

        # Remove tools no longer present
        tools_to_remove = [t for t in server.tools if t.name not in incoming_tool_names]
        removed_count = len(tools_to_remove)
        for tool in tools_to_remove:
            await self.session.delete(tool)

        # Add or update tools
        synced_count = 0
        for tool in tools:
            if tool.name in existing_tool_names:
                # Update existing tool
                existing_tool = next(t for t in server.tools if t.name == tool.name)
                existing_tool.namespaced_name = tool.namespaced_name
                existing_tool.display_name = tool.display_name
                existing_tool.description = tool.description
                existing_tool.input_schema = tool.input_schema
                existing_tool.synced_at = now
            else:
                # Add new tool
                tool.server_id = server_id
                tool.synced_at = now
                self.session.add(tool)
            synced_count += 1

        # Update server sync timestamp
        server.last_sync_at = now
        server.sync_error = None
        server.updated_at = now

        await self.session.flush()
        return synced_count, removed_count

    async def set_sync_error(
        self,
        server_id: UUID,
        error: str,
    ) -> Optional[ExternalMCPServer]:
        """Set sync error message on server."""
        server = await self.get_by_id(server_id)
        if not server:
            return None

        server.sync_error = error
        server.updated_at = datetime.utcnow()
        await self.session.flush()
        await self.session.refresh(server)
        return server


class ExternalMCPServerToolRepository:
    """Repository for External MCP Server Tool operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, tool_id: UUID) -> Optional[ExternalMCPServerTool]:
        """Get tool by ID."""
        result = await self.session.execute(
            select(ExternalMCPServerTool).where(ExternalMCPServerTool.id == tool_id)
        )
        return result.scalar_one_or_none()

    async def get_by_server_and_name(
        self,
        server_id: UUID,
        tool_name: str,
    ) -> Optional[ExternalMCPServerTool]:
        """Get tool by server ID and name."""
        result = await self.session.execute(
            select(ExternalMCPServerTool).where(
                and_(
                    ExternalMCPServerTool.server_id == server_id,
                    ExternalMCPServerTool.name == tool_name,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_by_server(
        self,
        server_id: UUID,
        enabled_only: bool = False,
    ) -> List[ExternalMCPServerTool]:
        """List tools for a server."""
        query = select(ExternalMCPServerTool).where(
            ExternalMCPServerTool.server_id == server_id
        )

        if enabled_only:
            query = query.where(ExternalMCPServerTool.enabled == True)  # noqa: E712

        query = query.order_by(ExternalMCPServerTool.name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_enabled(
        self,
        tool_id: UUID,
        enabled: bool,
    ) -> Optional[ExternalMCPServerTool]:
        """Enable or disable a tool."""
        tool = await self.get_by_id(tool_id)
        if not tool:
            return None

        tool.enabled = enabled
        await self.session.flush()
        await self.session.refresh(tool)
        return tool
