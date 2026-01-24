"""External MCP Server Loader.

Polls Control Plane API to fetch external MCP server configurations
(Linear, GitHub, Slack, etc.) and registers their tools with the registry.

The loader runs as a background task, polling every N seconds.
Tools are registered as ExternalTool instances that proxy to the external servers.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from ..config import get_settings

logger = structlog.get_logger(__name__)


class ExternalServerLoader:
    """Loader for external MCP server configurations.

    Polls the Control Plane API internal endpoint to fetch
    external MCP server configurations and their tools.
    """

    def __init__(self) -> None:
        """Initialize the external server loader."""
        self._running = False
        self._task: asyncio.Task | None = None
        self._http_client: httpx.AsyncClient | None = None
        self._servers: dict[str, dict[str, Any]] = {}
        self._tools: dict[str, dict[str, Any]] = {}  # tool_id -> tool config
        self._last_sync: datetime | None = None

    async def startup(self) -> None:
        """Start the loader background task."""
        settings = get_settings()

        if not settings.external_servers_enabled:
            logger.info("External MCP servers disabled")
            return

        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            follow_redirects=True,
        )

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "External server loader started",
            poll_interval=settings.external_server_poll_interval,
        )

    async def shutdown(self) -> None:
        """Stop the loader background task."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        logger.info("External server loader stopped")

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        settings = get_settings()

        while self._running:
            try:
                await self._sync_servers()
            except Exception as e:
                logger.error("Failed to sync external servers", error=str(e))

            await asyncio.sleep(settings.external_server_poll_interval)

    async def _sync_servers(self) -> None:
        """Fetch and sync external server configurations from Control Plane API."""
        settings = get_settings()

        if not self._http_client:
            return

        url = f"{settings.control_plane_api_url}/v1/internal/external-mcp-servers"

        headers = {
            "Accept": "application/json",
            "X-STOA-Service": "mcp-gateway",
        }

        # Add API key if configured
        if settings.external_server_api_key:
            headers["X-API-Key"] = settings.external_server_api_key

        try:
            response = await self._http_client.get(url, headers=headers)

            if response.status_code != 200:
                logger.warning(
                    "Failed to fetch external servers",
                    status_code=response.status_code,
                    response=response.text[:500],
                )
                return

            data = response.json()
            servers = data.get("servers", [])

            # Track which servers/tools we've seen
            seen_server_ids = set()
            seen_tool_ids = set()

            # Import here to avoid circular imports
            from . import get_tool_registry

            registry = await get_tool_registry()

            for server in servers:
                server_id = server.get("id")
                if not server_id:
                    continue

                seen_server_ids.add(server_id)
                self._servers[server_id] = server

                # Register tools from this server
                for tool in server.get("tools", []):
                    tool_id = tool.get("id")
                    if not tool_id or not tool.get("enabled", True):
                        continue

                    seen_tool_ids.add(tool_id)

                    # Check if tool needs registration or update
                    existing = self._tools.get(tool_id)
                    if existing != tool:
                        self._tools[tool_id] = tool
                        await self._register_external_tool(registry, server, tool)

            # Unregister tools that are no longer present
            for tool_id in list(self._tools.keys()):
                if tool_id not in seen_tool_ids:
                    tool = self._tools.pop(tool_id)
                    await self._unregister_external_tool(registry, tool)

            # Clean up servers that are no longer present
            for server_id in list(self._servers.keys()):
                if server_id not in seen_server_ids:
                    del self._servers[server_id]

            self._last_sync = datetime.now(timezone.utc)
            logger.info(
                "External servers synced",
                server_count=len(servers),
                tool_count=len(self._tools),
            )

        except httpx.RequestError as e:
            logger.error("HTTP error syncing external servers", error=str(e))

    async def _register_external_tool(
        self,
        registry: Any,
        server: dict[str, Any],
        tool: dict[str, Any],
    ) -> None:
        """Register an external tool with the registry.

        Args:
            registry: ToolRegistry instance
            server: Server configuration dict
            tool: Tool configuration dict
        """
        from ..models import ExternalTool, ToolInputSchema

        namespaced_name = tool.get("namespaced_name", tool.get("name"))

        # Build input schema if available
        input_schema = None
        if tool.get("input_schema"):
            schema_data = tool["input_schema"]
            input_schema = ToolInputSchema(
                type=schema_data.get("type", "object"),
                properties=schema_data.get("properties", {}),
                required=schema_data.get("required", []),
            )

        external_tool = ExternalTool(
            name=namespaced_name,
            description=tool.get("description") or f"Tool from {server.get('display_name', server.get('name'))}",
            input_schema=input_schema,
            # External server configuration
            server_id=str(server.get("id")),
            server_name=server.get("name"),
            original_name=tool.get("name"),
            base_url=server.get("base_url"),
            transport=server.get("transport", "sse"),
            auth_type=server.get("auth_type", "none"),
            credentials=server.get("credentials"),  # From Vault via Control Plane API
        )

        registry.register_external_tool(external_tool)
        logger.debug(
            "Registered external tool",
            tool_name=namespaced_name,
            server_name=server.get("name"),
        )

    async def _unregister_external_tool(
        self,
        registry: Any,
        tool: dict[str, Any],
    ) -> None:
        """Unregister an external tool from the registry.

        Args:
            registry: ToolRegistry instance
            tool: Tool configuration dict
        """
        namespaced_name = tool.get("namespaced_name", tool.get("name"))
        registry.unregister_external_tool(namespaced_name)
        logger.debug("Unregistered external tool", tool_name=namespaced_name)

    async def reload(self) -> dict[str, Any]:
        """Force reload of external server configurations.

        Returns:
            Status dict with server and tool counts
        """
        await self._sync_servers()
        return {
            "status": "reloaded",
            "server_count": len(self._servers),
            "tool_count": len(self._tools),
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
        }

    def get_status(self) -> dict[str, Any]:
        """Get loader status.

        Returns:
            Status dict with server/tool counts and last sync time
        """
        return {
            "enabled": get_settings().external_servers_enabled,
            "running": self._running,
            "server_count": len(self._servers),
            "tool_count": len(self._tools),
            "last_sync": self._last_sync.isoformat() if self._last_sync else None,
        }


# Module singleton
_external_server_loader: ExternalServerLoader | None = None


async def get_external_server_loader() -> ExternalServerLoader:
    """Get or create the external server loader singleton."""
    global _external_server_loader

    if _external_server_loader is None:
        _external_server_loader = ExternalServerLoader()

    return _external_server_loader


async def shutdown_external_server_loader() -> None:
    """Shutdown the external server loader."""
    global _external_server_loader

    if _external_server_loader:
        await _external_server_loader.shutdown()
        _external_server_loader = None
