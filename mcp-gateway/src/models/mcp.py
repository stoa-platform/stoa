"""MCP Protocol Models.

Based on the Model Context Protocol specification.
https://modelcontextprotocol.io/specification
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# Base Types
# =============================================================================


class MCPVersion(str, Enum):
    """Supported MCP protocol versions."""

    V1 = "1.0"


class ContentType(str, Enum):
    """Content types for MCP responses."""

    TEXT = "text"
    IMAGE = "image"
    RESOURCE = "resource"


# =============================================================================
# Tool Models
# =============================================================================


class ToolParameter(BaseModel):
    """Schema for a tool parameter."""

    name: str = Field(..., description="Parameter name")
    description: str = Field("", description="Parameter description")
    type: str = Field("string", description="JSON Schema type")
    required: bool = Field(False, description="Whether parameter is required")
    default: Any = Field(None, description="Default value if not provided")
    enum: list[str] | None = Field(None, description="Allowed values")


class ToolInputSchema(BaseModel):
    """JSON Schema for tool input."""

    type: Literal["object"] = "object"
    properties: dict[str, Any] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)


class Tool(BaseModel):
    """MCP Tool definition.

    A tool represents an action that can be invoked by an LLM.
    In STOA context, tools map to API endpoints.
    """

    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="Human-readable tool description")
    input_schema: ToolInputSchema = Field(
        default_factory=ToolInputSchema,
        alias="inputSchema",
        description="JSON Schema for tool input",
    )

    # STOA-specific extensions
    api_id: str | None = Field(None, description="Associated STOA API ID")
    tenant_id: str | None = Field(None, description="Owning tenant ID")
    endpoint: str | None = Field(None, description="Backend API endpoint")
    method: str = Field("POST", description="HTTP method for backend call")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    version: str = Field("1.0.0", description="Tool version")

    model_config = ConfigDict(populate_by_name=True)


class ToolInvocation(BaseModel):
    """Request to invoke a tool."""

    name: str = Field(..., description="Tool name to invoke")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Tool arguments"
    )
    request_id: str | None = Field(None, description="Optional request ID for tracing")


class TextContent(BaseModel):
    """Text content in tool response."""

    type: Literal["text"] = "text"
    text: str


class ImageContent(BaseModel):
    """Image content in tool response."""

    type: Literal["image"] = "image"
    data: str = Field(..., description="Base64-encoded image data")
    mime_type: str = Field("image/png", alias="mimeType")

    model_config = ConfigDict(populate_by_name=True)


class ResourceContent(BaseModel):
    """Resource reference in tool response."""

    type: Literal["resource"] = "resource"
    resource: "ResourceReference"


class ToolResult(BaseModel):
    """Result of a tool invocation."""

    content: list[TextContent | ImageContent | ResourceContent] = Field(
        default_factory=list
    )
    is_error: bool = Field(False, alias="isError")

    # STOA-specific extensions
    request_id: str | None = Field(None, description="Request ID for tracing")
    latency_ms: int | None = Field(None, description="Backend latency in milliseconds")
    backend_status: int | None = Field(None, description="Backend HTTP status code")

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Resource Models
# =============================================================================


class Resource(BaseModel):
    """MCP Resource definition.

    A resource represents data that can be accessed by an LLM.
    In STOA context, resources map to data sources or API responses.
    """

    uri: str = Field(..., description="Unique resource URI")
    name: str = Field(..., description="Human-readable resource name")
    description: str = Field("", description="Resource description")
    mime_type: str = Field("application/json", alias="mimeType")

    # STOA-specific extensions
    api_id: str | None = Field(None, description="Associated STOA API ID")
    tenant_id: str | None = Field(None, description="Owning tenant ID")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")

    model_config = ConfigDict(populate_by_name=True)


class ResourceReference(BaseModel):
    """Reference to a resource."""

    uri: str = Field(..., description="Resource URI")
    mime_type: str = Field("application/json", alias="mimeType")
    text: str | None = Field(None, description="Resource text content")
    blob: str | None = Field(None, description="Base64-encoded binary content")

    model_config = ConfigDict(populate_by_name=True)


class ResourceContentRead(BaseModel):
    """Content of a resource read operation."""

    uri: str = Field(..., description="Resource URI")
    mime_type: str = Field("application/json", alias="mimeType")
    text: str | None = Field(None, description="Text content")
    blob: str | None = Field(None, description="Base64-encoded binary content")

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Prompt Models
# =============================================================================


class PromptArgument(BaseModel):
    """Argument definition for a prompt template."""

    name: str = Field(..., description="Argument name")
    description: str = Field("", description="Argument description")
    required: bool = Field(False, description="Whether argument is required")


class Prompt(BaseModel):
    """MCP Prompt template.

    A prompt is a reusable template for generating LLM prompts.
    In STOA context, prompts provide pre-built API interaction patterns.
    """

    name: str = Field(..., description="Unique prompt identifier")
    description: str = Field("", description="Prompt description")
    arguments: list[PromptArgument] = Field(default_factory=list)

    # STOA-specific extensions
    template: str = Field("", description="Prompt template text")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")


class PromptMessage(BaseModel):
    """Message in a prompt response."""

    role: Literal["user", "assistant"] = Field(..., description="Message role")
    content: TextContent | ImageContent | ResourceContent


class GetPromptResult(BaseModel):
    """Result of getting a prompt."""

    description: str = Field("", description="Prompt description")
    messages: list[PromptMessage] = Field(default_factory=list)


# =============================================================================
# API Response Models
# =============================================================================


class ListToolsResponse(BaseModel):
    """Response for listing tools."""

    tools: list[Tool] = Field(default_factory=list)
    next_cursor: str | None = Field(None, alias="nextCursor")
    total_count: int = Field(0)

    model_config = ConfigDict(populate_by_name=True)


class ListResourcesResponse(BaseModel):
    """Response for listing resources."""

    resources: list[Resource] = Field(default_factory=list)
    next_cursor: str | None = Field(None, alias="nextCursor")
    total_count: int = Field(0)

    model_config = ConfigDict(populate_by_name=True)


class ListPromptsResponse(BaseModel):
    """Response for listing prompts."""

    prompts: list[Prompt] = Field(default_factory=list)
    next_cursor: str | None = Field(None, alias="nextCursor")
    total_count: int = Field(0)

    model_config = ConfigDict(populate_by_name=True)


class InvokeToolResponse(BaseModel):
    """Response for tool invocation."""

    result: ToolResult
    tool_name: str = Field(..., alias="toolName")
    invoked_at: datetime = Field(default_factory=lambda: datetime.utcnow())

    model_config = ConfigDict(populate_by_name=True)


class ReadResourceResponse(BaseModel):
    """Response for reading a resource."""

    contents: list[ResourceContentRead] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str = Field(..., description="Error message")
    code: str = Field("INTERNAL_ERROR", description="Error code")
    details: dict[str, Any] | None = Field(None, description="Additional error details")
    request_id: str | None = Field(None, description="Request ID for tracing")


# Update forward references
ResourceContent.model_rebuild()
