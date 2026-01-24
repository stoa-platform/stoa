"""MCP Tool Registry Service.

CAB-841: Refactored into modular structure for maintainability.
CAB-603: Core vs Proxied tool separation.
CAB-605 Phase 3: Tool consolidation with deprecation layer.

Manages the registration and discovery of MCP tools.
Tools are mapped from STOA API definitions.

Structure:
- exceptions.py: ToolNotFoundError
- models.py: DeprecatedToolAlias dataclass
- registration.py: RegistrationMixin (register/unregister methods)
- lookup.py: LookupMixin (get/list methods)
- deprecation.py: DeprecationMixin (deprecation management)
- invocation.py: InvocationMixin (main invoke entry point)
- core_routing.py: CoreRoutingMixin (_invoke_core_tool routing)
- action_handlers.py: ActionHandlersMixin (_handle_*_action methods)
- proxied.py: ProxiedMixin (_invoke_proxied_tool)
- legacy.py: LegacyMixin (legacy invocation methods)
- singleton.py: Module singleton functions
"""

import httpx
import structlog

from ...config import get_settings
from ...models import (
    Tool,
    CoreTool,
    ProxiedTool,
    ExternalTool,
)

# Public API exports
from .exceptions import ToolNotFoundError
from .models import DeprecatedToolAlias
from .singleton import get_tool_registry, shutdown_tool_registry

# Mixins
from .deprecation import DeprecationMixin
from .registration import RegistrationMixin
from .lookup import LookupMixin
from .invocation import InvocationMixin
from .core_routing import CoreRoutingMixin
from .action_handlers import ActionHandlersMixin
from .proxied import ProxiedMixin
from .external import ExternalMixin
from .legacy import LegacyMixin

logger = structlog.get_logger(__name__)


class ToolRegistry(
    DeprecationMixin,
    RegistrationMixin,
    LookupMixin,
    InvocationMixin,
    CoreRoutingMixin,
    ActionHandlersMixin,
    ProxiedMixin,
    ExternalMixin,
    LegacyMixin,
):
    """Registry for MCP Tools.

    Manages tool definitions and provides lookup functionality.
    Tools can be registered from:
    - Static configuration (core tools)
    - STOA Control Plane API (dynamic discovery)
    - Kubernetes CRDs (proxied tools)
    - OpenAPI specifications

    CAB-603: Separated storage for core vs proxied tools.
    - Core Tools: 12 static platform tools with stoa_{domain}_{action} naming
    - Proxied Tools: Dynamic tenant API tools with {tenant}:{api}:{operation} namespace

    CAB-605 Phase 3: Tool consolidation with deprecation layer.
    - Action-based tools: Single tool with action enum parameter
    - Deprecation aliases: Backward compatibility for 60 days

    CAB-841: Refactored from monolithic 1984-line file into modular mixins.
    """

    def __init__(self) -> None:
        """Initialize the tool registry."""
        # CAB-603: Separate storage for core vs proxied tools
        self._core_tools: dict[str, CoreTool] = {}
        self._proxied_tools: dict[str, ProxiedTool] = {}  # Key: internal_key
        self._external_tools: dict[str, ExternalTool] = {}  # External MCP servers (Linear, GitHub, etc.)
        self._tools: dict[str, Tool] = {}  # Legacy storage for backward compatibility
        self._http_client: httpx.AsyncClient | None = None

        # CAB-605 Phase 3: Deprecation aliases for backward compatibility
        self._deprecated_aliases: dict[str, DeprecatedToolAlias] = {}

    async def startup(self) -> None:
        """Initialize the registry on application startup."""
        settings = get_settings()
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.mcp_timeout_seconds),
            follow_redirects=True,
        )
        logger.info("Tool registry initialized")

        # CAB-605: Register consolidated core tools (12 action-based tools)
        await self._register_core_tools()

        # CAB-605: Register deprecation aliases for backward compatibility
        await self._register_deprecation_aliases()

        # Register built-in tools (legacy, for backward compatibility)
        await self._register_builtin_tools()

    async def shutdown(self) -> None:
        """Cleanup on application shutdown."""
        if self._http_client:
            await self._http_client.aclose()
        logger.info("Tool registry shutdown")


__all__ = [
    "ToolRegistry",
    "ToolNotFoundError",
    "DeprecatedToolAlias",
    "get_tool_registry",
    "shutdown_tool_registry",
]
