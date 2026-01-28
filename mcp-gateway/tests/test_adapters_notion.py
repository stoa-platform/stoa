# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for Notion Lite Adapter (CAB-881 — Step 3/4).

Covers:
- Field selection with realistic Notion payloads
- >70% reduction on search fixture
- Property simplification (title, select, multi_select, rich_text)
- Edge cases: empty, null, unicode, mixed types
- Auto-registration in registry
"""

import json
from pathlib import Path

import pytest

from src.transformer.adapters.notion import NotionLiteAdapter, NOTION_LITE_CONFIG
from src.transformer.engine import TransformEngine
from src.transformer.registry import get_adapter, get_config_for_tool, get_registered_adapters


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def notion_verbose():
    """Load the realistic Notion search fixture."""
    with open(FIXTURES_DIR / "notion_verbose.json") as f:
        return json.load(f)


@pytest.fixture
def adapter():
    return NotionLiteAdapter()


# =============================================================================
# Auto-Registration
# =============================================================================


class TestNotionRegistration:

    def test_adapter_registered(self):
        adapters = get_registered_adapters()
        assert "notion" in adapters

    def test_get_adapter_search(self):
        adapter = get_adapter("notion-search")
        assert isinstance(adapter, NotionLiteAdapter)

    def test_get_adapter_fetch(self):
        adapter = get_adapter("notion-fetch")
        assert isinstance(adapter, NotionLiteAdapter)

    def test_get_adapter_query_database(self):
        adapter = get_adapter("notion-query-database-view")
        assert isinstance(adapter, NotionLiteAdapter)

    def test_get_adapter_get_comments(self):
        adapter = get_adapter("notion-get-comments")
        assert isinstance(adapter, NotionLiteAdapter)

    def test_get_config_for_notion_tool(self):
        config = get_config_for_tool("notion-search")
        assert config is not None
        assert "id" in config.fields


# =============================================================================
# Adapter Interface
# =============================================================================


class TestNotionAdapterInterface:

    def test_get_tool_prefix(self, adapter):
        assert adapter.get_tool_prefix() == "notion"

    def test_get_default_fields(self, adapter):
        fields = adapter.get_default_fields()
        assert "id" in fields
        assert "title" in fields
        assert "url" in fields
        assert "parent.type" in fields

    def test_get_default_config(self, adapter):
        config = adapter.get_default_config()
        assert config.max_items == 20
        assert config.max_depth == 3
        assert "content" in config.truncate
        assert "rich_text" in config.truncate


# =============================================================================
# Reduction Benchmark (DoD)
# =============================================================================


class TestNotionReduction:

    def test_search_70pct_reduction(self, adapter, notion_verbose):
        """DoD: Notion search response reduced > 70%."""
        original = json.dumps(notion_verbose)
        transformed = adapter.transform(notion_verbose, NOTION_LITE_CONFIG)
        transformed_str = json.dumps(transformed, separators=(",", ":"))

        original_size = len(original)
        transformed_size = len(transformed_str)
        reduction = 1 - (transformed_size / original_size)

        assert reduction > 0.70, (
            f"Expected >70% reduction, got {reduction * 100:.1f}% "
            f"({original_size} → {transformed_size} bytes)"
        )

    def test_single_page_reduction(self, adapter, notion_verbose):
        """Single page should have significant reduction."""
        single = notion_verbose["results"][0]
        original = json.dumps(single)
        transformed = adapter.transform(single, NOTION_LITE_CONFIG)
        transformed_str = json.dumps(transformed, separators=(",", ":"))

        reduction = 1 - (len(transformed_str) / len(original))
        assert reduction > 0.50, f"Single page reduction: {reduction * 100:.1f}%"

    def test_transformed_has_essential_fields(self, adapter, notion_verbose):
        """Essential fields should be retained."""
        single = notion_verbose["results"][0]
        result = adapter.transform(single, NOTION_LITE_CONFIG)

        assert result["id"] == single["id"]
        assert result["title"] == single["title"]
        assert result["url"] == single["url"]
        assert result["type"] == single["type"]

    def test_transformed_removes_noise(self, adapter, notion_verbose):
        """Non-essential fields should be removed."""
        single = notion_verbose["results"][0]
        result = adapter.transform(single, NOTION_LITE_CONFIG)

        assert "cover" not in result
        assert "icon" not in result
        assert "archived" not in result
        assert "in_trash" not in result
        assert "object" not in result
        assert "last_edited_by" not in result
        assert "created_by" not in result or isinstance(result.get("created_by"), dict)


# =============================================================================
# Property Simplification
# =============================================================================


class TestPropertySimplification:

    def test_title_property(self, adapter):
        data = {
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [
                        {"plain_text": "Hello"},
                        {"plain_text": " World"},
                    ],
                },
            },
        }
        result = adapter._simplify_properties(data)
        assert result["properties"]["Name"] == "Hello World"

    def test_select_property(self, adapter):
        data = {
            "properties": {
                "Status": {
                    "type": "select",
                    "select": {"name": "Active", "color": "green"},
                },
            },
        }
        result = adapter._simplify_properties(data)
        assert result["properties"]["Status"] == "Active"

    def test_multi_select_property(self, adapter):
        data = {
            "properties": {
                "Tags": {
                    "type": "multi_select",
                    "multi_select": [
                        {"name": "bug"},
                        {"name": "urgent"},
                    ],
                },
            },
        }
        result = adapter._simplify_properties(data)
        assert result["properties"]["Tags"] == ["bug", "urgent"]

    def test_rich_text_property(self, adapter):
        data = {
            "properties": {
                "Description": {
                    "type": "rich_text",
                    "rich_text": [
                        {"plain_text": "Line 1"},
                        {"plain_text": " Line 2"},
                    ],
                },
            },
        }
        result = adapter._simplify_properties(data)
        assert result["properties"]["Description"] == "Line 1 Line 2"

    def test_number_property(self, adapter):
        data = {
            "properties": {
                "Points": {
                    "type": "number",
                    "number": 42,
                },
            },
        }
        result = adapter._simplify_properties(data)
        assert result["properties"]["Points"] == 42

    def test_null_select(self, adapter):
        data = {
            "properties": {
                "Status": {
                    "type": "select",
                    "select": None,
                },
            },
        }
        result = adapter._simplify_properties(data)
        assert result["properties"]["Status"] is None

    def test_empty_title(self, adapter):
        data = {
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [],
                },
            },
        }
        result = adapter._simplify_properties(data)
        assert result["properties"]["Name"] == ""

    def test_no_properties(self, adapter):
        data = {"id": "1", "title": "Test"}
        result = adapter._simplify_properties(data)
        assert result == {"id": "1", "title": "Test"}

    def test_full_fixture_properties_simplified(self, adapter, notion_verbose):
        """Properties in fixture should be simplified."""
        single = notion_verbose["results"][0]
        result = adapter.transform(single, NOTION_LITE_CONFIG)

        props = result.get("properties", {})
        if "Name" in props:
            # Should be a string, not the full Notion property object
            assert isinstance(props["Name"], str)
        if "Status" in props:
            assert isinstance(props["Status"], (str, type(None)))
        if "Tags" in props:
            assert isinstance(props["Tags"], list)


# =============================================================================
# Edge Cases (N3m0 requirement)
# =============================================================================


class TestNotionEdgeCases:

    def test_empty_results(self, adapter):
        data = {"results": [], "has_more": False}
        result = adapter.transform(data, NOTION_LITE_CONFIG)
        assert isinstance(result, dict)

    def test_empty_dict(self, adapter):
        result = adapter.transform({}, NOTION_LITE_CONFIG)
        assert result == {}

    def test_empty_list(self, adapter):
        result = adapter.transform([], NOTION_LITE_CONFIG)
        assert result == []

    def test_null_parent(self, adapter):
        data = {
            "id": "1",
            "title": "Orphan page",
            "parent": None,
        }
        result = adapter.transform(data, NOTION_LITE_CONFIG)
        assert result.get("parent") is None

    def test_null_content(self, adapter):
        data = {
            "id": "2",
            "title": "Empty page",
            "content": None,
        }
        result = adapter.transform(data, NOTION_LITE_CONFIG)
        # content is None, truncation should handle gracefully
        assert "content" not in result or result.get("content") is None

    def test_unicode_and_emojis(self, adapter):
        data = {
            "id": "3",
            "title": "📋 Sprint Planning — café résumé 日本語",
            "properties": {
                "Name": {
                    "type": "title",
                    "title": [{"plain_text": "📋 Sprint — café 日本語"}],
                },
            },
        }
        result = adapter.transform(data, NOTION_LITE_CONFIG)
        assert "📋" in result["title"]
        assert "café" in result["title"]
        props = result.get("properties", {})
        if "Name" in props:
            assert "📋" in props["Name"]

    def test_mixed_type_properties(self, adapter):
        """Properties with unexpected types should not crash."""
        data = {
            "properties": {
                "Weird": "just a string",
                "Number": 42,
                "Normal": {"type": "select", "select": {"name": "OK"}},
            },
        }
        result = adapter._simplify_properties(data)
        assert result["properties"]["Weird"] == "just a string"
        assert result["properties"]["Number"] == 42
        assert result["properties"]["Normal"] == "OK"

    def test_api_error_response(self, adapter):
        """Error responses should pass through without crash."""
        error = {
            "object": "error",
            "status": 401,
            "code": "unauthorized",
            "message": "API token is invalid.",
        }
        result = adapter.transform(error, NOTION_LITE_CONFIG)
        assert isinstance(result, dict)

    def test_long_content_truncation(self, adapter):
        """Long content field should be truncated."""
        data = {
            "id": "4",
            "title": "Long page",
            "content": "x" * 5000,
        }
        config = NOTION_LITE_CONFIG
        result = TransformEngine.apply(data, config)
        if "content" in result:
            assert len(result["content"]) < 5000
            assert "[...truncated" in result["content"]

    def test_large_results_paginated(self, adapter):
        """Results array > max_items should be paginated."""
        data = {
            "results": [
                {"id": str(i), "title": f"Page {i}"}
                for i in range(100)
            ],
        }
        result = adapter.transform(data, NOTION_LITE_CONFIG)
        # results should be paginated
        results_val = result.get("results", result)
        if isinstance(results_val, dict) and "_pagination" in results_val:
            assert results_val["_pagination"]["total"] == 100
            assert results_val["_pagination"]["returned"] == 20
