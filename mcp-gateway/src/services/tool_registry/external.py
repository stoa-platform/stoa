# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""External tool registration and invocation mixin.

Handles tools from external MCP servers (Linear, GitHub, Slack, etc.)
that STOA proxies with governance.
"""

import json
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from ...models import (
    ExternalTool,
    ToolResult,
    TextContent,
)

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)


class ExternalMixin:
    """Mixin providing external MCP server tool handling."""

    # Type hints for attributes from ToolRegistry
    _http_client: httpx.AsyncClient | None
    _external_tools: dict[str, ExternalTool]

    def register_external_tool(self, tool: ExternalTool) -> None:
        """Register an external MCP server tool.

        Args:
            tool: ExternalTool instance
        """
        key = tool.internal_key
        if key in self._external_tools:
            logger.info("Updating existing external tool", internal_key=key)
        self._external_tools[key] = tool
        logger.debug(
            "External tool registered",
            tool_name=tool.name,
            server_name=tool.server_name,
            internal_key=key,
        )

    def unregister_external_tool(self, name_or_key: str) -> bool:
        """Unregister an external tool by name or internal key.

        Args:
            name_or_key: Tool name or internal key

        Returns:
            True if tool was found and removed
        """
        # Try direct key lookup
        if name_or_key in self._external_tools:
            del self._external_tools[name_or_key]
            logger.debug("External tool unregistered", key=name_or_key)
            return True

        # Try finding by name
        for key, tool in list(self._external_tools.items()):
            if tool.name == name_or_key:
                del self._external_tools[key]
                logger.debug("External tool unregistered (by name)", name=name_or_key)
                return True

        return False

    def get_external_tool(self, name: str) -> ExternalTool | None:
        """Get an external tool by name.

        Args:
            name: Tool name (namespaced, e.g., linear__create_issue)

        Returns:
            ExternalTool if found, None otherwise
        """
        # Search by name since external tools use namespaced names
        for tool in self._external_tools.values():
            if tool.name == name:
                return tool
        return None

    def list_external_tools(self) -> list[ExternalTool]:
        """List all registered external tools.

        Returns:
            List of ExternalTool instances
        """
        return list(self._external_tools.values())

    async def _invoke_external_tool(
        self,
        tool: ExternalTool,
        arguments: dict[str, Any],
        user_token: str | None = None,
    ) -> ToolResult:
        """Invoke an external MCP server tool.

        Routes the invocation to the external MCP server using the
        appropriate transport (SSE, HTTP, WebSocket).

        Args:
            tool: ExternalTool instance
            arguments: Tool invocation arguments
            user_token: User JWT (used for audit, not passed to external server)

        Returns:
            ToolResult with response from external server
        """
        if not self._http_client:
            return ToolResult(
                content=[TextContent(text="HTTP client not initialized")],
                is_error=True,
            )

        transport = tool.transport.lower()

        if transport == "sse":
            return await self._invoke_external_sse(tool, arguments)
        elif transport == "http":
            return await self._invoke_external_http(tool, arguments)
        elif transport == "websocket":
            return ToolResult(
                content=[TextContent(text="WebSocket transport not yet implemented")],
                is_error=True,
            )
        else:
            return ToolResult(
                content=[TextContent(text=f"Unknown transport: {transport}")],
                is_error=True,
            )

    async def _invoke_external_sse(
        self,
        tool: ExternalTool,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Invoke external tool via SSE transport (MCP protocol).

        Uses the MCP JSON-RPC protocol over HTTP with SSE for streaming.

        Args:
            tool: ExternalTool instance
            arguments: Tool invocation arguments

        Returns:
            ToolResult with response
        """
        try:
            # Build MCP JSON-RPC request for tools/call
            jsonrpc_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool.original_name,
                    "arguments": arguments,
                },
            }

            # Build headers with authentication
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            }

            # Add credentials based on auth type
            if tool.auth_type == "api_key" and tool.credentials:
                api_key = tool.credentials.get("api_key")
                header_name = tool.credentials.get("header_name", "X-API-Key")
                if api_key:
                    headers[header_name] = api_key

            elif tool.auth_type == "bearer_token" and tool.credentials:
                token = tool.credentials.get("token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"

            elif tool.auth_type == "oauth2" and tool.credentials:
                # OAuth2: Would need to exchange credentials for access token
                # For now, if access_token is cached, use it
                access_token = tool.credentials.get("access_token")
                if access_token:
                    headers["Authorization"] = f"Bearer {access_token}"

            # Make request to external MCP server
            # SSE servers typically accept POST to /messages or similar
            url = tool.base_url
            if not url.endswith("/messages"):
                url = url.rstrip("/") + "/messages" if "/sse" in url else url

            logger.debug(
                "Invoking external SSE tool",
                tool_name=tool.name,
                url=url,
                original_name=tool.original_name,
            )

            response = await self._http_client.post(
                url,
                json=jsonrpc_request,
                headers=headers,
                timeout=30.0,
            )

            if response.status_code >= 400:
                return ToolResult(
                    content=[TextContent(text=f"External server error: {response.status_code} - {response.text}")],
                    is_error=True,
                    backend_status=response.status_code,
                )

            # Parse MCP JSON-RPC response
            try:
                data = response.json()

                if "error" in data:
                    error_msg = data["error"].get("message", str(data["error"]))
                    return ToolResult(
                        content=[TextContent(text=f"External tool error: {error_msg}")],
                        is_error=True,
                    )

                result = data.get("result", {})
                content_items = result.get("content", [])

                # Convert MCP content to our format
                contents = []
                for item in content_items:
                    if item.get("type") == "text":
                        contents.append(TextContent(text=item.get("text", "")))
                    else:
                        # Handle other content types by converting to text
                        contents.append(TextContent(text=json.dumps(item)))

                if not contents:
                    contents = [TextContent(text=json.dumps(result))]

                return ToolResult(
                    content=contents,
                    is_error=result.get("isError", False),
                    backend_status=response.status_code,
                )

            except json.JSONDecodeError:
                # Return raw text if not JSON
                return ToolResult(
                    content=[TextContent(text=response.text)],
                    is_error=False,
                    backend_status=response.status_code,
                )

        except httpx.RequestError as e:
            logger.error(
                "External SSE tool request failed",
                tool_name=tool.name,
                url=tool.base_url,
                error=str(e),
            )
            return ToolResult(
                content=[TextContent(text=f"Request to external server failed: {str(e)}")],
                is_error=True,
            )

    async def _invoke_external_http(
        self,
        tool: ExternalTool,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Invoke external tool via HTTP JSON-RPC transport.

        Args:
            tool: ExternalTool instance
            arguments: Tool invocation arguments

        Returns:
            ToolResult with response
        """
        try:
            # Build JSON-RPC request
            jsonrpc_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": tool.original_name,
                    "arguments": arguments,
                },
            }

            # Build headers
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            # Add credentials
            if tool.auth_type == "api_key" and tool.credentials:
                api_key = tool.credentials.get("api_key")
                header_name = tool.credentials.get("header_name", "X-API-Key")
                if api_key:
                    headers[header_name] = api_key

            elif tool.auth_type == "bearer_token" and tool.credentials:
                token = tool.credentials.get("token")
                if token:
                    headers["Authorization"] = f"Bearer {token}"

            logger.debug(
                "Invoking external HTTP tool",
                tool_name=tool.name,
                url=tool.base_url,
            )

            response = await self._http_client.post(
                tool.base_url,
                json=jsonrpc_request,
                headers=headers,
                timeout=30.0,
            )

            if response.status_code >= 400:
                return ToolResult(
                    content=[TextContent(text=f"External server error: {response.status_code}")],
                    is_error=True,
                    backend_status=response.status_code,
                )

            # Parse response
            try:
                data = response.json()

                if "error" in data:
                    error_msg = data["error"].get("message", str(data["error"]))
                    return ToolResult(
                        content=[TextContent(text=f"External tool error: {error_msg}")],
                        is_error=True,
                    )

                result = data.get("result", {})
                content_items = result.get("content", [])

                contents = []
                for item in content_items:
                    if item.get("type") == "text":
                        contents.append(TextContent(text=item.get("text", "")))
                    else:
                        contents.append(TextContent(text=json.dumps(item)))

                if not contents:
                    contents = [TextContent(text=json.dumps(result))]

                return ToolResult(
                    content=contents,
                    is_error=result.get("isError", False),
                    backend_status=response.status_code,
                )

            except json.JSONDecodeError:
                return ToolResult(
                    content=[TextContent(text=response.text)],
                    is_error=False,
                    backend_status=response.status_code,
                )

        except httpx.RequestError as e:
            logger.error(
                "External HTTP tool request failed",
                tool_name=tool.name,
                url=tool.base_url,
                error=str(e),
            )
            return ToolResult(
                content=[TextContent(text=f"Request to external server failed: {str(e)}")],
                is_error=True,
            )
