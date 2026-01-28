# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tool registry singleton management.

CAB-841: Extracted from tool_registry.py for modularity.
Provides singleton access to the ToolRegistry instance.
"""

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from . import ToolRegistry

logger = structlog.get_logger(__name__)

# Singleton instance
_registry: "ToolRegistry | None" = None


async def get_tool_registry() -> "ToolRegistry":
    """Get the tool registry singleton."""
    global _registry
    if _registry is None:
        # Import here to avoid circular imports
        from . import ToolRegistry
        _registry = ToolRegistry()
        await _registry.startup()
    return _registry


async def shutdown_tool_registry() -> None:
    """Shutdown the tool registry."""
    global _registry
    if _registry:
        await _registry.shutdown()
        _registry = None
