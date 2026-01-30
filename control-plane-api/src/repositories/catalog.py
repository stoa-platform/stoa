"""Repository for API catalog CRUD operations (CAB-682)

Provides fast database-backed queries for the Portal API catalog
instead of real-time GitLab API calls.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.dialects.postgresql import JSONB
from typing import Optional, List, Tuple
from datetime import datetime

from src.models.catalog import APICatalog, MCPToolsCatalog, CatalogSyncStatus


class CatalogRepository:
    """Repository for cached API catalog database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_portal_apis(
        self,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
        tenant_id: Optional[str] = None,
        tenant_ids: Optional[List[str]] = None,
        include_unpublished: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[APICatalog], int]:
        """
        Get APIs from the catalog cache.

        By default, only returns portal-published APIs.
        Set include_unpublished=True to see all APIs.

        Returns:
            Tuple of (list of APIs, total count)
        """
        # Base query - exclude soft-deleted
        query = select(APICatalog).where(APICatalog.deleted_at.is_(None))

        # Filter by portal_published unless including unpublished
        if not include_unpublished:
            query = query.where(APICatalog.portal_published == True)

        # Filter by category
        if category:
            query = query.where(APICatalog.category == category)

        # Filter by status
        if status:
            query = query.where(APICatalog.status == status)

        # Filter by tenant_id (single) or tenant_ids (multiple)
        if tenant_ids:
            query = query.where(APICatalog.tenant_id.in_(tenant_ids))
        elif tenant_id:
            query = query.where(APICatalog.tenant_id == tenant_id)

        # Filter by tags (any tag match using JSONB contains)
        if tags:
            # Match if any of the provided tags are in the API's tags array
            tag_conditions = [
                APICatalog.tags.contains([tag])
                for tag in tags
            ]
            query = query.where(or_(*tag_conditions))

        # Search filter (name, description, tags)
        if search:
            search_lower = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(APICatalog.api_name).like(search_lower),
                    func.lower(func.cast(APICatalog.api_metadata['description'], JSONB)).astext.like(search_lower),
                    APICatalog.api_id.ilike(search_lower),
                )
            )

        # Get total count before pagination
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Apply ordering and pagination
        query = query.order_by(APICatalog.api_name)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        apis = result.scalars().all()

        return list(apis), total

    async def get_api_by_id(
        self,
        tenant_id: str,
        api_id: str,
    ) -> Optional[APICatalog]:
        """Get a single API by tenant_id and api_id."""
        result = await self.session.execute(
            select(APICatalog)
            .where(APICatalog.tenant_id == tenant_id)
            .where(APICatalog.api_id == api_id)
            .where(APICatalog.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def find_api_by_name(
        self,
        api_name: str,
    ) -> Optional[APICatalog]:
        """
        Find an API by name across all tenants.

        Useful when api_id doesn't include tenant prefix.
        Returns the first matching published API.
        """
        result = await self.session.execute(
            select(APICatalog)
            .where(APICatalog.api_id == api_name)
            .where(APICatalog.deleted_at.is_(None))
            .where(APICatalog.portal_published == True)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_api_openapi_spec(
        self,
        tenant_id: str,
        api_id: str,
    ) -> Optional[dict]:
        """Get the OpenAPI spec for an API."""
        api = await self.get_api_by_id(tenant_id, api_id)
        return api.openapi_spec if api else None

    async def get_tenant_apis(
        self,
        tenant_id: str,
        include_unpublished: bool = False,
    ) -> List[APICatalog]:
        """Get all APIs for a specific tenant."""
        query = (
            select(APICatalog)
            .where(APICatalog.tenant_id == tenant_id)
            .where(APICatalog.deleted_at.is_(None))
        )

        if not include_unpublished:
            query = query.where(APICatalog.portal_published == True)

        query = query.order_by(APICatalog.api_name)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_categories(self) -> List[str]:
        """Get distinct categories from published APIs."""
        result = await self.session.execute(
            select(APICatalog.category)
            .where(APICatalog.portal_published == True)
            .where(APICatalog.deleted_at.is_(None))
            .where(APICatalog.category.isnot(None))
            .distinct()
            .order_by(APICatalog.category)
        )
        return [r[0] for r in result.fetchall() if r[0]]

    async def get_tags(self) -> List[str]:
        """Get distinct tags from published APIs."""
        # This query extracts unique tags from the JSONB array
        result = await self.session.execute(
            select(func.jsonb_array_elements_text(APICatalog.tags).label('tag'))
            .where(APICatalog.portal_published == True)
            .where(APICatalog.deleted_at.is_(None))
            .distinct()
        )
        return sorted([r[0] for r in result.fetchall() if r[0]])

    async def get_stats(self) -> dict:
        """Get catalog statistics."""
        # Total APIs
        total_result = await self.session.execute(
            select(func.count(APICatalog.id))
            .where(APICatalog.deleted_at.is_(None))
        )
        total = total_result.scalar_one()

        # Published APIs
        published_result = await self.session.execute(
            select(func.count(APICatalog.id))
            .where(APICatalog.deleted_at.is_(None))
            .where(APICatalog.portal_published == True)
        )
        published = published_result.scalar_one()

        # By tenant
        tenant_result = await self.session.execute(
            select(APICatalog.tenant_id, func.count(APICatalog.id))
            .where(APICatalog.deleted_at.is_(None))
            .group_by(APICatalog.tenant_id)
        )
        by_tenant = {r[0]: r[1] for r in tenant_result.fetchall()}

        # By category
        category_result = await self.session.execute(
            select(APICatalog.category, func.count(APICatalog.id))
            .where(APICatalog.deleted_at.is_(None))
            .where(APICatalog.category.isnot(None))
            .group_by(APICatalog.category)
        )
        by_category = {r[0]: r[1] for r in category_result.fetchall()}

        return {
            "total_apis": total,
            "published_apis": published,
            "unpublished_apis": total - published,
            "by_tenant": by_tenant,
            "by_category": by_category,
        }


class MCPToolsCatalogRepository:
    """Repository for cached MCP tools catalog database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_tools(
        self,
        category: Optional[str] = None,
        tenant_id: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[MCPToolsCatalog], int]:
        """Get MCP tools from the catalog cache."""
        query = select(MCPToolsCatalog).where(MCPToolsCatalog.deleted_at.is_(None))

        if category:
            query = query.where(MCPToolsCatalog.category == category)

        if tenant_id:
            query = query.where(MCPToolsCatalog.tenant_id == tenant_id)

        if search:
            search_lower = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(MCPToolsCatalog.tool_name).like(search_lower),
                    func.lower(MCPToolsCatalog.display_name).like(search_lower),
                    func.lower(MCPToolsCatalog.description).like(search_lower),
                )
            )

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        # Order and paginate
        query = query.order_by(MCPToolsCatalog.display_name)
        query = query.offset((page - 1) * page_size).limit(page_size)

        result = await self.session.execute(query)
        tools = result.scalars().all()

        return list(tools), total

    async def get_tool_by_name(
        self,
        tenant_id: str,
        tool_name: str,
    ) -> Optional[MCPToolsCatalog]:
        """Get a single tool by tenant_id and tool_name."""
        result = await self.session.execute(
            select(MCPToolsCatalog)
            .where(MCPToolsCatalog.tenant_id == tenant_id)
            .where(MCPToolsCatalog.tool_name == tool_name)
            .where(MCPToolsCatalog.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_categories(self) -> List[str]:
        """Get distinct tool categories."""
        result = await self.session.execute(
            select(MCPToolsCatalog.category)
            .where(MCPToolsCatalog.deleted_at.is_(None))
            .where(MCPToolsCatalog.category.isnot(None))
            .distinct()
            .order_by(MCPToolsCatalog.category)
        )
        return [r[0] for r in result.fetchall() if r[0]]
