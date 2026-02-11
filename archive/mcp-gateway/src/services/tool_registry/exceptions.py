"""Tool registry exceptions.

CAB-841: Extracted from tool_registry.py for modularity.
"""


class ToolNotFoundError(Exception):
    """Raised when a tool is not found or has been permanently removed."""

    pass
