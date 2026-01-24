"""Proxied tool invocation mixin.

CAB-841: Extracted from tool_registry.py for modularity.
CAB-603: Proxied tools forward requests to backend APIs.
"""

from typing import TYPE_CHECKING, Any

import httpx
import structlog

from ...models import (
    ProxiedTool,
    ToolResult,
    TextContent,
)

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)


class ProxiedMixin:
    """Mixin providing proxied tool invocation."""

    # Type hints for attributes from ToolRegistry
    _http_client: httpx.AsyncClient | None

    async def _invoke_proxied_tool(
        self,
        tool: ProxiedTool,
        arguments: dict[str, Any],
        user_token: str | None = None,
    ) -> ToolResult:
        """Invoke a proxied tenant API tool.

        CAB-603: Proxied tools forward requests to backend APIs
        with proper authentication and header injection.

        Args:
            tool: ProxiedTool instance
            arguments: Tool invocation arguments
            user_token: User JWT for backend authentication

        Returns:
            ToolResult with backend response
        """
        if not self._http_client:
            return ToolResult(
                content=[TextContent(text="HTTP client not initialized")],
                is_error=True,
            )

        if not tool.endpoint:
            return ToolResult(
                content=[TextContent(text=f"Proxied tool {tool.name} has no endpoint configured")],
                is_error=True,
            )

        # Build headers
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-STOA-Tenant-ID": tool.tenant_id,
            "X-STOA-Tool-Name": tool.namespaced_name,
        }

        # Add user token if available
        if user_token:
            headers["Authorization"] = f"Bearer {user_token}"

        # Add custom headers from tool definition
        headers.update(tool.headers)

        try:
            method = tool.method.upper()

            if method == "GET":
                response = await self._http_client.get(
                    tool.endpoint,
                    params=arguments,
                    headers=headers,
                )
            elif method == "POST":
                response = await self._http_client.post(
                    tool.endpoint,
                    json=arguments,
                    headers=headers,
                )
            elif method == "PUT":
                response = await self._http_client.put(
                    tool.endpoint,
                    json=arguments,
                    headers=headers,
                )
            elif method == "DELETE":
                response = await self._http_client.delete(
                    tool.endpoint,
                    params=arguments,
                    headers=headers,
                )
            elif method == "PATCH":
                response = await self._http_client.patch(
                    tool.endpoint,
                    json=arguments,
                    headers=headers,
                )
            else:
                return ToolResult(
                    content=[TextContent(text=f"Unsupported HTTP method: {method}")],
                    is_error=True,
                )

            # Return result
            is_error = response.status_code >= 400
            return ToolResult(
                content=[TextContent(text=response.text)],
                is_error=is_error,
                backend_status=response.status_code,
            )

        except httpx.RequestError as e:
            logger.error(
                "Proxied tool request failed",
                tool_name=tool.namespaced_name,
                endpoint=tool.endpoint,
                error=str(e),
            )
            return ToolResult(
                content=[TextContent(text=f"Request to backend failed: {str(e)}")],
                is_error=True,
            )
