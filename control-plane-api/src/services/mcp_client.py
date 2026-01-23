"""MCP Client Service for External Server Communication.

Provides connectivity testing and tool discovery for external MCP servers.
Supports SSE and HTTP transports with various authentication methods.

Reference: External MCP Server Registration Plan
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional, List
from uuid import uuid4

import httpx

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Discovered MCP tool from external server."""
    name: str
    description: Optional[str] = None
    input_schema: Optional[dict] = None


@dataclass
class TestConnectionResult:
    """Result of test-connection operation."""
    success: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    server_info: Optional[dict] = None
    tools_discovered: Optional[int] = None


class MCPClientService:
    """Client for connecting to external MCP servers.

    Supports:
    - SSE transport (Claude Desktop compatible)
    - HTTP transport (JSON-RPC over HTTP)
    - Various auth methods (none, api_key, bearer_token, oauth2)
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout

    def _build_auth_headers(
        self,
        auth_type: str,
        credentials: Optional[dict],
    ) -> dict[str, str]:
        """Build authentication headers from credentials."""
        headers = {}

        if not credentials or auth_type == "none":
            return headers

        if auth_type == "api_key":
            api_key = credentials.get("api_key")
            if api_key:
                # Common API key header patterns
                headers["X-API-Key"] = api_key
                headers["Authorization"] = f"ApiKey {api_key}"

        elif auth_type == "bearer_token":
            token = credentials.get("bearer_token")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        elif auth_type == "oauth2":
            # For OAuth2, we assume the access_token has been obtained
            access_token = credentials.get("access_token")
            if access_token:
                headers["Authorization"] = f"Bearer {access_token}"

        return headers

    async def test_connection(
        self,
        base_url: str,
        transport: str,
        auth_type: str,
        credentials: Optional[dict] = None,
    ) -> TestConnectionResult:
        """Test connection to an external MCP server.

        Args:
            base_url: Server URL
            transport: Transport type (sse, http, websocket)
            auth_type: Authentication type
            credentials: Credentials dict from Vault

        Returns:
            TestConnectionResult with success status, latency, and discovered tools count
        """
        start_time = time.monotonic()

        try:
            if transport == "sse":
                result = await self._test_sse_connection(base_url, auth_type, credentials)
            elif transport == "http":
                result = await self._test_http_connection(base_url, auth_type, credentials)
            elif transport == "websocket":
                result = await self._test_websocket_connection(base_url, auth_type, credentials)
            else:
                return TestConnectionResult(
                    success=False,
                    error=f"Unsupported transport: {transport}"
                )

            latency_ms = int((time.monotonic() - start_time) * 1000)
            result.latency_ms = latency_ms
            return result

        except asyncio.TimeoutError:
            return TestConnectionResult(
                success=False,
                latency_ms=self.timeout * 1000,
                error=f"Connection timeout after {self.timeout}s"
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start_time) * 1000)
            logger.exception(f"Connection test failed: {e}")
            return TestConnectionResult(
                success=False,
                latency_ms=latency_ms,
                error=str(e)
            )

    async def _test_sse_connection(
        self,
        base_url: str,
        auth_type: str,
        credentials: Optional[dict],
    ) -> TestConnectionResult:
        """Test SSE transport connection."""
        headers = self._build_auth_headers(auth_type, credentials)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # For SSE, we try to establish connection and read initial events
            # Most MCP SSE servers respond to a GET request
            try:
                response = await client.get(
                    base_url,
                    headers={**headers, "Accept": "text/event-stream"},
                    follow_redirects=True,
                )

                if response.status_code == 200:
                    # Try to discover tools via a simple request
                    tools_count = await self._discover_tools_count_sse(
                        base_url, headers, client
                    )
                    return TestConnectionResult(
                        success=True,
                        server_info={"transport": "sse", "url": base_url},
                        tools_discovered=tools_count,
                    )
                else:
                    return TestConnectionResult(
                        success=False,
                        error=f"HTTP {response.status_code}: {response.text[:200]}"
                    )

            except httpx.ConnectError as e:
                return TestConnectionResult(
                    success=False,
                    error=f"Connection failed: {e}"
                )

    async def _test_http_connection(
        self,
        base_url: str,
        auth_type: str,
        credentials: Optional[dict],
    ) -> TestConnectionResult:
        """Test HTTP JSON-RPC transport connection."""
        headers = self._build_auth_headers(auth_type, credentials)
        headers["Content-Type"] = "application/json"

        # Send MCP initialize request
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "STOA Control Plane",
                    "version": "1.0.0"
                }
            },
            "id": str(uuid4())
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    base_url,
                    json=init_request,
                    headers=headers,
                    follow_redirects=True,
                )

                if response.status_code == 200:
                    result = response.json()
                    if "result" in result:
                        # Successfully initialized, try to list tools
                        tools_count = await self._discover_tools_count_http(
                            base_url, headers, client
                        )
                        return TestConnectionResult(
                            success=True,
                            server_info=result.get("result", {}).get("serverInfo"),
                            tools_discovered=tools_count,
                        )
                    elif "error" in result:
                        return TestConnectionResult(
                            success=False,
                            error=f"MCP error: {result['error']}"
                        )

                return TestConnectionResult(
                    success=False,
                    error=f"HTTP {response.status_code}: {response.text[:200]}"
                )

            except httpx.ConnectError as e:
                return TestConnectionResult(
                    success=False,
                    error=f"Connection failed: {e}"
                )

    async def _test_websocket_connection(
        self,
        base_url: str,
        auth_type: str,
        credentials: Optional[dict],
    ) -> TestConnectionResult:
        """Test WebSocket transport connection."""
        # WebSocket support would require additional library (websockets)
        # For MVP, return not implemented
        return TestConnectionResult(
            success=False,
            error="WebSocket transport not yet implemented"
        )

    async def _discover_tools_count_sse(
        self,
        base_url: str,
        headers: dict,
        client: httpx.AsyncClient,
    ) -> Optional[int]:
        """Try to discover tools count for SSE transport."""
        # SSE servers typically require bidirectional communication
        # For now, return None (unknown) - full discovery in list_tools
        return None

    async def _discover_tools_count_http(
        self,
        base_url: str,
        headers: dict,
        client: httpx.AsyncClient,
    ) -> Optional[int]:
        """Try to discover tools count for HTTP transport."""
        try:
            tools_request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": str(uuid4())
            }

            response = await client.post(
                base_url,
                json=tools_request,
                headers=headers,
            )

            if response.status_code == 200:
                result = response.json()
                tools = result.get("result", {}).get("tools", [])
                return len(tools)

        except Exception as e:
            logger.warning(f"Failed to discover tools count: {e}")

        return None

    async def list_tools(
        self,
        base_url: str,
        transport: str,
        auth_type: str,
        credentials: Optional[dict] = None,
    ) -> List[MCPTool]:
        """Discover tools from an external MCP server.

        Args:
            base_url: Server URL
            transport: Transport type (sse, http, websocket)
            auth_type: Authentication type
            credentials: Credentials dict from Vault

        Returns:
            List of discovered MCPTool objects
        """
        try:
            if transport == "http":
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
        credentials: Optional[dict],
    ) -> List[MCPTool]:
        """List tools via HTTP JSON-RPC transport."""
        headers = self._build_auth_headers(auth_type, credentials)
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            # First initialize
            init_request = {
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "STOA Control Plane",
                        "version": "1.0.0"
                    }
                },
                "id": str(uuid4())
            }

            init_response = await client.post(
                base_url,
                json=init_request,
                headers=headers,
            )

            if init_response.status_code != 200:
                raise Exception(f"Initialize failed: HTTP {init_response.status_code}")

            # Then list tools
            tools_request = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": str(uuid4())
            }

            tools_response = await client.post(
                base_url,
                json=tools_request,
                headers=headers,
            )

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
        credentials: Optional[dict],
    ) -> List[MCPTool]:
        """List tools via SSE transport.

        Note: Full SSE implementation requires the mcp SDK for proper
        bidirectional communication. This is a simplified version.
        """
        # For SSE servers like Linear, we may need the official mcp SDK
        # For now, try HTTP-style request as some SSE servers support both
        try:
            return await self._list_tools_http(base_url, auth_type, credentials)
        except Exception:
            # SSE servers typically require proper SSE client
            logger.warning(
                f"SSE tool discovery requires mcp SDK - returning empty list"
            )
            return []


# Global service instance
_mcp_client_service: Optional[MCPClientService] = None


def get_mcp_client_service() -> MCPClientService:
    """Get or create the global MCP client service instance."""
    global _mcp_client_service

    if _mcp_client_service is None:
        _mcp_client_service = MCPClientService(timeout=30)

    return _mcp_client_service
