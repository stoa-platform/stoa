"""Catalog sync service for syncing API and MCP tools from GitLab to PostgreSQL (CAB-682, CAB-689)"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Set, Tuple
import yaml

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from src.models.catalog import APICatalog, MCPToolsCatalog, CatalogSyncStatus, SyncType, SyncStatus
from src.models.mcp_subscription import MCPServer, MCPServerTool, MCPServerStatus, MCPServerCategory, MCPServerSyncStatus
from src.services.git_service import GitLabService

logger = logging.getLogger(__name__)


class CatalogSyncService:
    """Service for synchronizing catalog data from GitLab to PostgreSQL"""

    def __init__(self, db: AsyncSession, git_service: GitLabService):
        self.db = db
        self.git = git_service

    async def sync_all(self) -> CatalogSyncStatus:
        """Full sync of all tenants from GitLab (CAB-688: parallel + progress logging)"""
        start_time = time.time()

        sync_status = CatalogSyncStatus(
            sync_type=SyncType.FULL.value,
            status=SyncStatus.RUNNING.value
        )
        self.db.add(sync_status)
        await self.db.commit()
        await self.db.refresh(sync_status)

        try:
            items_synced = 0
            apis_failed = 0
            errors = []

            # Ensure GitLab connection
            if not self.git._project:
                await self.git.connect()

            # Get current commit SHA
            commit_sha = await self._get_current_commit_sha()

            # CAB-688 Obligation #5: Single recursive tree call
            logger.info("Sync started: fetching full repository tree...")
            full_tree = await self.git.get_full_tree_recursive("tenants")
            tenant_apis = self.git.parse_tree_to_tenant_apis(full_tree)

            total_tenants = len(tenant_apis)
            total_apis = sum(len(apis) for apis in tenant_apis.values())
            logger.info(f"Found {total_tenants} tenants with {total_apis} APIs total")

            # Track seen APIs for soft-delete
            seen_apis: Set[Tuple[str, str]] = set()

            # CAB-688 Obligation #4: Progress logging
            for i, (tenant_id, api_ids) in enumerate(tenant_apis.items(), 1):
                logger.info(f"Sync progress: tenant {i}/{total_tenants} - {tenant_id} ({len(api_ids)} APIs)")

                try:
                    synced, failed = await self._sync_tenant_apis_parallel(
                        tenant_id, api_ids, commit_sha, seen_apis
                    )
                    items_synced += synced
                    apis_failed += failed
                except Exception as e:
                    logger.error(f"Error syncing tenant {tenant_id}: {e}")
                    errors.append({"tenant": tenant_id, "error": str(e)})

            # Soft-delete APIs no longer in Git
            deleted_count = await self._soft_delete_missing_apis(seen_apis)
            if deleted_count > 0:
                logger.info(f"Soft-deleted {deleted_count} APIs no longer in Git")

            # Mark sync as success
            sync_status.status = SyncStatus.SUCCESS.value
            sync_status.completed_at = datetime.now(timezone.utc)
            sync_status.items_synced = items_synced
            sync_status.errors = errors
            sync_status.git_commit_sha = commit_sha
            await self.db.commit()

            # CAB-689: Sync MCP servers alongside APIs
            logger.info("Syncing MCP Servers...")
            mcp_stats = await self.sync_mcp_servers()
            logger.info(f"MCP sync: {mcp_stats['servers_synced']} synced, {mcp_stats['servers_failed']} failed")

            # CAB-688 Obligation #6: Final summary
            elapsed = time.time() - start_time
            logger.info(
                f"Sync completed in {elapsed:.1f}s: "
                f"{items_synced} APIs synced, "
                f"{apis_failed} failed, "
                f"{mcp_stats['servers_synced']} MCP servers synced, "
                f"{len(errors)} tenant errors"
            )

            return sync_status

        except Exception as e:
            logger.error(f"Full sync failed: {e}")
            sync_status.status = SyncStatus.FAILED.value
            sync_status.completed_at = datetime.now(timezone.utc)
            sync_status.errors = [{"error": str(e)}]
            await self.db.commit()
            raise

    async def sync_tenant(self, tenant_id: str) -> CatalogSyncStatus:
        """Sync a single tenant from GitLab"""
        sync_status = CatalogSyncStatus(
            sync_type=SyncType.TENANT.value,
            status=SyncStatus.RUNNING.value
        )
        self.db.add(sync_status)
        await self.db.commit()
        await self.db.refresh(sync_status)

        try:
            # Ensure GitLab connection
            if not self.git._project:
                await self.git.connect()

            commit_sha = await self._get_current_commit_sha()
            seen_apis: Set[Tuple[str, str]] = set()

            items_synced = await self._sync_tenant_apis(tenant_id, commit_sha, seen_apis)

            # Mark sync as success
            sync_status.status = SyncStatus.SUCCESS.value
            sync_status.completed_at = datetime.now(timezone.utc)
            sync_status.items_synced = items_synced
            sync_status.git_commit_sha = commit_sha
            await self.db.commit()

            logger.info(f"Tenant sync completed for {tenant_id}: {items_synced} items synced")
            return sync_status

        except Exception as e:
            logger.error(f"Tenant sync failed for {tenant_id}: {e}")
            sync_status.status = SyncStatus.FAILED.value
            sync_status.completed_at = datetime.now(timezone.utc)
            sync_status.errors = [{"tenant": tenant_id, "error": str(e)}]
            await self.db.commit()
            raise

    async def _get_current_commit_sha(self) -> Optional[str]:
        """Get the current HEAD commit SHA from GitLab"""
        try:
            commits = self.git._project.commits.list(ref_name="main", per_page=1)
            if commits:
                return commits[0].id
        except Exception as e:
            logger.warning(f"Failed to get current commit SHA: {e}")
        return None

    async def _list_tenants(self) -> list[str]:
        """List all tenant IDs from GitLab"""
        try:
            tree = self.git._project.repository_tree(path="tenants", ref="main")
            return [
                item["name"]
                for item in tree
                if item["type"] == "tree"
            ]
        except Exception as e:
            logger.warning(f"Failed to list tenants: {e}")
            return []

    async def _sync_tenant_apis_parallel(
        self,
        tenant_id: str,
        api_ids: list[str],
        commit_sha: Optional[str],
        seen_apis: Set[Tuple[str, str]]
    ) -> Tuple[int, int]:
        """Sync all APIs for a tenant in parallel (CAB-688). Returns (synced, failed)."""
        # Parallel fetch all api.yaml and openapi specs
        apis = await self.git.list_apis_parallel(tenant_id)
        api_map = {api.get("id", api.get("name", "")): api for api in apis}

        openapi_specs = await self.git.get_all_openapi_specs_parallel(tenant_id, api_ids)

        synced = 0
        failed = 0

        for api_id in api_ids:
            api = api_map.get(api_id)
            if not api:
                failed += 1
                continue

            seen_apis.add((tenant_id, api_id))
            openapi_spec = openapi_specs.get(api_id)

            try:
                await self._upsert_api(tenant_id, api_id, api, openapi_spec, commit_sha)
                synced += 1
            except Exception as e:
                logger.warning(f"Failed to upsert API {tenant_id}/{api_id}: {e}")
                failed += 1

        await self.db.commit()
        return synced, failed

    async def _upsert_api(
        self,
        tenant_id: str,
        api_id: str,
        api: dict,
        openapi_spec: Optional[dict],
        commit_sha: Optional[str],
    ) -> None:
        """Upsert a single API into the catalog."""
        git_path = f"tenants/{tenant_id}/apis/{api_id}"
        tags = api.get("tags", [])
        promotion_tags = {"portal:published", "promoted:portal", "portal-promoted"}
        portal_published = any(tag.lower() in promotion_tags for tag in tags)

        stmt = insert(APICatalog).values(
            tenant_id=tenant_id,
            api_id=api_id,
            api_name=api.get("name", api_id),
            version=api.get("version"),
            status=api.get("status", "active"),
            category=api.get("category"),
            tags=tags,
            portal_published=portal_published,
            api_metadata=api,
            openapi_spec=openapi_spec,
            git_path=git_path,
            git_commit_sha=commit_sha,
            synced_at=datetime.now(timezone.utc),
            deleted_at=None
        ).on_conflict_do_update(
            constraint='uq_api_catalog_tenant_api',
            set_={
                APICatalog.api_name: api.get("name", api_id),
                APICatalog.version: api.get("version"),
                APICatalog.status: api.get("status", "active"),
                APICatalog.category: api.get("category"),
                APICatalog.tags: tags,
                APICatalog.portal_published: portal_published,
                APICatalog.api_metadata: api,
                APICatalog.openapi_spec: openapi_spec,
                APICatalog.git_commit_sha: commit_sha,
                APICatalog.synced_at: datetime.now(timezone.utc),
                APICatalog.deleted_at: None
            }
        )
        await self.db.execute(stmt)

    async def _sync_tenant_apis(
        self,
        tenant_id: str,
        commit_sha: Optional[str],
        seen_apis: Set[Tuple[str, str]]
    ) -> int:
        """Sync all APIs for a tenant (legacy sequential, used by sync_tenant)"""
        count = 0

        try:
            apis = await self.git.list_apis(tenant_id)

            for api in apis:
                try:
                    api_id = api.get("id", api.get("name", ""))
                    if not api_id:
                        continue

                    seen_apis.add((tenant_id, api_id))
                    openapi_spec = await self.git.get_api_openapi_spec(tenant_id, api_id)

                    await self._upsert_api(tenant_id, api_id, api, openapi_spec, commit_sha)
                    count += 1

                except Exception as e:
                    logger.error(f"Error syncing API {tenant_id}/{api_id}: {e}")

            await self.db.commit()

        except Exception as e:
            logger.error(f"Error listing APIs for tenant {tenant_id}: {e}")

        return count

    async def _soft_delete_missing_apis(self, seen_apis: Set[Tuple[str, str]]) -> int:
        """Mark APIs as deleted if they're no longer in Git"""
        # Get all active APIs in database
        result = await self.db.execute(
            select(APICatalog.tenant_id, APICatalog.api_id)
            .where(APICatalog.deleted_at.is_(None))
        )
        db_apis = set(result.fetchall())

        # APIs to soft-delete (in DB but not in Git)
        to_delete = db_apis - seen_apis

        if to_delete:
            for tenant_id, api_id in to_delete:
                await self.db.execute(
                    update(APICatalog)
                    .where(APICatalog.tenant_id == tenant_id)
                    .where(APICatalog.api_id == api_id)
                    .values(deleted_at=datetime.now(timezone.utc))
                )
            await self.db.commit()
            logger.info(f"Soft-deleted {len(to_delete)} APIs no longer in Git")

        return len(to_delete)

    async def get_last_sync_status(self) -> Optional[CatalogSyncStatus]:
        """Get the status of the last sync operation"""
        result = await self.db.execute(
            select(CatalogSyncStatus)
            .order_by(CatalogSyncStatus.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_sync_history(self, limit: int = 10) -> list[CatalogSyncStatus]:
        """Get recent sync history"""
        result = await self.db.execute(
            select(CatalogSyncStatus)
            .order_by(CatalogSyncStatus.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ============================================================
    # CAB-689: MCP Servers Sync (Git → PostgreSQL)
    # Obligation #1: Source = Git (not MCP Gateway)
    # Obligation #2: Pattern CAB-682 reused
    # ============================================================

    async def sync_mcp_servers(self, tenant_id: Optional[str] = None) -> dict:
        """
        Sync MCP servers from Git to PostgreSQL.
        CAB-689: Same pattern as sync_apis (CAB-682).

        Reads server.yaml from GitLab and upserts into the mcp_servers table.
        Supports both platform servers and tenant-specific servers.
        """
        start_time = time.time()
        stats = {
            "servers_synced": 0,
            "servers_failed": 0,
            "tenants_processed": 0,
            "errors": [],
        }

        # Ensure GitLab connection
        if not self.git._project:
            await self.git.connect()

        commit_sha = await self._get_current_commit_sha()

        # Determine which tenants to sync
        if tenant_id:
            tenants = [tenant_id]
        else:
            tenants = await self._list_tenants()
            # Also sync platform-level servers
            tenants = ["_platform"] + tenants

        total_tenants = len(tenants)
        logger.info(f"MCP Servers sync started: {total_tenants} tenants")

        seen_servers: Set[str] = set()

        for i, tid in enumerate(tenants, 1):
            logger.info(f"MCP sync progress: tenant {i}/{total_tenants} - {tid}")

            try:
                synced, failed = await self._sync_tenant_mcp_servers(
                    tid, commit_sha, seen_servers
                )
                stats["servers_synced"] += synced
                stats["servers_failed"] += failed
                stats["tenants_processed"] += 1
            except Exception as e:
                logger.error(f"Failed to sync MCP servers for tenant {tid}: {e}")
                stats["errors"].append({"tenant": tid, "error": str(e)})

        # Mark orphan servers (in DB but no longer in Git)
        if not tenant_id:
            orphan_count = await self._mark_orphan_mcp_servers(seen_servers)
            if orphan_count > 0:
                logger.info(f"Marked {orphan_count} MCP servers as orphan")
                stats["orphaned"] = orphan_count

        await self.db.commit()

        elapsed = time.time() - start_time
        stats["elapsed_seconds"] = round(elapsed, 2)

        logger.info(
            f"MCP Servers sync completed in {elapsed:.1f}s: "
            f"{stats['servers_synced']} synced, "
            f"{stats['servers_failed']} failed"
        )

        return stats

    async def _sync_tenant_mcp_servers(
        self,
        tenant_id: str,
        commit_sha: Optional[str],
        seen_servers: Set[str],
    ) -> Tuple[int, int]:
        """Sync MCP servers for a single tenant. Returns (synced, failed)."""
        synced = 0
        failed = 0

        try:
            servers = await self.git.list_mcp_servers(tenant_id)
        except Exception as e:
            logger.warning(f"Failed to list MCP servers for {tenant_id}: {e}")
            return 0, 0

        for server_data in servers:
            server_name = server_data.get("name", "")
            if not server_name:
                failed += 1
                continue

            seen_servers.add(server_name)

            try:
                await self._upsert_mcp_server(tenant_id, server_data, commit_sha)
                synced += 1
            except Exception as e:
                logger.warning(f"Failed to upsert MCP server {tenant_id}/{server_name}: {e}")
                failed += 1

        return synced, failed

    async def _upsert_mcp_server(
        self,
        tenant_id: str,
        server_data: dict,
        commit_sha: Optional[str],
    ) -> None:
        """Upsert a single MCP server into the mcp_servers table."""
        server_name = server_data["name"]
        now = datetime.now(timezone.utc)

        # Map category string to enum
        category_str = server_data.get("category", "public")
        category_map = {
            "platform": MCPServerCategory.PLATFORM,
            "tenant": MCPServerCategory.TENANT,
            "public": MCPServerCategory.PUBLIC,
        }
        category = category_map.get(category_str, MCPServerCategory.PUBLIC)

        # Check if server exists
        result = await self.db.execute(
            select(MCPServer).where(MCPServer.name == server_name)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing server
            existing.display_name = server_data.get("display_name", server_name)
            existing.description = server_data.get("description", "")
            existing.icon = server_data.get("icon", "")
            existing.category = category
            existing.tenant_id = tenant_id if tenant_id != "_platform" else None
            existing.visibility = server_data.get("visibility", {"public": True})
            existing.requires_approval = server_data.get("requires_approval", False)
            existing.auto_approve_roles = server_data.get("auto_approve_roles", [])
            existing.status = MCPServerStatus.ACTIVE
            existing.version = server_data.get("version", "1.0.0")
            existing.documentation_url = server_data.get("documentation_url", "")
            existing.git_path = server_data.get("git_path", "")
            existing.git_commit_sha = commit_sha
            existing.last_synced_at = now
            existing.sync_status = MCPServerSyncStatus.SYNCED
            existing.sync_error = None
            existing.updated_at = now

            # Sync tools
            await self._sync_server_tools(existing.id, server_data.get("tools", []))
        else:
            # Create new server
            import uuid
            server_id = uuid.uuid4()
            new_server = MCPServer(
                id=server_id,
                name=server_name,
                display_name=server_data.get("display_name", server_name),
                description=server_data.get("description", ""),
                icon=server_data.get("icon", ""),
                category=category,
                tenant_id=tenant_id if tenant_id != "_platform" else None,
                visibility=server_data.get("visibility", {"public": True}),
                requires_approval=server_data.get("requires_approval", False),
                auto_approve_roles=server_data.get("auto_approve_roles", []),
                status=MCPServerStatus.ACTIVE,
                version=server_data.get("version", "1.0.0"),
                documentation_url=server_data.get("documentation_url", ""),
                git_path=server_data.get("git_path", ""),
                git_commit_sha=commit_sha,
                last_synced_at=now,
                sync_status=MCPServerSyncStatus.SYNCED,
                created_at=now,
                updated_at=now,
            )
            self.db.add(new_server)
            await self.db.flush()

            # Sync tools
            await self._sync_server_tools(server_id, server_data.get("tools", []))

    async def _sync_server_tools(
        self,
        server_id,
        tools_data: list[dict],
    ) -> None:
        """Sync tools for a server — replace all tools with Git data."""
        # Delete existing tools
        result = await self.db.execute(
            select(MCPServerTool).where(MCPServerTool.server_id == server_id)
        )
        existing_tools = result.scalars().all()
        for tool in existing_tools:
            await self.db.delete(tool)

        # Insert tools from Git
        now = datetime.now(timezone.utc)
        for tool_data in tools_data:
            tool = MCPServerTool(
                server_id=server_id,
                name=tool_data.get("name", ""),
                display_name=tool_data.get("display_name", tool_data.get("name", "")),
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("input_schema"),
                enabled=tool_data.get("enabled", True),
                requires_approval=tool_data.get("requires_approval", False),
                endpoint=tool_data.get("endpoint"),
                method=tool_data.get("method", "POST"),
                timeout=tool_data.get("timeout", "30s"),
                rate_limit=tool_data.get("rate_limit", 60),
                created_at=now,
                updated_at=now,
            )
            self.db.add(tool)

    async def _mark_orphan_mcp_servers(self, seen_servers: Set[str]) -> int:
        """Mark MCP servers as orphan if they're no longer in Git."""
        result = await self.db.execute(
            select(MCPServer.name).where(
                MCPServer.sync_status != MCPServerSyncStatus.ORPHAN
            )
        )
        db_servers = {row[0] for row in result.fetchall()}

        orphans = db_servers - seen_servers
        if orphans:
            for server_name in orphans:
                await self.db.execute(
                    update(MCPServer)
                    .where(MCPServer.name == server_name)
                    .values(
                        sync_status=MCPServerSyncStatus.ORPHAN,
                        last_synced_at=datetime.now(timezone.utc),
                    )
                )

        return len(orphans)
