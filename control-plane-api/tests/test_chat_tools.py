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
