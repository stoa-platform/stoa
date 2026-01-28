# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for Response Transformer (CAB-881 — Step 2/4).

Validates field selection, truncation, pagination, config validation,
and end-to-end reduction on realistic Linear/Notion fixtures.
"""

import json

import pytest
from pydantic import ValidationError

from src.transformer.config import (
    TransformConfig,
    TruncateConfig,
    TruncateStrategy,
    DEFAULT_CONFIGS,
)
from src.transformer.engine import TransformEngine
from src.transformer.registry import get_config_for_tool


# =============================================================================
# Fixtures — Realistic MCP payloads
# =============================================================================

LINEAR_ISSUE_PAYLOAD = {
    "id": "issue-uuid-123",
    "identifier": "ENG-456",
    "title": "Fix token counting bug",
    "description": "A " * 2000 + "long description that should be truncated",
    "state": {"id": "state-1", "name": "In Progress", "type": "started"},
    "priority": 2,
    "priorityLabel": "High",
    "assignee": {
        "id": "user-1",
        "name": "Alice",
        "email": "alice@example.com",
        "displayName": "Alice Wonderland",
        "avatarUrl": "https://cdn.example.com/avatars/alice.png",
    },
    "team": {
        "id": "team-1",
        "name": "Engineering",
        "key": "ENG",
        "description": "The engineering team handles all development",
    },
    "labels": [
        {"id": "label-1", "name": "bug"},
        {"id": "label-2", "name": "priority"},
    ],
    "project": {
        "id": "proj-1",
        "name": "STOA Platform",
        "slugId": "stoa-platform",
        "icon": "rocket",
    },
    "createdAt": "2026-01-20T10:00:00Z",
    "updatedAt": "2026-01-28T14:30:00Z",
    "completedAt": None,
    "canceledAt": None,
    "archivedAt": None,
    "autoClosedAt": None,
    "autoArchivedAt": None,
    "dueDate": "2026-02-01",
    "startedAt": "2026-01-22T09:00:00Z",
    "snoozedUntilAt": None,
    "sortOrder": -1234.56,
    "subIssueSortOrder": 0,
    "previousIdentifiers": [],
    "branchName": "fix/token-counting",
    "cycle": None,
    "estimate": 5,
    "url": "https://linear.app/stoa/issue/ENG-456",
    "number": 456,
    "trashed": False,
    "customerTicketCount": 0,
    "integrationSourceType": None,
    "externalUserCreator": None,
    "botActor": None,
    "parent": None,
    "slaBreachesAt": None,
    "slaStartedAt": None,
}

LINEAR_LIST_PAYLOAD = [LINEAR_ISSUE_PAYLOAD.copy() for _ in range(100)]

NOTION_PAGE_PAYLOAD = {
    "id": "page-uuid-789",
    "title": "Sprint Planning Notes",
    "status": "Active",
    "lastEditedTime": "2026-01-28T12:00:00Z",
    "createdTime": "2026-01-20T08:00:00Z",
    "url": "https://notion.so/sprint-planning",
    "content": "Detailed sprint planning notes " * 500,
    "properties": {
        "Name": {"type": "title", "title": [{"plain_text": "Sprint Planning"}]},
        "Status": {"type": "select", "select": {"name": "Active"}},
        "Assignee": {"type": "people", "people": [{"name": "Bob"}]},
    },
    "icon": {"type": "emoji", "emoji": "📋"},
    "cover": {"type": "external", "external": {"url": "https://cdn.example.com/cover.png"}},
    "parent": {"type": "database_id", "database_id": "db-uuid-1"},
    "archived": False,
    "object": "page",
}


# =============================================================================
# Config Validation (JSON Schema)
# =============================================================================


class TestTransformConfig:
    """Tests for TransformConfig Pydantic validation."""

    def test_valid_config(self):
        config = TransformConfig(
            fields=["id", "title", "status"],
            max_depth=2,
            max_items=50,
            truncate={"description": TruncateConfig(max=200, strategy=TruncateStrategy.MIDDLE)},
        )
        assert config.fields == ["id", "title", "status"]
        assert config.max_depth == 2

    def test_invalid_max_depth_too_high(self):
        with pytest.raises(ValidationError):
            TransformConfig(max_depth=99)

    def test_invalid_max_depth_zero(self):
        with pytest.raises(ValidationError):
            TransformConfig(max_depth=0)

    def test_invalid_max_items_zero(self):
        with pytest.raises(ValidationError):
            TransformConfig(max_items=0)

    def test_invalid_max_items_too_high(self):
        with pytest.raises(ValidationError):
            TransformConfig(max_items=9999)

    def test_invalid_truncate_max(self):
        with pytest.raises(ValidationError):
            TruncateConfig(max=0)

    def test_disabled_config_passthrough(self):
        config = TransformConfig(enabled=False, fields=["id"])
        data = {"id": 1, "extra": 2}
        result = TransformEngine.apply(data, config)
        assert result == data  # No transformation

    def test_default_configs_exist(self):
        assert "linear" in DEFAULT_CONFIGS
        assert "notion" in DEFAULT_CONFIGS

    def test_config_from_dict(self):
        raw = {
            "fields": ["id", "title"],
            "max_depth": 2,
            "truncate": {
                "description": {"max": 200, "strategy": "middle"},
            },
        }
        config = TransformConfig(**raw)
        assert config.truncate["description"].max == 200
        assert config.truncate["description"].strategy == TruncateStrategy.MIDDLE


# =============================================================================
# Field Selection
# =============================================================================


class TestFieldSelection:
    """Tests for whitelist-based field selection."""

    def test_simple_whitelist(self):
        data = {"id": 1, "title": "Test", "secret": "hidden", "extra": "gone"}
        result = TransformEngine.select_fields(data, ["id", "title"], max_depth=3)
        assert result == {"id": 1, "title": "Test"}

    def test_empty_whitelist_returns_empty(self):
        data = {"id": 1, "title": "Test"}
        result = TransformEngine.select_fields(data, [], max_depth=3)
        assert result == {}

    def test_nested_dot_notation(self):
        data = {
            "assignee": {
                "id": "u1",
                "name": "Alice",
                "email": "alice@example.com",
            },
            "title": "Test",
        }
        result = TransformEngine.select_fields(
            data, ["title", "assignee.name"], max_depth=3
        )
        assert result == {"title": "Test", "assignee": {"name": "Alice"}}

    def test_array_of_objects(self):
        data = [
            {"id": 1, "name": "A", "secret": "x"},
            {"id": 2, "name": "B", "secret": "y"},
        ]
        result = TransformEngine.select_fields(data, ["id", "name"], max_depth=3)
        assert result == [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]

    def test_max_depth_stops_recursion(self):
        data = {
            "level1": {
                "level2": {
                    "level3": {"deep": "value"},
                },
            },
        }
        result = TransformEngine.select_fields(data, ["level1"], max_depth=1)
        # At depth 1, level1 is included as-is (no further filtering)
        assert "level1" in result

    def test_missing_fields_ignored(self):
        data = {"id": 1}
        result = TransformEngine.select_fields(data, ["id", "nonexistent"], max_depth=3)
        assert result == {"id": 1}

    def test_linear_fixture_reduction(self):
        """Linear issue payload reduced to essential fields."""
        config = DEFAULT_CONFIGS["linear"]
        result = TransformEngine.select_fields(
            LINEAR_ISSUE_PAYLOAD, config.fields, config.max_depth
        )
        # Should only contain whitelisted fields
        assert set(result.keys()).issubset(set(config.fields))
        assert "id" in result
        assert "title" in result
        assert "state" in result
        # Removed fields
        assert "sortOrder" not in result
        assert "previousIdentifiers" not in result
        assert "trashed" not in result
        assert "customerTicketCount" not in result


# =============================================================================
# Truncation
# =============================================================================


class TestTruncation:
    """Tests for intelligent text truncation."""

    def test_short_text_unchanged(self):
        result = TransformEngine.truncate_text(
            "short", TruncateConfig(max=100)
        )
        assert result == "short"

    def test_end_strategy(self):
        text = "a" * 200
        result = TransformEngine.truncate_text(
            text, TruncateConfig(max=50, strategy=TruncateStrategy.END)
        )
        assert result.startswith("a" * 50)
        assert "[...truncated 150 chars...]" in result
        assert len(result) < len(text)

    def test_middle_strategy(self):
        text = "START" + "x" * 1000 + "END"
        result = TransformEngine.truncate_text(
            text, TruncateConfig(max=100, strategy=TruncateStrategy.MIDDLE)
        )
        assert result.startswith("START")
        assert result.endswith("END")
        assert "[...truncated" in result

    def test_truncate_in_dict(self):
        data = {"description": "a" * 1000, "title": "Short"}
        config = {"description": TruncateConfig(max=100)}
        result = TransformEngine.truncate_fields(data, config)
        assert len(result["description"]) < 1000
        assert result["title"] == "Short"

    def test_truncate_nested(self):
        data = {"item": {"description": "a" * 500}}
        config = {"description": TruncateConfig(max=50)}
        result = TransformEngine.truncate_fields(data, config)
        assert len(result["item"]["description"]) < 500

    def test_truncate_in_array(self):
        data = [{"description": "a" * 500}, {"description": "b" * 500}]
        config = {"description": TruncateConfig(max=50)}
        result = TransformEngine.truncate_fields(data, config)
        assert all(len(item["description"]) < 500 for item in result)

    def test_linear_description_truncation(self):
        config = DEFAULT_CONFIGS["linear"]
        result = TransformEngine.truncate_fields(
            LINEAR_ISSUE_PAYLOAD, config.truncate
        )
        assert len(result["description"]) < len(LINEAR_ISSUE_PAYLOAD["description"])
        assert "[...truncated" in result["description"]


# =============================================================================
# Pagination
# =============================================================================


class TestPagination:
    """Tests for automatic array pagination."""

    def test_small_array_unchanged(self):
        data = {"items": [1, 2, 3]}
        result = TransformEngine.paginate_arrays(data, max_items=50)
        assert result == {"items": [1, 2, 3]}

    def test_large_array_paginated(self):
        data = {"results": list(range(100))}
        result = TransformEngine.paginate_arrays(data, max_items=10)
        assert len(result["results"]["items"]) == 10
        assert result["results"]["_pagination"]["total"] == 100
        assert result["results"]["_pagination"]["returned"] == 10
        assert result["results"]["_pagination"]["has_more"] is True

    def test_top_level_array_paginated(self):
        data = list(range(200))
        result = TransformEngine.paginate_arrays(data, max_items=20)
        assert isinstance(result, dict)
        assert len(result["items"]) == 20
        assert result["_pagination"]["total"] == 200

    def test_nested_array_paginated(self):
        data = {"level1": {"results": list(range(100))}}
        result = TransformEngine.paginate_arrays(data, max_items=5)
        assert result["level1"]["results"]["_pagination"]["total"] == 100

    def test_linear_list_pagination(self):
        result = TransformEngine.paginate_arrays(LINEAR_LIST_PAYLOAD, max_items=20)
        assert isinstance(result, dict)
        assert len(result["items"]) == 20
        assert result["_pagination"]["total"] == 100


# =============================================================================
# Full Pipeline (apply)
# =============================================================================


class TestFullPipeline:
    """Tests for the complete transformation pipeline."""

    def test_linear_issue_70_pct_reduction(self):
        """DoD: payload reduced > 70%."""
        config = DEFAULT_CONFIGS["linear"]
        original = json.dumps(LINEAR_ISSUE_PAYLOAD)
        transformed = TransformEngine.apply(LINEAR_ISSUE_PAYLOAD, config)
        transformed_str = json.dumps(transformed, separators=(",", ":"))

        original_size = len(original)
        transformed_size = len(transformed_str)
        reduction = 1 - (transformed_size / original_size)

        assert reduction > 0.70, (
            f"Expected >70% reduction, got {reduction * 100:.1f}% "
            f"(original={original_size}, transformed={transformed_size})"
        )

    def test_linear_list_reduction(self):
        """List of 100 issues reduced via pagination + field selection."""
        config = DEFAULT_CONFIGS["linear"]
        original = json.dumps(LINEAR_LIST_PAYLOAD)
        transformed = TransformEngine.apply(LINEAR_LIST_PAYLOAD, config)
        transformed_str = json.dumps(transformed, separators=(",", ":"))

        original_size = len(original)
        transformed_size = len(transformed_str)
        reduction = 1 - (transformed_size / original_size)

        assert reduction > 0.70, (
            f"Expected >70% reduction on list, got {reduction * 100:.1f}%"
        )

    def test_notion_page_reduction(self):
        """Notion page reduced via field selection + truncation."""
        config = DEFAULT_CONFIGS["notion"]
        original = json.dumps(NOTION_PAGE_PAYLOAD)
        transformed = TransformEngine.apply(NOTION_PAGE_PAYLOAD, config)
        transformed_str = json.dumps(transformed, separators=(",", ":"))

        original_size = len(original)
        transformed_size = len(transformed_str)
        reduction = 1 - (transformed_size / original_size)

        assert reduction > 0.50, (
            f"Expected >50% reduction on Notion, got {reduction * 100:.1f}%"
        )

    def test_disabled_config_no_transform(self):
        config = TransformConfig(enabled=False)
        result = TransformEngine.apply(LINEAR_ISSUE_PAYLOAD, config)
        assert result == LINEAR_ISSUE_PAYLOAD

    def test_empty_fields_no_field_selection(self):
        config = TransformConfig(fields=[], max_items=1000)
        result = TransformEngine.apply({"a": 1, "b": 2}, config)
        assert result == {"a": 1, "b": 2}

    def test_mcp_envelope_transformation(self):
        """MCP tool response envelope: content[].text is transformed."""
        from src.middleware.response_transformer import ResponseTransformerMiddleware

        middleware = ResponseTransformerMiddleware(app=None)
        config = TransformConfig(fields=["id", "title"])
        inner = {"id": 1, "title": "Test", "secret": "hidden"}
        payload = {
            "content": [
                {"type": "text", "text": json.dumps(inner)},
            ],
            "isError": False,
        }

        result = middleware._transform_response(payload, "test-tool", config)
        inner_result = json.loads(result["content"][0]["text"])
        assert inner_result == {"id": 1, "title": "Test"}
        assert "secret" not in inner_result


# =============================================================================
# Config Registry
# =============================================================================


class TestConfigRegistry:
    """Tests for tool→config resolution."""

    def test_linear_tool_matches_default(self):
        config = get_config_for_tool("linear-list-issues")
        assert config is not None
        assert "id" in config.fields

    def test_notion_tool_matches_default(self):
        config = get_config_for_tool("notion-search")
        assert config is not None

    def test_unknown_tool_returns_none(self):
        config = get_config_for_tool("unknown-tool-xyz")
        assert config is None

    def test_tenant_config_overrides_default(self):
        tenant_config = {
            "linear": TransformConfig(fields=["id", "title"]),
        }
        config = get_config_for_tool("linear-get-issue", tenant_config)
        assert config.fields == ["id", "title"]
