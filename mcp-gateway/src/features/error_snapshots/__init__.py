"""
MCP Gateway Error Snapshots - Phase 3 & 4

Captures detailed error context for MCP server failures, tool execution errors,
and LLM-related issues for time-travel debugging.

Phase 3: Core capture, masking, Kafka publishing
Phase 4: Database persistence, REST API, Console UI
"""

from .models import (
    MCPErrorSnapshot,
    MCPServerContext,
    ToolInvocation,
    LLMContext,
    RetryContext,
    MCPErrorType,
)
from .capture import capture_mcp_error, capture_tool_error
from .middleware import MCPErrorSnapshotMiddleware
from .config import MCPSnapshotSettings, get_mcp_snapshot_settings
from .router import router as snapshots_router

__all__ = [
    # Models
    "MCPErrorSnapshot",
    "MCPServerContext",
    "ToolInvocation",
    "LLMContext",
    "RetryContext",
    "MCPErrorType",
    # Capture functions
    "capture_mcp_error",
    "capture_tool_error",
    # Middleware
    "MCPErrorSnapshotMiddleware",
    # Config
    "MCPSnapshotSettings",
    "get_mcp_snapshot_settings",
    # Router (Phase 4)
    "snapshots_router",
]
