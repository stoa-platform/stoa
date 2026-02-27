"""Unit tests for chat_tools.py — tool definitions and executor (CAB-1437 Phase 2)

Tests CHAT_TOOLS format, execute_tool dispatcher, platform_info, and error handling.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.chat_tools import CHAT_TOOLS, execute_tool

# ── CHAT_TOOLS definitions ──


class TestChatToolsFormat:
    """Verify all tool definitions conform to Anthropic tools schema."""

    def test_seven_tools_defined(self):
        assert len(CHAT_TOOLS) == 7

    @pytest.mark.parametrize("tool", CHAT_TOOLS, ids=[t["name"] for t in CHAT_TOOLS])
    def test_tool_has_required_fields(self, tool):
        assert "name" in tool
        assert "description" in tool
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"

    def test_tool_names(self):
        names = {t["name"] for t in CHAT_TOOLS}
        expected = {
            "list_tenants",
            "list_apis",
            "get_api_detail",
            "list_gateway_instances",
            "list_deployments",
            "platform_info",
            "search_docs",
        }
        assert names == expected

    def test_get_api_detail_requires_fields(self):
        tool = next(t for t in CHAT_TOOLS if t["name"] == "get_api_detail")
        assert "tenant_id" in tool["input_schema"]["required"]
        assert "api_id" in tool["input_schema"]["required"]

    def test_search_docs_requires_query(self):
        tool = next(t for t in CHAT_TOOLS if t["name"] == "search_docs")
        assert "query" in tool["input_schema"]["required"]


# ── platform_info ──


class TestPlatformInfo:
    async def test_returns_json(self):
        session = AsyncMock()
        result = await execute_tool("platform_info", {}, session)
        data = json.loads(result)
        assert data["name"] == "STOA Platform"
        assert data["status"] == "operational"
        assert "Universal API Contract (UAC)" in data["features"]


# ── execute_tool dispatcher ──


class TestExecuteToolDispatcher:
    @pytest.fixture()
    def session(self):
        return AsyncMock()

    async def test_unknown_tool(self, session):
        result = await execute_tool("nonexistent_tool", {}, session)
        data = json.loads(result)
        assert "error" in data
        assert "Unknown tool" in data["error"]

    @patch("src.services.chat_tools._exec_list_tenants", new_callable=AsyncMock)
    async def test_dispatches_list_tenants(self, mock_fn, session):
        mock_fn.return_value = "[]"
        result = await execute_tool("list_tenants", {}, session)
        mock_fn.assert_awaited_once_with(session)
        assert result == "[]"

    @patch("src.services.chat_tools._exec_list_apis", new_callable=AsyncMock)
    async def test_dispatches_list_apis(self, mock_fn, session):
        mock_fn.return_value = '{"total":0,"apis":[]}'
        inp = {"search": "test"}
        await execute_tool("list_apis", inp, session)
        mock_fn.assert_awaited_once_with(session, inp)

    @patch("src.services.chat_tools._exec_get_api_detail", new_callable=AsyncMock)
    async def test_dispatches_get_api_detail(self, mock_fn, session):
        mock_fn.return_value = '{"id":"1"}'
        inp = {"tenant_id": "t1", "api_id": "a1"}
        await execute_tool("get_api_detail", inp, session)
        mock_fn.assert_awaited_once_with(session, inp)

    @patch("src.services.chat_tools._exec_list_gateway_instances", new_callable=AsyncMock)
    async def test_dispatches_list_gateway_instances(self, mock_fn, session):
        mock_fn.return_value = '{"total":0,"instances":[]}'
        await execute_tool("list_gateway_instances", {}, session)
        mock_fn.assert_awaited_once_with(session)

    @patch("src.services.chat_tools._exec_list_deployments", new_callable=AsyncMock)
    async def test_dispatches_list_deployments(self, mock_fn, session):
        mock_fn.return_value = '{"total":0,"deployments":[]}'
        await execute_tool("list_deployments", {}, session)
        mock_fn.assert_awaited_once_with(session)

    @patch("src.services.chat_tools._exec_search_docs", new_callable=AsyncMock)
    async def test_dispatches_search_docs(self, mock_fn, session):
        mock_fn.return_value = '{"query":"q","total":0,"results":[]}'
        inp = {"query": "mcp"}
        await execute_tool("search_docs", inp, session)
        mock_fn.assert_awaited_once_with(inp)

    async def test_exception_returns_error_json(self, session):
        with patch("src.services.chat_tools._exec_list_tenants", new_callable=AsyncMock) as mock_fn:
            mock_fn.side_effect = RuntimeError("db crashed")
            result = await execute_tool("list_tenants", {}, session)
        data = json.loads(result)
        assert "error" in data
        assert "db crashed" in data["error"]


# ── Handler integration (mocked repos) ──


class TestListTenantsHandler:
    async def test_formats_tenant_list(self):
        tenant = MagicMock()
        tenant.id = "t1"
        tenant.name = "Acme"
        tenant.display_name = "Acme Corp"
        tenant.status = "active"

        session = AsyncMock()
        with patch("src.repositories.tenant.TenantRepository") as MockRepo:
            MockRepo.return_value.list_all = AsyncMock(return_value=[tenant])
            result = await execute_tool("list_tenants", {}, session)

        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["id"] == "t1"
        assert data[0]["name"] == "Acme"


class TestListApisHandler:
    async def test_formats_api_list(self):
        api = MagicMock()
        api.id = "api-1"
        api.name = "Pet Store"
        api.version = "1.0"
        api.status = "published"
        api.category = "test"
        api.tenant_id = "t1"

        session = AsyncMock()
        with patch("src.repositories.catalog.CatalogRepository") as MockRepo:
            MockRepo.return_value.get_portal_apis = AsyncMock(return_value=([api], 1))
            result = await execute_tool("list_apis", {"search": "pet"}, session)

        data = json.loads(result)
        assert data["total"] == 1
        assert data["apis"][0]["name"] == "Pet Store"


# ── Additional handler coverage (CAB-1538) ──


class TestGetApiDetailHandler:
    async def test_returns_api_detail(self):
        api = MagicMock()
        api.id = "api-42"
        api.name = "Payments API"
        api.version = "2.0"
        api.description = "Payment processing"
        api.status = "published"
        api.category = "finance"
        api.tenant_id = "tenant-1"
        api.base_url = "https://api.example.com/payments"

        session = AsyncMock()
        with patch("src.repositories.catalog.CatalogRepository") as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=api)
            result = await execute_tool(
                "get_api_detail",
                {"tenant_id": "tenant-1", "api_id": "api-42"},
                session,
            )

        data = json.loads(result)
        assert data["id"] == "api-42"
        assert data["name"] == "Payments API"
        assert data["version"] == "2.0"
        assert data["description"] == "Payment processing"
        assert data["status"] == "published"
        assert data["base_url"] == "https://api.example.com/payments"
        assert data["tenant_id"] == "tenant-1"

    async def test_api_not_found_returns_error(self):
        session = AsyncMock()
        with patch("src.repositories.catalog.CatalogRepository") as MockRepo:
            MockRepo.return_value.get_api_by_id = AsyncMock(return_value=None)
            result = await execute_tool(
                "get_api_detail",
                {"tenant_id": "tenant-1", "api_id": "missing-api"},
                session,
            )

        data = json.loads(result)
        assert "error" in data
        assert data["error"] == "API not found"

    async def test_calls_repo_with_correct_ids(self):
        session = AsyncMock()
        with patch("src.repositories.catalog.CatalogRepository") as MockRepo:
            mock_get = AsyncMock(return_value=None)
            MockRepo.return_value.get_api_by_id = mock_get
            await execute_tool(
                "get_api_detail",
                {"tenant_id": "t-xyz", "api_id": "a-abc"},
                session,
            )
        mock_get.assert_awaited_once_with(tenant_id="t-xyz", api_id="a-abc")


class TestListGatewayInstancesHandler:
    async def test_formats_instance_list(self):
        inst = MagicMock()
        inst.id = "gw-1"
        inst.name = "kong-prod"
        inst.display_name = "Kong Production"
        inst.gateway_type = "kong"
        inst.status = "online"
        inst.base_url = "https://kong.example.com"

        session = AsyncMock()
        with patch("src.repositories.gateway_instance.GatewayInstanceRepository") as MockRepo:
            MockRepo.return_value.list_all = AsyncMock(return_value=([inst], 1))
            result = await execute_tool("list_gateway_instances", {}, session)

        data = json.loads(result)
        assert data["total"] == 1
        assert len(data["instances"]) == 1
        assert data["instances"][0]["id"] == "gw-1"
        assert data["instances"][0]["name"] == "kong-prod"
        assert data["instances"][0]["display_name"] == "Kong Production"
        assert data["instances"][0]["gateway_type"] == "kong"
        assert data["instances"][0]["status"] == "online"
        assert data["instances"][0]["base_url"] == "https://kong.example.com"

    async def test_empty_instances(self):
        session = AsyncMock()
        with patch("src.repositories.gateway_instance.GatewayInstanceRepository") as MockRepo:
            MockRepo.return_value.list_all = AsyncMock(return_value=([], 0))
            result = await execute_tool("list_gateway_instances", {}, session)

        data = json.loads(result)
        assert data["total"] == 0
        assert data["instances"] == []

    async def test_calls_list_all_with_pagination_defaults(self):
        session = AsyncMock()
        with patch("src.repositories.gateway_instance.GatewayInstanceRepository") as MockRepo:
            mock_list = AsyncMock(return_value=([], 0))
            MockRepo.return_value.list_all = mock_list
            await execute_tool("list_gateway_instances", {}, session)
        mock_list.assert_awaited_once_with(page=1, page_size=50)


class TestListDeploymentsHandler:
    async def test_formats_deployment_list(self):
        dep = MagicMock()
        dep.id = "dep-1"
        dep.api_catalog_id = "api-99"
        dep.gateway_instance_id = "gw-1"
        dep.sync_status = "synced"

        session = AsyncMock()
        with patch("src.repositories.gateway_deployment.GatewayDeploymentRepository") as MockRepo:
            MockRepo.return_value.list_all = AsyncMock(return_value=([dep], 1))
            result = await execute_tool("list_deployments", {}, session)

        data = json.loads(result)
        assert data["total"] == 1
        assert len(data["deployments"]) == 1
        assert data["deployments"][0]["id"] == "dep-1"
        assert data["deployments"][0]["api_catalog_id"] == "api-99"
        assert data["deployments"][0]["gateway_instance_id"] == "gw-1"
        assert data["deployments"][0]["sync_status"] == "synced"

    async def test_empty_deployments(self):
        session = AsyncMock()
        with patch("src.repositories.gateway_deployment.GatewayDeploymentRepository") as MockRepo:
            MockRepo.return_value.list_all = AsyncMock(return_value=([], 0))
            result = await execute_tool("list_deployments", {}, session)

        data = json.loads(result)
        assert data["total"] == 0
        assert data["deployments"] == []

    async def test_calls_list_all_with_pagination_defaults(self):
        session = AsyncMock()
        with patch("src.repositories.gateway_deployment.GatewayDeploymentRepository") as MockRepo:
            mock_list = AsyncMock(return_value=([], 0))
            MockRepo.return_value.list_all = mock_list
            await execute_tool("list_deployments", {}, session)
        mock_list.assert_awaited_once_with(page=1, page_size=50)


class TestSearchDocsHandler:
    async def test_returns_search_results(self):
        result_item = MagicMock()
        result_item.title = "Getting Started with MCP"
        result_item.url = "https://docs.gostoa.dev/guides/mcp"
        result_item.snippet = "MCP protocol enables AI agents..."
        result_item.category = "guides"

        response = MagicMock()
        response.query = "mcp protocol"
        response.total = 1
        response.results = [result_item]

        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=response)

        session = AsyncMock()
        with patch(
            "src.routers.docs_search.get_docs_search_service", return_value=mock_service
        ):
            result = await execute_tool(
                "search_docs", {"query": "mcp protocol"}, session
            )

        data = json.loads(result)
        assert data["query"] == "mcp protocol"
        assert data["total"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Getting Started with MCP"
        assert data["results"][0]["url"] == "https://docs.gostoa.dev/guides/mcp"
        assert data["results"][0]["snippet"] == "MCP protocol enables AI agents..."
        assert data["results"][0]["category"] == "guides"

    async def test_empty_results(self):
        response = MagicMock()
        response.query = "nonexistent topic xyz"
        response.total = 0
        response.results = []

        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=response)

        session = AsyncMock()
        with patch(
            "src.routers.docs_search.get_docs_search_service", return_value=mock_service
        ):
            result = await execute_tool(
                "search_docs", {"query": "nonexistent topic xyz"}, session
            )

        data = json.loads(result)
        assert data["total"] == 0
        assert data["results"] == []

    async def test_limit_clamped_to_valid_range(self):
        response = MagicMock()
        response.query = "api"
        response.total = 0
        response.results = []

        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=response)

        session = AsyncMock()
        with patch(
            "src.routers.docs_search.get_docs_search_service", return_value=mock_service
        ):
            # limit=99 should be clamped to 20
            await execute_tool("search_docs", {"query": "api", "limit": 99}, session)

        mock_service.search.assert_awaited_once_with(query="api", limit=20)

    async def test_limit_defaults_to_five(self):
        response = MagicMock()
        response.query = "gateway"
        response.total = 0
        response.results = []

        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=response)

        session = AsyncMock()
        with patch(
            "src.routers.docs_search.get_docs_search_service", return_value=mock_service
        ):
            await execute_tool("search_docs", {"query": "gateway"}, session)

        mock_service.search.assert_awaited_once_with(query="gateway", limit=5)

    async def test_limit_clamped_minimum_to_one(self):
        response = MagicMock()
        response.query = "test"
        response.total = 0
        response.results = []

        mock_service = MagicMock()
        mock_service.search = AsyncMock(return_value=response)

        session = AsyncMock()
        with patch(
            "src.routers.docs_search.get_docs_search_service", return_value=mock_service
        ):
            # limit=0 should be clamped to 1
            await execute_tool("search_docs", {"query": "test", "limit": 0}, session)

        mock_service.search.assert_awaited_once_with(query="test", limit=1)
