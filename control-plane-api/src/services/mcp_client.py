"""MCP Client Service for External Server Communication.

Provides connectivity testing and tool discovery for external MCP servers.
Supports SSE (Server-Sent Events) and HTTP (Streamable HTTP) transports
with various authentication methods.

SSE Transport (MCP spec):
  1. GET /sse → SSE stream, first event is `endpoint` with POST URL
  2. POST to that endpoint with JSON-RPC messages
  3. Responses arrive as SSE `message` events on the original stream

HTTP Transport (Streamable HTTP, MCP 2025-03-26+):
  POST with JSON-RPC, response is JSON-RPC directly.
"""

import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import urljoin
from uuid import uuid4

import httpx
import httpx_sse

logger = logging.getLogger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"
CLIENT_INFO = {"name": "STOA Control Plane", "version": "1.0.0"}


@dataclass
class MCPTool:
    """Discovered MCP tool from external server."""

    name: str
    description: str | None = None
    input_schema: dict | None = None


@dataclass
class TestConnectionResult:
    """Result of test-connection operation."""

    success: bool
    latency_ms: int | None = None
    error: str | None = None
    server_info: dict | None = None
    tools_discovered: int | None = None


def _jsonrpc_request(method: str, params: dict | None = None) -> dict:
    """Build a JSON-RPC 2.0 request."""
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
        "id": str(uuid4()),
    }


class MCPClientService:
    """Client for connecting to external MCP servers.

    Supports:
    - SSE transport (MCP spec — bidirectional via SSE stream + POST)
    - HTTP transport (Streamable HTTP — JSON-RPC over POST)
    - Various auth methods (none, api_key, bearer_token, oauth2)
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _build_auth_headers(
        self,
        auth_type: str,
        credentials: dict | None,
    ) -> dict[str, str]:
        """Build authentication headers from credentials."""
        headers: dict[str, str] = {}

        if not credentials or auth_type == "none":
            return headers

        if auth_type == "api_key":
            api_key = credentials.get("api_key")
            if api_key:
                headers["X-API-Key"] = api_key
                headers["Authorization"] = f"ApiKey {api_key}"

        elif auth_type == "bearer_token":
            token = credentials.get("bearer_token")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        elif auth_type == "oauth2":
            access_token = credentials.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

        return headers

    # ── Test Connection ──────────────────────────────────────────────

    async def test_connection(
        self,
        base_url: str,
        transport: str,
        auth_type: str,
        credentials: dict | None = None,
    ) -> TestConnectionResult:
        """Test connection to an external MCP server."""
        start_time = time.monotonic()

        try:
            if transport == "sse":
                result = await self._test_sse_connection(base_url, auth_type, credentials)
            elif transport in ("http", "streamable_http"):
                result = await self._test_http_connection(base_url, auth_type, credentials)
            elif transport == "websocket":
                result = await self._test_websocket_connection(base_url, auth_type, credentials)
            else:
                return TestConnectionResult(success=False, error=f"Unsupported transport: {transport}")

            result.latency_ms = int((time.monotonic() - start_time) * 1000)
            return result

        except TimeoutError:
            return TestConnectionResult(
                success=False,
                latency_ms=self.timeout * 1000,
                error=f"Connection timeout after {self.timeout}s",
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.exception(f"Connection test failed: {e}")
            return TestConnectionResult(success=False, latency_ms=latency_ms, error=str(e))

    async def _test_sse_connection(
        self,
        base_url: str,
        auth_type: str,
        credentials: dict | None,
    ) -> TestConnectionResult:
        """Test SSE transport: connect, get endpoint, send initialize."""
        headers = self._build_auth_headers(auth_type, credentials)

        try:
            endpoint_url, server_info = await self._sse_initialize(base_url, headers)
            if endpoint_url:
                tools_count = await self._sse_tools_count(base_url, endpoint_url, headers)
                return TestConnectionResult(
                    success=True,
                    server_info=server_info or {"transport": "sse", "url": base_url},
                    tools_discovered=tools_count,
                )
            else:
                return TestConnectionResult(
                    success=False,
                    error="SSE: no endpoint event received",
                )
        except httpx.ConnectError as e:
            return TestConnectionResult(success=False, error=f"Connection failed: {e}")

    async def _test_http_connection(
        self,
        base_url: str,
        auth_type: str,
        credentials: dict | None,
    ) -> TestConnectionResult:
        """Test HTTP JSON-RPC transport connection."""
        headers = self._build_auth_headers(auth_type, credentials)
        headers["Content-Type"] = "application/json"

        init_request = _jsonrpc_request(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(base_url, json=init_request, headers=headers, follow_redirects=True)

                if response.status_code == 200:
                    result = response.json()
                    if "result" in result:
                        tools_count = await self._discover_tools_count_http(base_url, headers, client)
                        return TestConnectionResult(
                            success=True,
                            server_info=result.get("result", {}).get("serverInfo"),
                            tools_discovered=tools_count,
                        )
                    elif "error" in result:
                        return TestConnectionResult(success=False, error=f"MCP error: {result['error']}")

                return TestConnectionResult(success=False, error=f"HTTP {response.status_code}: {response.text[:200]}")

            except httpx.ConnectError as e:
                return TestConnectionResult(success=False, error=f"Connection failed: {e}")

    async def _test_websocket_connection(
        self,
        base_url: str,
        auth_type: str,
        credentials: dict | None,
    ) -> TestConnectionResult:
        """Test WebSocket transport connection."""
        return TestConnectionResult(success=False, error="WebSocket transport not yet implemented")

    # ── Tool Discovery ───────────────────────────────────────────────

    async def list_tools(
        self,
        base_url: str,
        transport: str,
        auth_type: str,
        credentials: dict | None = None,
    ) -> list[MCPTool]:
        """Discover tools from an external MCP server."""
        try:
            if transport in ("http", "streamable_http"):
                return await self._list_tools_http(base_url, auth_type, credentials)
            elif transport == "sse":
                return await self._list_tools_sse(base_url, auth_type, credentials)
            else:
                logger.warning(f"Tool discovery not supported for transport: {transport}")
                return []

        except Exception as e:
            logger.exception(f"Failed to list tools: {e}")
            raise

    async def _list_tools_http(
        self,
        base_url: str,
        auth_type: str,
        credentials: dict | None,
    ) -> list[MCPTool]:
        """List tools via HTTP JSON-RPC transport."""
        headers = self._build_auth_headers(auth_type, credentials)
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Initialize
            init_request = _jsonrpc_request(
                "initialize",
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": CLIENT_INFO,
                },
            )
            init_response = await client.post(base_url, json=init_request, headers=headers)
            if init_response.status_code != 200:
                raise Exception(f"Initialize failed: HTTP {init_response.status_code}")

            # List tools
            tools_request = _jsonrpc_request("tools/list")
            tools_response = await client.post(base_url, json=tools_request, headers=headers)

            if tools_response.status_code != 200:
                raise Exception(f"tools/list failed: HTTP {tools_response.status_code}")

            result = tools_response.json()
            if "error" in result:
                raise Exception(f"MCP error: {result['error']}")

            tools_data = result.get("result", {}).get("tools", [])
            return [
                MCPTool(
                    name=t.get("name", ""),
                    description=t.get("description"),
                    input_schema=t.get("inputSchema"),
                )
                for t in tools_data
            ]

    async def _list_tools_sse(
        self,
        base_url: str,
        auth_type: str,
        credentials: dict | None,
    ) -> list[MCPTool]:
        """List tools via SSE transport.

        MCP SSE protocol:
        1. GET base_url/sse → SSE stream
        2. First event type=endpoint → POST URL for JSON-RPC
        3. POST initialize to endpoint
        4. POST tools/list to endpoint
        5. Read response from SSE stream (event type=message)
        """
        headers = self._build_auth_headers(auth_type, credentials)

        sse_url = base_url.rstrip("/") + "/sse" if not base_url.endswith("/sse") else base_url

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # Step 1: Connect SSE and get endpoint
            endpoint_url = None
            async with httpx_sse.aconnect_sse(
                client,
                "GET",
                sse_url,
                headers={**headers, "Accept": "text/event-stream"},
            ) as event_source:
                # Read endpoint event
                async for event in event_source.aiter_sse():
                    if event.event == "endpoint":
                        endpoint_url = event.data.strip()
                        if not endpoint_url.startswith("http"):
                            endpoint_url = urljoin(base_url, endpoint_url)
                        break

                if not endpoint_url:
                    logger.warning("SSE: no endpoint event received from %s", sse_url)
                    return []

                # Step 2: Initialize via POST
                init_request = _jsonrpc_request(
                    "initialize",
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": CLIENT_INFO,
                    },
                )
                await client.post(endpoint_url, json=init_request, headers={"Content-Type": "application/json"})

                # Read initialize response from SSE
                init_response = None
                async for event in event_source.aiter_sse():
                    if event.event == "message":
                        init_response = json.loads(event.data)
                        break

                if not init_response or "result" not in init_response:
                    logger.warning("SSE: initialize failed — %s", init_response)
                    return []

                # Send initialized notification
                await client.post(
                    endpoint_url,
                    json={"jsonrpc": "2.0", "method": "notifications/initialized"},
                    headers={"Content-Type": "application/json"},
                )

                # Step 3: List tools via POST
                tools_request = _jsonrpc_request("tools/list")
                await client.post(endpoint_url, json=tools_request, headers={"Content-Type": "application/json"})

                # Read tools response from SSE
                async for event in event_source.aiter_sse():
                    if event.event == "message":
                        result = json.loads(event.data)
                        if "result" in result:
                            tools_data = result["result"].get("tools", [])
                            return [
                                MCPTool(
                                    name=t.get("name", ""),
                                    description=t.get("description"),
                                    input_schema=t.get("inputSchema"),
                                )
                                for t in tools_data
                            ]
                        elif "error" in result:
                            raise Exception(f"MCP error: {result['error']}")

        return []

    # ── Helpers ──────────────────────────────────────────────────────

    async def _sse_initialize(
        self,
        base_url: str,
        headers: dict,
    ) -> tuple[str | None, dict | None]:
        """Connect to SSE, get endpoint, send initialize. Returns (endpoint_url, server_info)."""
        sse_url = base_url.rstrip("/") + "/sse" if not base_url.endswith("/sse") else base_url

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with httpx_sse.aconnect_sse(
                    client,
                    "GET",
                    sse_url,
                    headers={**headers, "Accept": "text/event-stream"},
                ) as event_source:
                    # Get endpoint URL
                    endpoint_url = None
                    async for event in event_source.aiter_sse():
                        if event.event == "endpoint":
                            endpoint_url = event.data.strip()
                            if not endpoint_url.startswith("http"):
                                endpoint_url = urljoin(base_url, endpoint_url)
                            break

                    if not endpoint_url:
                        return None, None

                    # Send initialize
                    init_request = _jsonrpc_request(
                        "initialize",
                        {
                            "protocolVersion": MCP_PROTOCOL_VERSION,
                            "capabilities": {},
                            "clientInfo": CLIENT_INFO,
                        },
                    )
                    await client.post(endpoint_url, json=init_request, headers={"Content-Type": "application/json"})

                    # Read initialize response
                    async for event in event_source.aiter_sse():
                        if event.event == "message":
                            data = json.loads(event.data)
                            server_info = data.get("result", {}).get("serverInfo")
                            return endpoint_url, server_info

            except TimeoutError:
                logger.warning("SSE initialize timed out for %s", sse_url)
            except Exception as e:
                logger.warning("SSE initialize failed for %s: %s", sse_url, e)

        return None, None

    async def _sse_tools_count(
        self,
        base_url: str,
        endpoint_url: str,
        headers: dict,
    ) -> int | None:
        """Send tools/list via already-initialized SSE session. Returns count or None."""
        sse_url = base_url.rstrip("/") + "/sse" if not base_url.endswith("/sse") else base_url

        try:
            async with (
                httpx.AsyncClient(timeout=self.timeout) as client,
                httpx_sse.aconnect_sse(
                    client,
                    "GET",
                    sse_url,
                    headers={**headers, "Accept": "text/event-stream"},
                ) as event_source,
            ):
                # Wait for endpoint event (reconnection gives us a new session)
                ep = None
                async for event in event_source.aiter_sse():
                    if event.event == "endpoint":
                        ep = event.data.strip()
                        if not ep.startswith("http"):
                            ep = urljoin(base_url, ep)
                        break

                if not ep:
                    return None

                # Re-initialize on new session
                init_req = _jsonrpc_request(
                    "initialize",
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {},
                        "clientInfo": CLIENT_INFO,
                    },
                )
                await client.post(ep, json=init_req, headers={"Content-Type": "application/json"})

                # Read init response
                async for event in event_source.aiter_sse():
                    if event.event == "message":
                        break

                # Send tools/list
                tools_req = _jsonrpc_request("tools/list")
                await client.post(ep, json=tools_req, headers={"Content-Type": "application/json"})

                async for event in event_source.aiter_sse():
                    if event.event == "message":
                        data = json.loads(event.data)
                        tools = data.get("result", {}).get("tools", [])
                        return len(tools)
        except Exception as e:
            logger.warning("SSE tools count failed: %s", e)

        return None

    async def _discover_tools_count_http(
        self,
        base_url: str,
        headers: dict,
        client: httpx.AsyncClient,
    ) -> int | None:
        """Try to discover tools count for HTTP transport."""
        try:
            tools_request = _jsonrpc_request("tools/list")
            response = await client.post(base_url, json=tools_request, headers=headers)

            if response.status_code == 200:
                result = response.json()
                tools = result.get("result", {}).get("tools", [])
                return len(tools)

        except Exception as e:
            logger.warning(f"Failed to discover tools count: {e}")

        return None


# Global service instance
_mcp_client_service: MCPClientService | None = None


def get_mcp_client_service() -> MCPClientService:
    """Get or create the global MCP client service instance."""
    global _mcp_client_service

    if _mcp_client_service is None:
        _mcp_client_service = MCPClientService(timeout=30)

    return _mcp_client_service
