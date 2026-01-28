# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Linear Lite Adapter (CAB-881 — Step 3/4).

Optimized transformation for Linear MCP tools:
- list_issues (most verbose — primary target)
- get_issue
- list_projects
- search_issues

Typical reduction: ~85% on list_issues payloads.
"""

from __future__ import annotations

from typing import Any

from ..base import TransformerAdapter
from ..config import TransformConfig, TruncateConfig, TruncateStrategy
from ..engine import TransformEngine


# Default config matching the ADR-015 spec
LINEAR_LITE_CONFIG = TransformConfig(
    fields=[
        "id",
        "identifier",
        "title",
        "state.name",
        "state.type",
        "priority",
        "assignee.name",
        "project.name",
        "labels",
        "updatedAt",
        "url",
    ],
    max_depth=2,
    max_items=25,
    truncate={
        "description": TruncateConfig(max=300, strategy=TruncateStrategy.MIDDLE),
    },
)


class LinearLiteAdapter(TransformerAdapter):
    """Adapter for Linear API responses.

    Strips heavy fields like sortOrder, previousIdentifiers, cycle,
    botActor, externalUserCreator, etc. Keeps only what LLMs need
    to understand and act on issues.
    """

    def get_default_fields(self) -> list[str]:
        return LINEAR_LITE_CONFIG.fields

    def get_tool_prefix(self) -> str:
        return "linear"

    def get_default_config(self) -> TransformConfig:
        return LINEAR_LITE_CONFIG

    def transform(self, response: dict[str, Any], config: TransformConfig) -> dict[str, Any]:
        """Transform Linear response with special handling for nested structures.

        Linear API returns deeply nested objects (state, assignee, team, project)
        where only a few fields are useful. This adapter also handles:
        - Null assignee/project (common for backlog items)
        - Labels array (keep name only)
        - State flattening (name + type only)
        """
        # Apply standard transformation first
        result = TransformEngine.apply(response, config)

        # Post-process: flatten labels to names only (if present and not already filtered)
        if isinstance(result, dict):
            result = self._flatten_labels(result)
        elif isinstance(result, list):
            result = [self._flatten_labels(item) if isinstance(item, dict) else item
                      for item in result]

        return result

    def _flatten_labels(self, data: dict[str, Any]) -> dict[str, Any]:
        """Flatten labels from [{id, name, ...}] to [name, ...]."""
        labels = data.get("labels")
        if isinstance(labels, list):
            data["labels"] = [
                label.get("name", label) if isinstance(label, dict) else label
                for label in labels
            ]
        return data
