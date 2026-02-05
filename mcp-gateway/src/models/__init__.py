"""Pydantic models for MCP Gateway."""

from .mcp import (
    AnyTool,
    BaseTool,
    ContentType,
    CoreTool,
    ErrorResponse,
    ExternalTool,
    GetPromptResult,
    ImageContent,
    InvokeToolResponse,
    ListCategoriesResponse,
    ListPromptsResponse,
    ListResourcesResponse,
    ListTagsResponse,
    # Response models
    ListToolsResponse,
    # Enums
    MCPVersion,
    # Prompt models
    Prompt,
    PromptArgument,
    PromptMessage,
    ProxiedTool,
    ReadResourceResponse,
    # Resource models
    Resource,
    ResourceContent,
    ResourceReference,
    TextContent,
    # Tool models
    Tool,
    ToolCategory,
    ToolDomain,
    ToolInputSchema,
    ToolInvocation,
    ToolParameter,
    ToolResult,
    ToolType,
)
from .server import (
    ListServersResponse,
    ListServerSubscriptionsResponse,
    MCPServer,
    # SQLAlchemy models
    MCPServerModel,
    MCPServerTool,
    MCPServerToolModel,
    # Pydantic schemas
    MCPServerVisibility,
    # Enums
    ServerCategory,
    ServerStatus,
    ServerSubscription,
    ServerSubscriptionCreate,
    ServerSubscriptionModel,
    ServerSubscriptionStatus,
    ServerSubscriptionWithKey,
    ToolAccess,
    ToolAccessModel,
    ToolAccessStatus,
    ToolAccessUpdate,
)
from .subscription import (
    Base,
    SubscriptionModel,
    SubscriptionStatus,
)

__all__ = [
    # Enums
    "MCPVersion",
    "ContentType",
    "ToolType",
    "ToolDomain",
    # Tool models
    "Tool",
    "BaseTool",
    "CoreTool",
    "ProxiedTool",
    "ExternalTool",
    "AnyTool",
    "ToolParameter",
    "ToolInputSchema",
    "ToolInvocation",
    "ToolResult",
    "TextContent",
    "ImageContent",
    "ResourceContent",
    "ToolCategory",
    # Resource models
    "Resource",
    "ResourceReference",
    # Prompt models
    "Prompt",
    "PromptArgument",
    "PromptMessage",
    "GetPromptResult",
    # Response models
    "ListToolsResponse",
    "ListCategoriesResponse",
    "ListTagsResponse",
    "ListResourcesResponse",
    "ListPromptsResponse",
    "InvokeToolResponse",
    "ReadResourceResponse",
    "ErrorResponse",
    # Subscription models
    "Base",
    "SubscriptionStatus",
    "SubscriptionModel",
    # Server models
    "ServerCategory",
    "ServerStatus",
    "ToolAccessStatus",
    "ServerSubscriptionStatus",
    "MCPServerModel",
    "MCPServerToolModel",
    "ServerSubscriptionModel",
    "ToolAccessModel",
    "MCPServerVisibility",
    "MCPServerTool",
    "MCPServer",
    "ToolAccess",
    "ServerSubscription",
    "ServerSubscriptionWithKey",
    "ServerSubscriptionCreate",
    "ToolAccessUpdate",
    "ListServersResponse",
    "ListServerSubscriptionsResponse",
]
