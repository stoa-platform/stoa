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
    ListResourcesResponse,
    ListPromptsResponse,
    InvokeToolResponse,
    ReadResourceResponse,
    ErrorResponse,
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
    "ListResourcesResponse",
    "ListPromptsResponse",
    "InvokeToolResponse",
    "ReadResourceResponse",
    "ErrorResponse",
]
