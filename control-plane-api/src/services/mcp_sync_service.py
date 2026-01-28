# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""MCP Server GitOps Sync Service.

Synchronizes MCP Server definitions from GitLab to PostgreSQL.
GitLab is the source of truth for the MCP server catalog.
PostgreSQL stores runtime state for subscriptions.

This service implements one-way sync: GitLab -> Database.
"""
import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import uuid

from ..models.mcp_subscription import (
    MCPServer,
    MCPServerTool,
    MCPServerCategory,
    MCPServerStatus,
    MCPServerSyncStatus,
)
from .git_service import GitLabService

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a sync operation."""
    success: bool = True
    servers_synced: int = 0
    servers_created: int = 0
    servers_updated: int = 0
    servers_orphaned: int = 0
    tools_synced: int = 0
    errors: List[str] = field(default_factory=list)

    def add_error(self, error: str):
        self.errors.append(error)
        self.success = False


class MCPSyncService:
    """Synchronize MCP Servers from GitLab to PostgreSQL.

    GitLab is the source of truth for server definitions.
    Database is the runtime store for subscriptions and access control.
    """

    def __init__(self, git_service: GitLabService, db: AsyncSession):
        self.git_service = git_service
        self.db = db

    async def sync_server(
        self,
        tenant_id: str,
        server_name: str,
        commit_sha: Optional[str] = None
    ) -> Optional[MCPServer]:
        """
        Sync a single MCP server from GitLab to database.

        Steps:
        1. Read server.yaml from GitLab
        2. Parse and normalize the YAML data
        3. Upsert server in database (create or update)
        4. Sync tools (add new, update existing, mark removed as disabled)
        5. Update sync tracking fields

        Args:
            tenant_id: Tenant ID or "_platform" for platform servers
            server_name: Server name
            commit_sha: Optional commit SHA for tracking

        Returns:
            The synced MCPServer instance, or None if failed
        """
        logger.info(f"Syncing MCP server {server_name} for tenant {tenant_id}")

        try:
            # 1. Get server data from GitLab
            server_data = await self.git_service.get_mcp_server(tenant_id, server_name)
            if not server_data:
                logger.warning(f"MCP server {server_name} not found in GitLab")
                return None

            # 2. Find existing server in database
            result = await self.db.execute(
                select(MCPServer)
                .where(MCPServer.name == server_name)
                .options(selectinload(MCPServer.tools))
            )
            existing_server = result.scalar_one_or_none()

            # 3. Map category string to enum
            category_map = {
                "platform": MCPServerCategory.PLATFORM,
                "tenant": MCPServerCategory.TENANT,
                "public": MCPServerCategory.PUBLIC,
            }
            category = category_map.get(
                server_data.get("category", "public"),
                MCPServerCategory.PUBLIC
            )

            # 4. Map status string to enum
            status_map = {
                "active": MCPServerStatus.ACTIVE,
                "maintenance": MCPServerStatus.MAINTENANCE,
                "deprecated": MCPServerStatus.DEPRECATED,
            }
            status = status_map.get(
                server_data.get("status", "active"),
                MCPServerStatus.ACTIVE
            )

            if existing_server:
                # Update existing server
                existing_server.display_name = server_data.get("display_name", server_name)
                existing_server.description = server_data.get("description", "")
                existing_server.icon = server_data.get("icon")
                existing_server.category = category
                existing_server.tenant_id = tenant_id if tenant_id != "_platform" else None
                existing_server.visibility = server_data.get("visibility", {"public": True})
                existing_server.requires_approval = server_data.get("requires_approval", False)
                existing_server.auto_approve_roles = server_data.get("auto_approve_roles", [])
                existing_server.status = status
                existing_server.version = server_data.get("version", "1.0.0")
                existing_server.documentation_url = server_data.get("documentation_url")
                existing_server.git_path = server_data.get("git_path")
                existing_server.git_commit_sha = commit_sha
                existing_server.last_synced_at = datetime.utcnow()
                existing_server.sync_status = MCPServerSyncStatus.SYNCED
                existing_server.sync_error = None
                existing_server.updated_at = datetime.utcnow()

                server = existing_server
                logger.info(f"Updated existing MCP server {server_name}")
            else:
                # Create new server
                server = MCPServer(
                    id=uuid.uuid4(),
                    name=server_name,
                    display_name=server_data.get("display_name", server_name),
                    description=server_data.get("description", ""),
                    icon=server_data.get("icon"),
                    category=category,
                    tenant_id=tenant_id if tenant_id != "_platform" else None,
                    visibility=server_data.get("visibility", {"public": True}),
                    requires_approval=server_data.get("requires_approval", False),
                    auto_approve_roles=server_data.get("auto_approve_roles", []),
                    status=status,
                    version=server_data.get("version", "1.0.0"),
                    documentation_url=server_data.get("documentation_url"),
                    git_path=server_data.get("git_path"),
                    git_commit_sha=commit_sha,
                    last_synced_at=datetime.utcnow(),
                    sync_status=MCPServerSyncStatus.SYNCED,
                    sync_error=None,
                )
                self.db.add(server)
                logger.info(f"Created new MCP server {server_name}")

            # 5. Sync tools
            await self._sync_tools(server, server_data.get("tools", []))

            await self.db.commit()
            await self.db.refresh(server)

            return server

        except Exception as e:
            logger.error(f"Failed to sync MCP server {server_name}: {e}")
            await self.db.rollback()

            # Update sync status to error if server exists
            try:
                result = await self.db.execute(
                    select(MCPServer).where(MCPServer.name == server_name)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    existing.sync_status = MCPServerSyncStatus.ERROR
                    existing.sync_error = str(e)
                    await self.db.commit()
            except Exception:
                pass

            return None

    async def _sync_tools(self, server: MCPServer, tools_data: List[dict]) -> int:
        """
        Sync tools for a server.

        Strategy:
        - Add new tools that don't exist
        - Update existing tools
        - Mark tools not in GitLab as disabled (don't delete - may have subscriptions)

        Returns:
            Number of tools synced
        """
        # Build lookup of existing tools
        existing_tools = {tool.name: tool for tool in server.tools}
        seen_tool_names = set()
        tools_synced = 0

        for tool_data in tools_data:
            tool_name = tool_data.get("name")
            if not tool_name:
                continue

            seen_tool_names.add(tool_name)

            if tool_name in existing_tools:
                # Update existing tool
                tool = existing_tools[tool_name]
                tool.display_name = tool_data.get("display_name", tool_name)
                tool.description = tool_data.get("description", "")
                tool.input_schema = tool_data.get("input_schema", {})
                tool.enabled = tool_data.get("enabled", True)
                tool.requires_approval = tool_data.get("requires_approval", False)
                tool.endpoint = tool_data.get("endpoint")
                tool.method = tool_data.get("method", "POST")
                tool.timeout = tool_data.get("timeout", "30s")
                tool.rate_limit = tool_data.get("rate_limit", 60)
                tool.updated_at = datetime.utcnow()
            else:
                # Create new tool
                tool = MCPServerTool(
                    id=uuid.uuid4(),
                    server_id=server.id,
                    name=tool_name,
                    display_name=tool_data.get("display_name", tool_name),
                    description=tool_data.get("description", ""),
                    input_schema=tool_data.get("input_schema", {}),
                    enabled=tool_data.get("enabled", True),
                    requires_approval=tool_data.get("requires_approval", False),
                    endpoint=tool_data.get("endpoint"),
                    method=tool_data.get("method", "POST"),
                    timeout=tool_data.get("timeout", "30s"),
                    rate_limit=tool_data.get("rate_limit", 60),
                )
                self.db.add(tool)
                logger.debug(f"Created tool {tool_name} for server {server.name}")

            tools_synced += 1

        # Mark tools not in GitLab as disabled
        for tool_name, tool in existing_tools.items():
            if tool_name not in seen_tool_names:
                tool.enabled = False
                logger.debug(f"Disabled orphan tool {tool_name} for server {server.name}")

        return tools_synced

    async def sync_tenant_servers(self, tenant_id: str) -> SyncResult:
        """
        Sync all MCP servers for a tenant.

        Args:
            tenant_id: Tenant ID or "_platform" for platform servers

        Returns:
            SyncResult with statistics
        """
        result = SyncResult()
        logger.info(f"Syncing all MCP servers for tenant {tenant_id}")

        try:
            # Get all servers from GitLab
            servers = await self.git_service.list_mcp_servers(tenant_id)

            for server_data in servers:
                server_name = server_data.get("name")
                if not server_name:
                    continue

                try:
                    synced = await self.sync_server(tenant_id, server_name)
                    if synced:
                        result.servers_synced += 1
                except Exception as e:
                    result.add_error(f"Failed to sync {server_name}: {e}")

            logger.info(f"Synced {result.servers_synced} servers for tenant {tenant_id}")

        except Exception as e:
            result.add_error(f"Failed to list servers for {tenant_id}: {e}")

        return result

    async def sync_all_servers(self) -> SyncResult:
        """
        Full sync of all MCP servers from GitLab.

        Steps:
        1. Get all servers from GitLab (platform + all tenants)
        2. Sync each server
        3. Mark servers in DB but not in GitLab as orphans

        Returns:
            SyncResult with statistics
        """
        result = SyncResult()
        logger.info("Starting full MCP server sync from GitLab")

        git_server_paths = set()

        try:
            # 1. Get all servers from GitLab
            all_servers = await self.git_service.list_all_mcp_servers()

            for server_data in all_servers:
                server_name = server_data.get("name")
                tenant_id = server_data.get("tenant_id", "_platform")
                git_path = server_data.get("git_path")

                if not server_name:
                    continue

                if git_path:
                    git_server_paths.add(git_path)

                try:
                    # Check if server exists
                    existing = await self.db.execute(
                        select(MCPServer).where(MCPServer.name == server_name)
                    )
                    was_new = existing.scalar_one_or_none() is None

                    synced = await self.sync_server(tenant_id, server_name)
                    if synced:
                        result.servers_synced += 1
                        if was_new:
                            result.servers_created += 1
                        else:
                            result.servers_updated += 1
                except Exception as e:
                    result.add_error(f"Failed to sync {server_name}: {e}")

            # 2. Mark servers not in GitLab as orphans
            db_servers = await self.db.execute(
                select(MCPServer).where(MCPServer.git_path.isnot(None))
            )
            for server in db_servers.scalars():
                if server.git_path not in git_server_paths:
                    server.sync_status = MCPServerSyncStatus.ORPHAN
                    result.servers_orphaned += 1
                    logger.warning(f"Marked server {server.name} as orphan")

            await self.db.commit()

            logger.info(
                f"Full sync complete: {result.servers_synced} synced, "
                f"{result.servers_created} created, {result.servers_updated} updated, "
                f"{result.servers_orphaned} orphaned"
            )

        except Exception as e:
            result.add_error(f"Full sync failed: {e}")
            logger.error(f"Full MCP server sync failed: {e}")

        return result

    async def get_sync_status(self) -> dict:
        """
        Get current GitOps sync status.

        Returns:
            Dict with sync statistics and status
        """
        try:
            # Count servers by sync status
            result = await self.db.execute(select(MCPServer))
            servers = result.scalars().all()

            synced = sum(1 for s in servers if s.sync_status == MCPServerSyncStatus.SYNCED)
            pending = sum(1 for s in servers if s.sync_status == MCPServerSyncStatus.PENDING)
            error = sum(1 for s in servers if s.sync_status == MCPServerSyncStatus.ERROR)
            orphan = sum(1 for s in servers if s.sync_status == MCPServerSyncStatus.ORPHAN)
            no_status = sum(1 for s in servers if s.sync_status is None)

            # Find last sync time
            last_synced = None
            for s in servers:
                if s.last_synced_at:
                    if last_synced is None or s.last_synced_at > last_synced:
                        last_synced = s.last_synced_at

            return {
                "total_servers": len(servers),
                "synced": synced,
                "pending": pending,
                "error": error,
                "orphan": orphan,
                "untracked": no_status,
                "last_sync_at": last_synced.isoformat() if last_synced else None,
                "errors": [
                    {"server": s.name, "error": s.sync_error}
                    for s in servers
                    if s.sync_status == MCPServerSyncStatus.ERROR and s.sync_error
                ],
            }
        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return {"error": str(e)}
