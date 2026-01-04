"""Kubernetes watcher for Tool and ToolSet CRDs.

Watches Kubernetes custom resources and synchronizes them
with the MCP Gateway tool registry.
"""

import asyncio
from typing import Any, Callable, Coroutine

import structlog

from ..config import get_settings
from ..models import Tool, ToolInputSchema
from .models import ToolCR, ToolCRSpec, ToolSetCR

logger = structlog.get_logger(__name__)

# Singleton instance
_watcher: "ToolWatcher | None" = None

# CRD API Group and Version
CRD_GROUP = "stoa.cab-i.com"
CRD_VERSION = "v1alpha1"
CRD_PLURAL_TOOLS = "tools"
CRD_PLURAL_TOOLSETS = "toolsets"


class ToolWatcher:
    """Watches Kubernetes CRDs and syncs with tool registry.

    Supports two modes:
    - In-cluster: Uses service account credentials
    - Out-of-cluster: Uses kubeconfig file

    The watcher monitors Tool and ToolSet custom resources and
    automatically registers/unregisters tools in the MCP Gateway.
    """

    def __init__(
        self,
        namespace: str | None = None,
        kubeconfig: str | None = None,
        enabled: bool = True,
    ):
        """Initialize the Kubernetes watcher.

        Args:
            namespace: Namespace to watch (None for all namespaces)
            kubeconfig: Path to kubeconfig file (None for in-cluster)
            enabled: Enable/disable the watcher
        """
        self.namespace = namespace
        self.kubeconfig = kubeconfig
        self.enabled = enabled

        self._api_client: Any | None = None
        self._custom_api: Any | None = None
        self._watch_tasks: list[asyncio.Task] = []
        self._running = False

        # Callbacks for tool registry integration
        self._on_tool_added: Callable[[Tool], Coroutine[Any, Any, None]] | None = None
        self._on_tool_removed: Callable[[str], Coroutine[Any, Any, None]] | None = None
        self._on_tool_modified: Callable[[Tool], Coroutine[Any, Any, None]] | None = None

        # Track registered tools by CR name
        self._cr_to_tools: dict[str, list[str]] = {}

    def set_callbacks(
        self,
        on_added: Callable[[Tool], Coroutine[Any, Any, None]] | None = None,
        on_removed: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        on_modified: Callable[[Tool], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        """Set callbacks for tool registry integration.

        Args:
            on_added: Called when a tool should be registered
            on_removed: Called when a tool should be unregistered
            on_modified: Called when a tool should be updated
        """
        self._on_tool_added = on_added
        self._on_tool_removed = on_removed
        self._on_tool_modified = on_modified

    async def startup(self) -> None:
        """Start the Kubernetes watcher.

        Initializes the Kubernetes client and starts watching
        for Tool and ToolSet custom resources.
        """
        if not self.enabled:
            logger.info("Kubernetes watcher disabled")
            return

        try:
            # Try to import kubernetes-asyncio
            from kubernetes_asyncio import client, config, watch

            # Load configuration
            if self.kubeconfig:
                await config.load_kube_config(config_file=self.kubeconfig)
                logger.info("Loaded kubeconfig", path=self.kubeconfig)
            else:
                try:
                    config.load_incluster_config()
                    logger.info("Using in-cluster Kubernetes config")
                except config.ConfigException:
                    # Fallback to kubeconfig for local development
                    await config.load_kube_config()
                    logger.info("Loaded default kubeconfig")

            self._api_client = client.ApiClient()
            self._custom_api = client.CustomObjectsApi(self._api_client)

            self._running = True

            # Start watch tasks
            self._watch_tasks.append(
                asyncio.create_task(self._watch_tools())
            )
            self._watch_tasks.append(
                asyncio.create_task(self._watch_toolsets())
            )

            logger.info(
                "Kubernetes watcher started",
                namespace=self.namespace or "all",
            )

        except ImportError:
            logger.warning(
                "kubernetes-asyncio not installed, K8s watcher disabled. "
                "Install with: pip install kubernetes-asyncio"
            )
            self.enabled = False
        except Exception as e:
            logger.error("Failed to start Kubernetes watcher", error=str(e))
            self.enabled = False

    async def shutdown(self) -> None:
        """Stop the Kubernetes watcher."""
        self._running = False

        # Cancel watch tasks
        for task in self._watch_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._watch_tasks.clear()

        # Close API client
        if self._api_client:
            await self._api_client.close()
            self._api_client = None

        logger.info("Kubernetes watcher stopped")

    async def _watch_tools(self) -> None:
        """Watch Tool custom resources."""
        from kubernetes_asyncio import watch

        w = watch.Watch()

        while self._running:
            try:
                if self.namespace:
                    stream = w.stream(
                        self._custom_api.list_namespaced_custom_object,
                        group=CRD_GROUP,
                        version=CRD_VERSION,
                        namespace=self.namespace,
                        plural=CRD_PLURAL_TOOLS,
                    )
                else:
                    stream = w.stream(
                        self._custom_api.list_cluster_custom_object,
                        group=CRD_GROUP,
                        version=CRD_VERSION,
                        plural=CRD_PLURAL_TOOLS,
                    )

                async for event in stream:
                    if not self._running:
                        break

                    event_type = event["type"]
                    obj = event["object"]

                    try:
                        tool_cr = self._parse_tool_cr(obj)
                        await self._handle_tool_event(event_type, tool_cr)
                    except Exception as e:
                        logger.error(
                            "Error handling Tool event",
                            event_type=event_type,
                            error=str(e),
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Tool watch error, restarting", error=str(e))
                await asyncio.sleep(5)  # Backoff before retry

    async def _watch_toolsets(self) -> None:
        """Watch ToolSet custom resources."""
        from kubernetes_asyncio import watch

        w = watch.Watch()

        while self._running:
            try:
                if self.namespace:
                    stream = w.stream(
                        self._custom_api.list_namespaced_custom_object,
                        group=CRD_GROUP,
                        version=CRD_VERSION,
                        namespace=self.namespace,
                        plural=CRD_PLURAL_TOOLSETS,
                    )
                else:
                    stream = w.stream(
                        self._custom_api.list_cluster_custom_object,
                        group=CRD_GROUP,
                        version=CRD_VERSION,
                        plural=CRD_PLURAL_TOOLSETS,
                    )

                async for event in stream:
                    if not self._running:
                        break

                    event_type = event["type"]
                    obj = event["object"]

                    try:
                        toolset_cr = self._parse_toolset_cr(obj)
                        await self._handle_toolset_event(event_type, toolset_cr)
                    except Exception as e:
                        logger.error(
                            "Error handling ToolSet event",
                            event_type=event_type,
                            error=str(e),
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ToolSet watch error, restarting", error=str(e))
                await asyncio.sleep(5)

    def _parse_tool_cr(self, obj: dict[str, Any]) -> ToolCR:
        """Parse a Kubernetes object into a ToolCR model."""
        return ToolCR(
            apiVersion=obj.get("apiVersion", f"{CRD_GROUP}/{CRD_VERSION}"),
            kind=obj.get("kind", "Tool"),
            metadata=obj.get("metadata", {}),
            spec=obj.get("spec", {}),
            status=obj.get("status"),
        )

    def _parse_toolset_cr(self, obj: dict[str, Any]) -> ToolSetCR:
        """Parse a Kubernetes object into a ToolSetCR model."""
        return ToolSetCR(
            apiVersion=obj.get("apiVersion", f"{CRD_GROUP}/{CRD_VERSION}"),
            kind=obj.get("kind", "ToolSet"),
            metadata=obj.get("metadata", {}),
            spec=obj.get("spec", {}),
            status=obj.get("status"),
        )

    async def _handle_tool_event(self, event_type: str, tool_cr: ToolCR) -> None:
        """Handle a Tool custom resource event.

        Args:
            event_type: ADDED, MODIFIED, or DELETED
            tool_cr: The Tool custom resource
        """
        cr_key = f"{tool_cr.metadata.namespace}/{tool_cr.metadata.name}"

        logger.info(
            "Tool CR event",
            event_type=event_type,
            name=tool_cr.metadata.name,
            namespace=tool_cr.metadata.namespace,
        )

        if event_type == "DELETED":
            # Unregister all tools from this CR
            tool_names = self._cr_to_tools.pop(cr_key, [])
            for tool_name in tool_names:
                if self._on_tool_removed:
                    await self._on_tool_removed(tool_name)
            return

        if not tool_cr.spec.enabled:
            # Tool is disabled, treat as deletion
            tool_names = self._cr_to_tools.pop(cr_key, [])
            for tool_name in tool_names:
                if self._on_tool_removed:
                    await self._on_tool_removed(tool_name)
            return

        # Convert CR to Tool model
        tool = self._cr_to_tool(tool_cr)

        if event_type == "ADDED":
            self._cr_to_tools[cr_key] = [tool.name]
            if self._on_tool_added:
                await self._on_tool_added(tool)
        elif event_type == "MODIFIED":
            # Remove old tools, add new
            old_names = self._cr_to_tools.get(cr_key, [])
            for old_name in old_names:
                if old_name != tool.name and self._on_tool_removed:
                    await self._on_tool_removed(old_name)

            self._cr_to_tools[cr_key] = [tool.name]
            if self._on_tool_modified:
                await self._on_tool_modified(tool)
            elif self._on_tool_added:
                await self._on_tool_added(tool)

    async def _handle_toolset_event(
        self, event_type: str, toolset_cr: ToolSetCR
    ) -> None:
        """Handle a ToolSet custom resource event.

        Args:
            event_type: ADDED, MODIFIED, or DELETED
            toolset_cr: The ToolSet custom resource
        """
        cr_key = f"{toolset_cr.metadata.namespace}/{toolset_cr.metadata.name}"

        logger.info(
            "ToolSet CR event",
            event_type=event_type,
            name=toolset_cr.metadata.name,
            namespace=toolset_cr.metadata.namespace,
        )

        if event_type == "DELETED":
            # Unregister all tools from this ToolSet
            tool_names = self._cr_to_tools.pop(cr_key, [])
            for tool_name in tool_names:
                if self._on_tool_removed:
                    await self._on_tool_removed(tool_name)
            return

        if not toolset_cr.spec.enabled:
            tool_names = self._cr_to_tools.pop(cr_key, [])
            for tool_name in tool_names:
                if self._on_tool_removed:
                    await self._on_tool_removed(tool_name)
            return

        # Convert ToolSet to multiple Tools
        tools = await self._toolset_to_tools(toolset_cr)

        # Handle based on event type
        old_names = set(self._cr_to_tools.get(cr_key, []))
        new_names = {t.name for t in tools}

        # Remove tools that no longer exist
        for old_name in old_names - new_names:
            if self._on_tool_removed:
                await self._on_tool_removed(old_name)

        # Add/update tools
        for tool in tools:
            if tool.name in old_names:
                if self._on_tool_modified:
                    await self._on_tool_modified(tool)
            else:
                if self._on_tool_added:
                    await self._on_tool_added(tool)

        self._cr_to_tools[cr_key] = list(new_names)

    def _cr_to_tool(self, tool_cr: ToolCR) -> Tool:
        """Convert a Tool CR to an MCP Tool model.

        Args:
            tool_cr: The Tool custom resource

        Returns:
            An MCP Tool model
        """
        spec = tool_cr.spec

        # Generate tool name from CR metadata
        tool_name = self._generate_tool_name(
            tool_cr.metadata.namespace,
            tool_cr.metadata.name,
        )

        # Build input schema
        input_schema = ToolInputSchema(
            properties=spec.inputSchema.get("properties", {}),
            required=spec.inputSchema.get("required", []),
        )

        return Tool(
            name=tool_name,
            description=spec.description,
            input_schema=input_schema,
            endpoint=spec.endpoint,
            method=spec.method,
            tags=spec.tags,
            version=spec.version,
            tenant_id=tool_cr.metadata.namespace,
            api_id=spec.apiRef.name if spec.apiRef else None,
        )

    async def _toolset_to_tools(self, toolset_cr: ToolSetCR) -> list[Tool]:
        """Convert a ToolSet CR to multiple MCP Tool models.

        Fetches OpenAPI spec and generates tools from operations.

        Args:
            toolset_cr: The ToolSet custom resource

        Returns:
            List of MCP Tool models
        """
        tools: list[Tool] = []
        spec = toolset_cr.spec

        if not spec.openAPISpec:
            logger.warning(
                "ToolSet has no OpenAPI spec",
                name=toolset_cr.metadata.name,
            )
            return tools

        # Fetch OpenAPI spec
        openapi_spec = await self._fetch_openapi_spec(spec.openAPISpec)
        if not openapi_spec:
            return tools

        # Import the converter
        from ..services.openapi_converter import convert_openapi_to_tools

        # Convert OpenAPI to tools
        base_url = spec.baseURL

        converted_tools = convert_openapi_to_tools(
            openapi_spec,
            api_id=toolset_cr.metadata.name,
            tenant_id=toolset_cr.metadata.namespace,
            base_url=base_url,
        )

        # Apply selector filters
        if spec.selector:
            converted_tools = self._apply_selector(converted_tools, spec.selector)

        # Apply defaults
        if spec.toolDefaults:
            for tool in converted_tools:
                if spec.toolDefaults.tags:
                    tool.tags.extend(spec.toolDefaults.tags)

        return converted_tools

    async def _fetch_openapi_spec(self, source: Any) -> dict[str, Any] | None:
        """Fetch OpenAPI specification from the configured source.

        Args:
            source: OpenAPISpecSource configuration

        Returns:
            Parsed OpenAPI spec or None on error
        """
        import httpx
        import yaml

        try:
            if source.url:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(source.url)
                    resp.raise_for_status()

                    content_type = resp.headers.get("content-type", "")
                    if "yaml" in content_type or source.url.endswith((".yaml", ".yml")):
                        return yaml.safe_load(resp.text)
                    return resp.json()

            if source.inline:
                if source.inline.strip().startswith("{"):
                    import json
                    return json.loads(source.inline)
                return yaml.safe_load(source.inline)

            if source.configMapRef:
                # Read from ConfigMap (requires K8s API)
                # TODO: Implement ConfigMap reading
                logger.warning("ConfigMap source not yet implemented")
                return None

            if source.secretRef:
                # Read from Secret (requires K8s API)
                # TODO: Implement Secret reading
                logger.warning("Secret source not yet implemented")
                return None

        except Exception as e:
            logger.error("Failed to fetch OpenAPI spec", error=str(e))

        return None

    def _apply_selector(
        self, tools: list[Tool], selector: Any
    ) -> list[Tool]:
        """Apply selector filters to tools.

        Args:
            tools: List of tools to filter
            selector: ToolSetSelectorSpec

        Returns:
            Filtered list of tools
        """
        filtered = tools

        if selector.tags:
            filtered = [
                t for t in filtered
                if any(tag in t.tags for tag in selector.tags)
            ]

        if selector.excludeTags:
            filtered = [
                t for t in filtered
                if not any(tag in t.tags for tag in selector.excludeTags)
            ]

        if selector.methods:
            filtered = [
                t for t in filtered
                if t.method in selector.methods
            ]

        return filtered

    def _generate_tool_name(self, namespace: str, name: str) -> str:
        """Generate a unique tool name from namespace and CR name.

        Args:
            namespace: Kubernetes namespace
            name: CR name

        Returns:
            Sanitized tool name
        """
        # Format: {namespace}_{name}
        raw_name = f"{namespace}_{name}"

        # Sanitize: lowercase, replace invalid chars with underscore
        sanitized = raw_name.lower()
        sanitized = "".join(
            c if c.isalnum() or c == "_" else "_"
            for c in sanitized
        )

        # Collapse multiple underscores
        while "__" in sanitized:
            sanitized = sanitized.replace("__", "_")

        return sanitized.strip("_")


async def get_tool_watcher() -> ToolWatcher:
    """Get or create the singleton tool watcher.

    Returns:
        The global ToolWatcher instance.
    """
    global _watcher

    if _watcher is None:
        settings = get_settings()

        # Get K8s settings
        k8s_enabled = getattr(settings, "k8s_watcher_enabled", True)
        k8s_namespace = getattr(settings, "k8s_watch_namespace", None)
        kubeconfig = getattr(settings, "kubeconfig_path", None)

        _watcher = ToolWatcher(
            namespace=k8s_namespace,
            kubeconfig=kubeconfig,
            enabled=k8s_enabled,
        )
        await _watcher.startup()

    return _watcher


async def shutdown_tool_watcher() -> None:
    """Shutdown the singleton tool watcher."""
    global _watcher

    if _watcher:
        await _watcher.shutdown()
        _watcher = None
