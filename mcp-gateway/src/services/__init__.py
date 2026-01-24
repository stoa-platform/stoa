"""Business logic services."""

from .tool_registry import (
    ToolRegistry,
    get_tool_registry,
    shutdown_tool_registry,
)
from .openapi_converter import (
    OpenAPIConverter,
    convert_openapi_to_tools,
)
from .vault_client import (
    VaultClient,
    get_vault_client,
    shutdown_vault_client,
)
from .database import (
    init_database,
    shutdown_database,
    get_db_session,
    get_session,
)
from .api_key import (
    validate_api_key,
    hash_api_key,
    verify_api_key_hash,
)
from .health import (
    HealthChecker,
    HealthStatus,
    ComponentHealth,
    PlatformHealth,
    check_platform_health,
)
# CAB-660/ADR-001: Tool handlers using CoreAPIClient (no direct DB access)
from .tool_handlers import (
    STOAToolHandlers,
    get_tool_handlers,
    init_tool_handlers,
    shutdown_tool_handlers,
)

__all__ = [
    "ToolRegistry",
    "get_tool_registry",
    "shutdown_tool_registry",
    "OpenAPIConverter",
    "convert_openapi_to_tools",
    "VaultClient",
    "get_vault_client",
    "shutdown_vault_client",
    "init_database",
    "shutdown_database",
    "get_db_session",
    "get_session",
    "validate_api_key",
    "hash_api_key",
    "verify_api_key_hash",
    # CAB-658: Health check module
    "HealthChecker",
    "HealthStatus",
    "ComponentHealth",
    "PlatformHealth",
    "check_platform_health",
    # CAB-660/ADR-001: Tool handlers using CoreAPIClient (no direct DB access)
    "STOAToolHandlers",
    "get_tool_handlers",
    "init_tool_handlers",
    "shutdown_tool_handlers",
]
