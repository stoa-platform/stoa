# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tool registry exceptions.

CAB-841: Extracted from tool_registry.py for modularity.
"""


class ToolNotFoundError(Exception):
    """Raised when a tool is not found or has been permanently removed."""

    pass
