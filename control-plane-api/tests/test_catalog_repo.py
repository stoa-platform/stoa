"""Tests for CatalogRepository + MCPToolsCatalogRepository (CAB-1291)"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.repositories.catalog import (
    CatalogRepository,
    MCPToolsCatalogRepository,
    escape_like,
)


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _mock_api(**kwargs):
    api = MagicMock()
    api.id = kwargs.get("id", uuid4())
    api.tenant_id = kwargs.get("tenant_id", "acme")
    api.api_id = kwargs.get("api_id", "weather-api")
    api.api_name = kwargs.get("api_name", "Weather API")
    api.category = kwargs.get("category", "weather")
    api.status = kwargs.get("status", "active")
    api.portal_published = kwargs.get("portal_published", True)
    api.deleted_at = kwargs.get("deleted_at", None)
    api.tags = kwargs.get("tags", ["weather", "geo"])
    api.openapi_spec = kwargs.get("openapi_spec", {"openapi": "3.0.0"})
    api.api_metadata = kwargs.get("api_metadata", {"description": "Weather"})
    return api


def _mock_tool(**kwargs):
    tool = MagicMock()
    tool.id = kwargs.get("id", uuid4())
    tool.tenant_id = kwargs.get("tenant_id", "acme")
    tool.tool_name = kwargs.get("tool_name", "get_weather")
    tool.display_name = kwargs.get("display_name", "Get Weather")
    tool.description = kwargs.get("description", "Gets weather")
    tool.category = kwargs.get("category", "weather")
    tool.deleted_at = kwargs.get("deleted_at", None)
    return tool


# ── escape_like ──


class TestEscapeLike:
    def test_no_special(self):
        assert escape_like("hello") == "hello"

    def test_percent(self):
        assert escape_like("50%") == "50\\%"

    def test_underscore(self):
        assert escape_like("a_b") == "a\\_b"

    def test_backslash(self):
        assert escape_like("a\\b") == "a\\\\b"

    def test_all_special(self):
        assert escape_like("%_\\") == "\\%\\_\\\\"


# ── CatalogRepository.get_portal_apis ──


class TestGetPortalApis:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_api(), _mock_api()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        items, total = await repo.get_portal_apis()
        assert total == 2
        assert len(items) == 2

    async def test_with_category(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_api()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        items, total = await repo.get_portal_apis(category="weather")
        assert total == 1

    async def test_with_status(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        items, total = await repo.get_portal_apis(status="deprecated")
        assert total == 0

    async def test_with_tenant_id(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_api()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        items, total = await repo.get_portal_apis(tenant_id="acme")
        assert total == 1

    async def test_with_tenant_ids(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 3
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_api()] * 3
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        items, total = await repo.get_portal_apis(tenant_ids=["acme", "beta"])
        assert total == 3

    async def test_with_tags(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_api()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        items, total = await repo.get_portal_apis(tags=["weather"])
        assert total == 1

    async def test_with_search(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_api()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        items, total = await repo.get_portal_apis(search="weather")
        assert total == 1

    async def test_include_unpublished(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 5
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_api()] * 5
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        items, total = await repo.get_portal_apis(include_unpublished=True)
        assert total == 5

    async def test_empty_search(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 0
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = CatalogRepository(db)
        items, total = await repo.get_portal_apis(search="   ")
        assert total == 0


# ── CatalogRepository single lookups ──


class TestGetApiById:
    async def test_found(self):
        db = _mock_db()
        api = _mock_api()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = api
        db.execute = AsyncMock(return_value=mock_result)

        repo = CatalogRepository(db)
        result = await repo.get_api_by_id("acme", "weather-api")
        assert result is api

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = CatalogRepository(db)
        result = await repo.get_api_by_id("acme", "missing")
        assert result is None


class TestFindApiByName:
    async def test_found(self):
        db = _mock_db()
        api = _mock_api()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = api
        db.execute = AsyncMock(return_value=mock_result)

        repo = CatalogRepository(db)
        result = await repo.find_api_by_name("weather-api")
        assert result is api


class TestGetApiOpenapiSpec:
    async def test_found(self):
        db = _mock_db()
        api = _mock_api(openapi_spec={"openapi": "3.0.0"})
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = api
        db.execute = AsyncMock(return_value=mock_result)

        repo = CatalogRepository(db)
        result = await repo.get_api_openapi_spec("acme", "weather-api")
        assert result == {"openapi": "3.0.0"}

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = CatalogRepository(db)
        result = await repo.get_api_openapi_spec("acme", "missing")
        assert result is None


class TestGetTenantApis:
    async def test_returns_list(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_api()]
        db.execute = AsyncMock(return_value=mock_result)

        repo = CatalogRepository(db)
        result = await repo.get_tenant_apis("acme")
        assert len(result) == 1

    async def test_include_unpublished(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_api()] * 3
        db.execute = AsyncMock(return_value=mock_result)

        repo = CatalogRepository(db)
        result = await repo.get_tenant_apis("acme", include_unpublished=True)
        assert len(result) == 3


class TestGetCategories:
    async def test_returns_list(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("weather",), ("finance",), (None,)]
        db.execute = AsyncMock(return_value=mock_result)

        repo = CatalogRepository(db)
        result = await repo.get_categories()
        assert result == ["weather", "finance"]


class TestGetTags:
    async def test_returns_sorted(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("geo",), ("weather",), ("api",)]
        db.execute = AsyncMock(return_value=mock_result)

        repo = CatalogRepository(db)
        result = await repo.get_tags()
        assert result == ["api", "geo", "weather"]


class TestGetStats:
    async def test_returns_stats(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 10
        mock_published = MagicMock()
        mock_published.scalar_one.return_value = 8
        mock_tenant = MagicMock()
        mock_tenant.fetchall.return_value = [("acme", 6), ("beta", 4)]
        mock_category = MagicMock()
        mock_category.fetchall.return_value = [("weather", 5), ("finance", 5)]
        db.execute = AsyncMock(side_effect=[mock_total, mock_published, mock_tenant, mock_category])

        repo = CatalogRepository(db)
        stats = await repo.get_stats()
        assert stats["total_apis"] == 10
        assert stats["published_apis"] == 8
        assert stats["unpublished_apis"] == 2
        assert stats["by_tenant"]["acme"] == 6


# ── MCPToolsCatalogRepository ──


class TestMCPToolsGetTools:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_tool(), _mock_tool()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = MCPToolsCatalogRepository(db)
        items, total = await repo.get_tools()
        assert total == 2
        assert len(items) == 2

    async def test_with_category(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_tool()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = MCPToolsCatalogRepository(db)
        items, total = await repo.get_tools(category="weather")
        assert total == 1

    async def test_with_tenant(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_tool()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = MCPToolsCatalogRepository(db)
        items, total = await repo.get_tools(tenant_id="acme")
        assert total == 1

    async def test_with_search(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_tool()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = MCPToolsCatalogRepository(db)
        items, total = await repo.get_tools(search="weather")
        assert total == 1


class TestMCPToolsGetByName:
    async def test_found(self):
        db = _mock_db()
        tool = _mock_tool()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tool
        db.execute = AsyncMock(return_value=mock_result)

        repo = MCPToolsCatalogRepository(db)
        result = await repo.get_tool_by_name("acme", "get_weather")
        assert result is tool


class TestMCPToolsGetCategories:
    async def test_returns(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("weather",), ("finance",)]
        db.execute = AsyncMock(return_value=mock_result)

        repo = MCPToolsCatalogRepository(db)
        result = await repo.get_categories()
        assert result == ["weather", "finance"]
