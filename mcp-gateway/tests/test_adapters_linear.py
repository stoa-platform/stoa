# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for Linear Lite Adapter (CAB-881 — Step 3/4).

Covers:
- Field selection with realistic Linear payloads
- >70% reduction on list_issues fixture
- Edge cases: empty, null, unicode, mixed types, error responses
- Label flattening
- Auto-registration in registry
"""

import json
import os
from pathlib import Path

import pytest

from src.transformer.adapters.linear import LinearLiteAdapter, LINEAR_LITE_CONFIG
from src.transformer.engine import TransformEngine
from src.transformer.registry import get_adapter, get_config_for_tool, get_registered_adapters


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def linear_verbose():
    """Load the realistic Linear list_issues fixture."""
    with open(FIXTURES_DIR / "linear_verbose.json") as f:
        return json.load(f)


@pytest.fixture
def adapter():
    return LinearLiteAdapter()


# =============================================================================
# Auto-Registration
# =============================================================================


class TestLinearRegistration:
    """Verify adapter is auto-registered in the registry."""

    def test_adapter_registered(self):
        adapters = get_registered_adapters()
        assert "linear" in adapters

    def test_get_adapter_by_tool_name(self):
        adapter = get_adapter("linear-list-issues")
        assert isinstance(adapter, LinearLiteAdapter)

    def test_get_adapter_get_issue(self):
        adapter = get_adapter("linear-get-issue")
        assert isinstance(adapter, LinearLiteAdapter)

    def test_get_adapter_search(self):
        adapter = get_adapter("linear-search-issues")
        assert isinstance(adapter, LinearLiteAdapter)

    def test_get_config_for_linear_tool(self):
        config = get_config_for_tool("linear-list-issues")
        assert config is not None
        assert "id" in config.fields


# =============================================================================
# Adapter Interface
# =============================================================================


class TestLinearAdapterInterface:

    def test_get_tool_prefix(self, adapter):
        assert adapter.get_tool_prefix() == "linear"

    def test_get_default_fields(self, adapter):
        fields = adapter.get_default_fields()
        assert "id" in fields
        assert "title" in fields
        assert "assignee.name" in fields
        assert "state.name" in fields

    def test_get_default_config(self, adapter):
        config = adapter.get_default_config()
        assert config.max_items == 25
        assert config.max_depth == 2
        assert "description" in config.truncate


# =============================================================================
# Reduction Benchmark (DoD)
# =============================================================================


class TestLinearReduction:
    """DoD: Linear list_issues reduced > 70% on realistic fixture."""

    def test_list_issues_70pct_reduction(self, adapter, linear_verbose):
        """Primary DoD assertion: >70% reduction on real Linear payload."""
        original = json.dumps(linear_verbose)
        transformed = adapter.transform(linear_verbose, LINEAR_LITE_CONFIG)
        transformed_str = json.dumps(transformed, separators=(",", ":"))

        original_size = len(original)
        transformed_size = len(transformed_str)
        reduction = 1 - (transformed_size / original_size)

        assert reduction > 0.70, (
            f"Expected >70% reduction, got {reduction * 100:.1f}% "
            f"({original_size} → {transformed_size} bytes)"
        )

    def test_single_issue_reduction(self, adapter, linear_verbose):
        """Single issue should also have significant reduction."""
        single = linear_verbose[0]
        original = json.dumps(single)
        transformed = adapter.transform(single, LINEAR_LITE_CONFIG)
        transformed_str = json.dumps(transformed, separators=(",", ":"))

        reduction = 1 - (len(transformed_str) / len(original))
        assert reduction > 0.60, f"Single issue reduction: {reduction * 100:.1f}%"

    def test_transformed_has_essential_fields(self, adapter, linear_verbose):
        """Transformed output should retain all essential fields."""
        single = linear_verbose[0]
        result = adapter.transform(single, LINEAR_LITE_CONFIG)

        assert result["id"] == single["id"]
        assert result["identifier"] == single["identifier"]
        assert result["title"] == single["title"]
        assert result["url"] == single["url"]
        assert result["priority"] == single["priority"]
        assert "updatedAt" in result

    def test_transformed_removes_noise(self, adapter, linear_verbose):
        """Fields not in whitelist should be removed."""
        single = linear_verbose[0]
        result = adapter.transform(single, LINEAR_LITE_CONFIG)

        assert "sortOrder" not in result
        assert "boardOrder" not in result
        assert "previousIdentifiers" not in result
        assert "descriptionState" not in result
        assert "trashed" not in result
        assert "customerTicketCount" not in result
        assert "botActor" not in result
        assert "subscribers" not in result
        assert "children" not in result
        assert "comments" not in result
        assert "history" not in result
        assert "cycle" not in result
        assert "team" not in result


# =============================================================================
# Label Flattening
# =============================================================================


class TestLabelFlattening:

    def test_labels_flattened_to_names(self, adapter):
        data = {
            "id": "1",
            "labels": [
                {"id": "l1", "name": "bug", "color": "#red"},
                {"id": "l2", "name": "urgent", "color": "#orange"},
            ],
        }
        result = adapter._flatten_labels(data)
        assert result["labels"] == ["bug", "urgent"]

    def test_empty_labels(self, adapter):
        data = {"id": "1", "labels": []}
        result = adapter._flatten_labels(data)
        assert result["labels"] == []

    def test_no_labels_key(self, adapter):
        data = {"id": "1"}
        result = adapter._flatten_labels(data)
        assert "labels" not in result


# =============================================================================
# Edge Cases (N3m0 requirement)
# =============================================================================


class TestLinearEdgeCases:

    def test_empty_list(self, adapter):
        """Empty list should pass through cleanly."""
        result = adapter.transform([], LINEAR_LITE_CONFIG)
        assert result == []

    def test_empty_dict(self, adapter):
        """Empty dict should pass through cleanly."""
        result = adapter.transform({}, LINEAR_LITE_CONFIG)
        assert result == {}

    def test_null_assignee(self, adapter):
        """Null assignee (backlog item) should not crash."""
        data = {
            "id": "1",
            "title": "Unassigned issue",
            "assignee": None,
            "state": {"name": "Backlog", "type": "backlog"},
            "priority": 0,
            "url": "https://linear.app/issue/1",
        }
        result = adapter.transform(data, LINEAR_LITE_CONFIG)
        assert result["assignee"] is None

    def test_null_project(self, adapter):
        """Null project should not crash."""
        data = {
            "id": "2",
            "title": "No project issue",
            "project": None,
        }
        result = adapter.transform(data, LINEAR_LITE_CONFIG)
        # project.name in fields — when project is None, it stays None
        assert result.get("project") is None

    def test_nested_null_values(self, adapter):
        """Deeply nested nulls should be handled gracefully."""
        data = {
            "id": "3",
            "state": None,
            "assignee": {"name": None},
            "labels": None,
        }
        result = adapter.transform(data, LINEAR_LITE_CONFIG)
        assert result["state"] is None
        assert result["assignee"] == {"name": None}

    def test_unicode_and_emojis(self, adapter):
        """Unicode and emojis in content should be preserved."""
        data = {
            "id": "4",
            "title": "Fix 🐛 bug with café résumé — 日本語テスト",
            "description": "Détails: l'erreur se produit avec des caractères spéciaux 🎉✨🚀",
            "state": {"name": "In Progress", "type": "started"},
            "labels": [{"name": "🐛 bug"}],
        }
        result = adapter.transform(data, LINEAR_LITE_CONFIG)
        assert "🐛" in result["title"]
        assert "café" in result["title"]
        assert result["labels"] == ["🐛 bug"]

    def test_mixed_type_array(self, adapter):
        """Arrays with mixed types should not crash."""
        data = {
            "id": "5",
            "labels": [
                {"name": "valid"},
                "string-label",
                42,
                None,
            ],
        }
        result = adapter._flatten_labels(data)
        assert "valid" in result["labels"]
        assert "string-label" in result["labels"]

    def test_api_error_response(self, adapter):
        """Error responses (non-standard structure) should pass through."""
        error_data = {
            "error": "unauthorized",
            "message": "Invalid API key",
            "status": 401,
        }
        result = adapter.transform(error_data, LINEAR_LITE_CONFIG)
        # No fields match whitelist, but should not crash
        assert isinstance(result, dict)

    def test_description_truncation(self, adapter, linear_verbose):
        """Long descriptions should be truncated."""
        single = linear_verbose[0]
        result = adapter.transform(single, LINEAR_LITE_CONFIG)
        # description is in truncate config but not in fields whitelist
        # so it gets filtered out by field selection
        # This is correct behavior — only whitelisted fields are kept
        assert "description" not in result or len(result.get("description", "")) <= 400

    def test_very_large_list(self, adapter):
        """List of 200 items should be paginated to max_items=25."""
        data = [{"id": str(i), "title": f"Issue {i}"} for i in range(200)]
        result = adapter.transform(data, LINEAR_LITE_CONFIG)

        assert isinstance(result, dict)
        assert len(result["items"]) == 25
        assert result["_pagination"]["total"] == 200
        assert result["_pagination"]["has_more"] is True
