"""Catalog sync service for syncing API and MCP tools from GitLab to PostgreSQL (CAB-682)"""
import logging
from datetime import datetime, timezone
from typing import Optional, Set, Tuple
import yaml

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from src.models.catalog import APICatalog, MCPToolsCatalog, CatalogSyncStatus, SyncType, SyncStatus
from src.services.git_service import GitLabService

logger = logging.getLogger(__name__)


class CatalogSyncService:
    """Service for synchronizing catalog data from GitLab to PostgreSQL"""

    def __init__(self, db: AsyncSession, git_service: GitLabService):
        self.db = db
        self.git = git_service

    async def sync_all(self) -> CatalogSyncStatus:
        """Full sync of all tenants from GitLab"""
        sync_status = CatalogSyncStatus(
            sync_type=SyncType.FULL.value,
            status=SyncStatus.RUNNING.value
        )
        self.db.add(sync_status)
        await self.db.commit()
        await self.db.refresh(sync_status)

        try:
            items_synced = 0
            errors = []

            # Ensure GitLab connection
            if not self.git._project:
                await self.git.connect()

            # Get current commit SHA
            commit_sha = await self._get_current_commit_sha()

            # List all tenants
            tenants = await self._list_tenants()

            # Track seen APIs for soft-delete
            seen_apis: Set[Tuple[str, str]] = set()

            for tenant_id in tenants:
                try:
                    count = await self._sync_tenant_apis(tenant_id, commit_sha, seen_apis)
                    items_synced += count
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

            logger.info(f"Full sync completed: {items_synced} items synced")
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

    async def _sync_tenant_apis(
        self,
        tenant_id: str,
        commit_sha: Optional[str],
        seen_apis: Set[Tuple[str, str]]
    ) -> int:
        """Sync all APIs for a tenant"""
        count = 0

        try:
            # List APIs for tenant
            apis = await self.git.list_apis(tenant_id)

            for api in apis:
                try:
                    api_id = api.get("id", api.get("name", ""))
                    if not api_id:
                        continue

                    git_path = f"tenants/{tenant_id}/apis/{api_id}"
                    seen_apis.add((tenant_id, api_id))

                    # Try to load OpenAPI spec
                    openapi_spec = await self.git.get_api_openapi_spec(tenant_id, api_id)

                    # Determine portal_published from tags
                    tags = api.get("tags", [])
                    promotion_tags = {"portal:published", "promoted:portal", "portal-promoted"}
                    portal_published = any(
                        tag.lower() in promotion_tags
                        for tag in tags
                    )

                    # Upsert into database
                    stmt = insert(APICatalog).values(
                        tenant_id=tenant_id,
                        api_id=api_id,
                        api_name=api.get("name", api_id),
                        version=api.get("version"),
                        status=api.get("status", "active"),
                        category=api.get("category"),
                        tags=tags,
                        portal_published=portal_published,
                        metadata=api,
                        openapi_spec=openapi_spec,
                        git_path=git_path,
                        git_commit_sha=commit_sha,
                        synced_at=datetime.now(timezone.utc),
                        deleted_at=None  # Reactivate if was soft-deleted
                    ).on_conflict_do_update(
                        constraint='uq_api_catalog_tenant_api',
                        set_={
                            'api_name': api.get("name", api_id),
                            'version': api.get("version"),
                            'status': api.get("status", "active"),
                            'category': api.get("category"),
                            'tags': tags,
                            'portal_published': portal_published,
                            'metadata': api,
                            'openapi_spec': openapi_spec,
                            'git_commit_sha': commit_sha,
                            'synced_at': datetime.now(timezone.utc),
                            'deleted_at': None
                        }
                    )
                    await self.db.execute(stmt)
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
