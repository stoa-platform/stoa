"""
MCP Gateway Error Snapshots - Phase 3

Captures detailed error context for MCP server failures, tool execution errors,
and LLM-related issues for time-travel debugging.
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
]
