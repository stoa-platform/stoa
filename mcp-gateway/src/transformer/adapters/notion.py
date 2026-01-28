# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Notion Lite Adapter (CAB-881 — Step 3/4).

Optimized transformation for Notion MCP tools:
- notion-search
- notion-fetch
- notion-query-database-view
- notion-get-comments

Typical reduction: ~85% on search/query payloads.
"""

from __future__ import annotations

from typing import Any

from ..base import TransformerAdapter
from ..config import TransformConfig, TruncateConfig, TruncateStrategy
from ..engine import TransformEngine


# Default config matching the ADR-015 spec
NOTION_LITE_CONFIG = TransformConfig(
    fields=[
        "id",
        "title",
        "url",
        "type",
        "parent.type",
        "parent.title",
        "lastEditedTime",
        "createdBy.name",
        "properties",
        "status",
    ],
    max_depth=3,
    max_items=20,
    truncate={
        "content": TruncateConfig(max=500, strategy=TruncateStrategy.MIDDLE),
        "rich_text": TruncateConfig(max=200, strategy=TruncateStrategy.END),
    },
)


class NotionLiteAdapter(TransformerAdapter):
    """Adapter for Notion API responses.

    Notion responses are extremely verbose with deep nesting:
    - properties contain full type metadata
    - rich_text arrays with annotation objects
    - icon/cover with full URLs
    - parent with recursive database references

    This adapter keeps only LLM-actionable fields.
    """

    def get_default_fields(self) -> list[str]:
        return NOTION_LITE_CONFIG.fields

    def get_tool_prefix(self) -> str:
        return "notion"

    def get_default_config(self) -> TransformConfig:
        return NOTION_LITE_CONFIG

    def transform(self, response: dict[str, Any], config: TransformConfig) -> dict[str, Any]:
        """Transform Notion response with property simplification.

        Notion properties are deeply nested:
        {"Name": {"type": "title", "title": [{"plain_text": "Hello"}]}}

        We simplify to:
        {"Name": "Hello"}
        """
        result = TransformEngine.apply(response, config)

        if isinstance(result, dict):
            result = self._simplify_properties(result)
        elif isinstance(result, list):
            result = [self._simplify_properties(item) if isinstance(item, dict) else item
                      for item in result]

        return result

    def _simplify_properties(self, data: dict[str, Any]) -> dict[str, Any]:
        """Simplify Notion properties to plain values."""
        props = data.get("properties")
        if not isinstance(props, dict):
            return data

        simplified = {}
        for key, prop in props.items():
            if not isinstance(prop, dict):
                simplified[key] = prop
                continue
            simplified[key] = self._extract_property_value(prop)

        data["properties"] = simplified
        return data

    def _extract_property_value(self, prop: dict[str, Any]) -> Any:
        """Extract the useful value from a Notion property object."""
        prop_type = prop.get("type", "")

        # Title: [{"plain_text": "..."}] → "..."
        if prop_type == "title":
            title_arr = prop.get("title", [])
            if isinstance(title_arr, list) and title_arr:
                return " ".join(
                    t.get("plain_text", "") for t in title_arr
                    if isinstance(t, dict)
                ).strip()
            return ""

        # Rich text: [{"plain_text": "..."}] → "..."
        if prop_type == "rich_text":
            text_arr = prop.get("rich_text", [])
            if isinstance(text_arr, list) and text_arr:
                return " ".join(
                    t.get("plain_text", "") for t in text_arr
                    if isinstance(t, dict)
                ).strip()
            return ""

        # Select: {"select": {"name": "..."}} → "..."
        if prop_type == "select":
            select = prop.get("select")
            if isinstance(select, dict):
                return select.get("name", "")
            return None

        # Multi-select: {"multi_select": [{"name": "..."}]} → ["...", ...]
        if prop_type == "multi_select":
            items = prop.get("multi_select", [])
            if isinstance(items, list):
                return [
                    i.get("name", "") for i in items
                    if isinstance(i, dict)
                ]
            return []

        # Number, checkbox, date, etc. — return raw value
        if prop_type in prop:
            return prop[prop_type]

        return prop
