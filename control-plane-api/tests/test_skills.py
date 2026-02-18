"""Tests for Skills CRUD + CSS cascade resolution (CAB-1314)."""

import pytest
from pydantic import ValidationError

from src.models.skill import SkillScope
from src.repositories.skill import SCOPE_SPECIFICITY
from src.schemas.skill import ResolvedSkillResponse, SkillCreate, SkillListResponse, SkillResponse, SkillUpdate

# ============================================================================
# Model tests
# ============================================================================


class TestSkillScope:
    def test_enum_values(self) -> None:
        assert SkillScope.GLOBAL == "global"
        assert SkillScope.TENANT == "tenant"
        assert SkillScope.TOOL == "tool"
        assert SkillScope.USER == "user"

    def test_enum_count(self) -> None:
        assert len(SkillScope) == 4


# ============================================================================
# Schema tests
# ============================================================================


class TestSkillCreate:
    def test_defaults(self) -> None:
        s = SkillCreate(name="test-skill")
        assert s.scope == SkillScope.TENANT
        assert s.priority == 50
        assert s.enabled is True
        assert s.tool_ref is None
        assert s.user_ref is None

    def test_full_create(self) -> None:
        s = SkillCreate(
            name="coding-style",
            description="Python coding conventions",
            scope=SkillScope.TOOL,
            priority=80,
            instructions="Always use type hints.",
            tool_ref="code-review",
            enabled=True,
        )
        assert s.name == "coding-style"
        assert s.scope == SkillScope.TOOL
        assert s.priority == 80

    def test_name_min_length(self) -> None:
        with pytest.raises(ValidationError):
            SkillCreate(name="")

    def test_name_max_length(self) -> None:
        with pytest.raises(ValidationError):
            SkillCreate(name="x" * 256)

    def test_priority_range_low(self) -> None:
        with pytest.raises(ValidationError):
            SkillCreate(name="test", priority=-1)

    def test_priority_range_high(self) -> None:
        with pytest.raises(ValidationError):
            SkillCreate(name="test", priority=101)


class TestSkillUpdate:
    def test_all_optional(self) -> None:
        s = SkillUpdate()
        d = s.model_dump(exclude_unset=True)
        assert d == {}

    def test_partial_update(self) -> None:
        s = SkillUpdate(priority=75, enabled=False)
        d = s.model_dump(exclude_unset=True)
        assert d == {"priority": 75, "enabled": False}


class TestSkillResponse:
    def test_from_attributes(self) -> None:
        assert SkillResponse.model_config.get("from_attributes") is True


class TestSkillListResponse:
    def test_structure(self) -> None:
        resp = SkillListResponse(items=[], total=0)
        assert resp.items == []
        assert resp.total == 0


class TestResolvedSkillResponse:
    def test_resolved_fields(self) -> None:
        r = ResolvedSkillResponse(
            name="test",
            scope=SkillScope.TOOL,
            priority=80,
            instructions="Do things.",
            specificity=2,
        )
        assert r.specificity == 2
        assert r.scope == SkillScope.TOOL


# ============================================================================
# Cascade specificity tests
# ============================================================================


class TestCascadeSpecificity:
    def test_specificity_ordering(self) -> None:
        assert SCOPE_SPECIFICITY[SkillScope.GLOBAL] < SCOPE_SPECIFICITY[SkillScope.TENANT]
        assert SCOPE_SPECIFICITY[SkillScope.TENANT] < SCOPE_SPECIFICITY[SkillScope.TOOL]
        assert SCOPE_SPECIFICITY[SkillScope.TOOL] < SCOPE_SPECIFICITY[SkillScope.USER]

    def test_specificity_values(self) -> None:
        assert SCOPE_SPECIFICITY[SkillScope.GLOBAL] == 0
        assert SCOPE_SPECIFICITY[SkillScope.TENANT] == 1
        assert SCOPE_SPECIFICITY[SkillScope.TOOL] == 2
        assert SCOPE_SPECIFICITY[SkillScope.USER] == 3

    def test_cascade_sort_order(self) -> None:
        """Higher specificity + higher priority should win."""
        items = [
            {"scope": SkillScope.GLOBAL, "priority": 90},
            {"scope": SkillScope.USER, "priority": 10},
            {"scope": SkillScope.TENANT, "priority": 50},
            {"scope": SkillScope.TOOL, "priority": 50},
        ]
        sorted_items = sorted(
            items,
            key=lambda s: (SCOPE_SPECIFICITY.get(s["scope"], 0), s["priority"]),
            reverse=True,
        )
        assert sorted_items[0]["scope"] == SkillScope.USER
        assert sorted_items[1]["scope"] == SkillScope.TOOL
        assert sorted_items[2]["scope"] == SkillScope.TENANT
        assert sorted_items[3]["scope"] == SkillScope.GLOBAL

    def test_priority_tiebreaker_within_scope(self) -> None:
        """Within the same scope, higher priority wins."""
        items = [
            {"scope": SkillScope.TENANT, "priority": 30},
            {"scope": SkillScope.TENANT, "priority": 80},
            {"scope": SkillScope.TENANT, "priority": 50},
        ]
        sorted_items = sorted(
            items,
            key=lambda s: (SCOPE_SPECIFICITY.get(s["scope"], 0), s["priority"]),
            reverse=True,
        )
        assert sorted_items[0]["priority"] == 80
        assert sorted_items[1]["priority"] == 50
        assert sorted_items[2]["priority"] == 30
