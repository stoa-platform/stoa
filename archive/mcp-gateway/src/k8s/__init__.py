"""Kubernetes integration module for STOA MCP Gateway.

This module provides integration with Kubernetes Custom Resources
for dynamic tool registration and management.
"""

from .models import (
    ToolCR,
    ToolCRSpec,
    ToolSetCR,
    ToolSetCRSpec,
)
from .watcher import (
    ToolWatcher,
    get_tool_watcher,
    shutdown_tool_watcher,
)

__all__ = [
    # Watcher
    "ToolWatcher",
    "get_tool_watcher",
    "shutdown_tool_watcher",
    # Models
    "ToolCR",
    "ToolSetCR",
    "ToolCRSpec",
    "ToolSetCRSpec",
]
