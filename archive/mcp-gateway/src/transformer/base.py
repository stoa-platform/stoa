# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""TransformerAdapter abstract base class (CAB-881).

Each MCP tool source (Linear, Notion, GitHub, etc.) implements this
interface to declare its default fields and optional custom transform logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .config import TransformConfig


class TransformerAdapter(ABC):
    """Abstract adapter for tool-specific response transformation.

    Implementations:
    - Declare default fields for the tool (used when no tenant config exists)
    - Optionally override transform() for source-specific normalization

    Example:
        class LinearAdapter(TransformerAdapter):
            def get_default_fields(self) -> list[str]:
                return ["id", "title", "state", "priority", "assignee"]

            def get_tool_prefix(self) -> str:
                return "linear"
    """

    @abstractmethod
    def get_default_fields(self) -> list[str]:
        """Return the default whitelist of fields for this tool.

        Used when the tenant has no custom transform config.
        Should include only fields that are generally useful for LLM consumption.
        """
        ...

    @abstractmethod
    def get_tool_prefix(self) -> str:
        """Return the tool prefix for matching (e.g. 'linear', 'notion').

        Used to match tool_name against this adapter.
        A tool_name like 'linear-list-issues' matches prefix 'linear'.
        """
        ...

    def transform(self, response: dict[str, Any], config: TransformConfig) -> dict[str, Any]:
        """Optional: override for source-specific transformation.

        Default implementation delegates to TransformEngine.
        Override this for custom normalization (e.g., flattening nested structures).
        """
        from .engine import TransformEngine
        return TransformEngine.apply(response, config)
