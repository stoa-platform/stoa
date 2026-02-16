"""Tests for MCPClientService (CAB-1291)"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.mcp_client import (
    MCPClientService,
    MCPTool,
    TestConnectionResult,
    get_mcp_client_service,
)


# ── Dataclasses ──


class TestMCPTool:
    def test_defaults(self):
        tool = MCPTool(name="search")
        assert tool.name == "search"
        assert tool.description is None
        assert tool.input_schema is None

    def test_full(self):
        tool = MCPTool(name="query", description="Run query", input_schema={"type": "object"})
        assert tool.description == "Run query"
        assert tool.input_schema == {"type": "object"}


class TestTestConnectionResult:
    def test_defaults(self):
        r = TestConnectionResult(success=True)
        assert r.success is True
        assert r.latency_ms is None
        assert r.error is None
        assert r.server_info is None
        assert r.tools_discovered is None

    def test_failure(self):
        r = TestConnectionResult(success=False, error="timeout", latency_ms=5000)
        assert r.success is False
        assert r.error == "timeout"
        assert r.latency_ms == 5000


# ── _build_auth_headers ──


class TestBuildAuthHeaders:
    def setup_method(self):
        self.svc = MCPClientService()

    def test_none_auth(self):
        headers = self.svc._build_auth_headers("none", None)
        assert headers == {}

    def test_no_credentials(self):
        headers = self.svc._build_auth_headers("api_key", None)
        assert headers == {}

    def test_api_key(self):
        headers = self.svc._build_auth_headers("api_key", {"api_key": "secret123"})
        assert headers["X-API-Key"] == "secret123"
        assert headers["Authorization"] == "ApiKey secret123"

    def test_bearer_token(self):
        headers = self.svc._build_auth_headers("bearer_token", {"bearer_token": "tok"})
        assert headers["Authorization"] == "Bearer tok"

    def test_oauth2(self):
        headers = self.svc._build_auth_headers("oauth2", {"access_token": "at123"})
        assert headers["Authorization"] == "Bearer at123"

    def test_api_key_missing_value(self):
        headers = self.svc._build_auth_headers("api_key", {"other": "val"})
        assert headers == {}

    def test_bearer_missing_value(self):
        headers = self.svc._build_auth_headers("bearer_token", {})
        assert headers == {}

    def test_oauth2_missing_value(self):
        headers = self.svc._build_auth_headers("oauth2", {})
        assert headers == {}


# ── test_connection ──


class TestTestConnection:
    def setup_method(self):
        self.svc = MCPClientService(timeout=5)

    async def test_unsupported_transport(self):
        result = await self.svc.test_connection("http://host", "grpc", "none")
        assert result.success is False
        assert "Unsupported transport" in result.error

    async def test_websocket_not_implemented(self):
        result = await self.svc.test_connection("ws://host", "websocket", "none")
        assert result.success is False
        assert "not yet implemented" in result.error

    async def test_timeout_error(self):
        self.svc._test_sse_connection = AsyncMock(side_effect=TimeoutError())
        result = await self.svc.test_connection("http://host", "sse", "none")
        assert result.success is False
        assert "timeout" in result.error.lower()

    async def test_generic_exception(self):
        self.svc._test_http_connection = AsyncMock(side_effect=RuntimeError("boom"))
        result = await self.svc.test_connection("http://host", "http", "none")
        assert result.success is False
        assert "boom" in result.error

    async def test_sse_success(self):
        mock_result = TestConnectionResult(success=True, server_info={"transport": "sse"})
        self.svc._test_sse_connection = AsyncMock(return_value=mock_result)
        result = await self.svc.test_connection("http://host", "sse", "none")
        assert result.success is True
        assert result.latency_ms is not None

    async def test_http_success(self):
        mock_result = TestConnectionResult(success=True)
        self.svc._test_http_connection = AsyncMock(return_value=mock_result)
        result = await self.svc.test_connection("http://host", "http", "none")
        assert result.success is True


# ── _test_sse_connection ──


class TestSSEConnection:
    def setup_method(self):
        self.svc = MCPClientService(timeout=5)

    async def test_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            result = await self.svc._test_sse_connection("http://host/sse", "none", None)
        assert result.success is True

    async def test_non_200(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            result = await self.svc._test_sse_connection("http://host/sse", "none", None)
        assert result.success is False
        assert "401" in result.error

    async def test_connect_error(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            result = await self.svc._test_sse_connection("http://host/sse", "none", None)
        assert result.success is False
        assert "Connection failed" in result.error


# ── _test_http_connection ──


class TestHTTPConnection:
    def setup_method(self):
        self.svc = MCPClientService(timeout=5)

    async def test_success_with_result(self):
        init_response = MagicMock()
        init_response.status_code = 200
        init_response.json.return_value = {
            "result": {"serverInfo": {"name": "test-server"}}
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=init_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            result = await self.svc._test_http_connection("http://host/mcp", "none", None)
        assert result.success is True
        assert result.server_info == {"name": "test-server"}

    async def test_mcp_error_response(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"error": {"code": -1, "message": "bad request"}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            result = await self.svc._test_http_connection("http://host/mcp", "none", None)
        assert result.success is False
        assert "MCP error" in result.error

    async def test_non_200(self):
        response = MagicMock()
        response.status_code = 500
        response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            result = await self.svc._test_http_connection("http://host/mcp", "none", None)
        assert result.success is False
        assert "500" in result.error

    async def test_connect_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            result = await self.svc._test_http_connection("http://host/mcp", "none", None)
        assert result.success is False
        assert "Connection failed" in result.error


# ── _discover_tools_count ──


class TestDiscoverToolsCount:
    def setup_method(self):
        self.svc = MCPClientService()

    async def test_sse_returns_none(self):
        result = await self.svc._discover_tools_count_sse("http://host", {}, MagicMock())
        assert result is None

    async def test_http_success(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "result": {"tools": [{"name": "a"}, {"name": "b"}]}
        }
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=response)
        count = await self.svc._discover_tools_count_http("http://host", {}, mock_client)
        assert count == 2

    async def test_http_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("fail"))
        count = await self.svc._discover_tools_count_http("http://host", {}, mock_client)
        assert count is None

    async def test_http_non_200(self):
        response = MagicMock()
        response.status_code = 500
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=response)
        count = await self.svc._discover_tools_count_http("http://host", {}, mock_client)
        assert count is None


# ── list_tools ──


class TestListTools:
    def setup_method(self):
        self.svc = MCPClientService()

    async def test_unsupported_transport(self):
        tools = await self.svc.list_tools("http://host", "grpc", "none")
        assert tools == []

    async def test_http_transport(self):
        self.svc._list_tools_http = AsyncMock(return_value=[MCPTool(name="t1")])
        tools = await self.svc.list_tools("http://host", "http", "none")
        assert len(tools) == 1
        assert tools[0].name == "t1"

    async def test_sse_transport_falls_back(self):
        self.svc._list_tools_sse = AsyncMock(return_value=[])
        tools = await self.svc.list_tools("http://host", "sse", "none")
        assert tools == []

    async def test_exception_propagates(self):
        self.svc._list_tools_http = AsyncMock(side_effect=RuntimeError("fail"))
        with pytest.raises(RuntimeError, match="fail"):
            await self.svc.list_tools("http://host", "http", "none")


# ── _list_tools_http ──


class TestListToolsHTTP:
    def setup_method(self):
        self.svc = MCPClientService()

    async def test_success(self):
        init_resp = MagicMock()
        init_resp.status_code = 200
        init_resp.json.return_value = {"result": {}}

        tools_resp = MagicMock()
        tools_resp.status_code = 200
        tools_resp.json.return_value = {
            "result": {
                "tools": [
                    {"name": "search", "description": "Search docs", "inputSchema": {"type": "object"}},
                    {"name": "query"},
                ]
            }
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[init_resp, tools_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            tools = await self.svc._list_tools_http("http://host", "none", None)
        assert len(tools) == 2
        assert tools[0].name == "search"
        assert tools[0].description == "Search docs"
        assert tools[1].name == "query"

    async def test_init_failure(self):
        response = MagicMock()
        response.status_code = 500

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="Initialize failed"):
                await self.svc._list_tools_http("http://host", "none", None)

    async def test_tools_list_mcp_error(self):
        init_resp = MagicMock()
        init_resp.status_code = 200
        init_resp.json.return_value = {"result": {}}

        tools_resp = MagicMock()
        tools_resp.status_code = 200
        tools_resp.json.return_value = {"error": {"message": "not allowed"}}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[init_resp, tools_resp])
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("src.services.mcp_client.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(Exception, match="MCP error"):
                await self.svc._list_tools_http("http://host", "none", None)


# ── _list_tools_sse ──


class TestListToolsSSE:
    def setup_method(self):
        self.svc = MCPClientService()

    async def test_falls_back_to_http(self):
        self.svc._list_tools_http = AsyncMock(return_value=[MCPTool(name="t")])
        tools = await self.svc._list_tools_sse("http://host", "none", None)
        assert len(tools) == 1

    async def test_fallback_exception_returns_empty(self):
        self.svc._list_tools_http = AsyncMock(side_effect=Exception("fail"))
        tools = await self.svc._list_tools_sse("http://host", "none", None)
        assert tools == []


# ── Global service ──


class TestGetMCPClientService:
    def test_returns_instance(self):
        with patch("src.services.mcp_client._mcp_client_service", None):
            svc = get_mcp_client_service()
            assert isinstance(svc, MCPClientService)
            assert svc.timeout == 30
