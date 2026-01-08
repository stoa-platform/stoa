"""Pydantic models for MCP Gateway."""

from .mcp import (
    # Enums
    MCPVersion,
    ContentType,
    # Tool models
    Tool,
    ToolParameter,
    ToolInputSchema,
    ToolInvocation,
    ToolResult,
    TextContent,
    ImageContent,
    ResourceContent,
    ToolCategory,
    # Resource models
    Resource,
    ResourceReference,
    # Prompt models
    Prompt,
    PromptArgument,
    PromptMessage,
    GetPromptResult,
    # Response models
    ListToolsResponse,
    ListCategoriesResponse,
    ListTagsResponse,
    ListResourcesResponse,
    ListPromptsResponse,
    InvokeToolResponse,
    ReadResourceResponse,
    ErrorResponse,
)
from .subscription import (
    Base,
    SubscriptionStatus,
    SubscriptionModel,
)

__all__ = [
    # Enums
    "MCPVersion",
    "ContentType",
    # Tool models
    "Tool",
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
]
