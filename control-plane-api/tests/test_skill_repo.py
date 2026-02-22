"""Tests for SkillRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.skill import Skill, SkillScope
from src.repositories.skill import SCOPE_SPECIFICITY, SkillRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.get = AsyncMock()
    return db


def _mock_skill(**kwargs):
    s = MagicMock(spec=Skill)
    s.id = kwargs.get("id", uuid4())
    s.tenant_id = kwargs.get("tenant_id", "acme")
    s.name = kwargs.get("name", "test-skill")
    s.scope = kwargs.get("scope", SkillScope.GLOBAL)
    s.enabled = kwargs.get("enabled", True)
    s.priority = kwargs.get("priority", 0)
    s.instructions = kwargs.get("instructions", "Do X")
    s.tool_ref = kwargs.get("tool_ref", None)
    s.user_ref = kwargs.get("user_ref", None)
    return s


# ── SCOPE_SPECIFICITY ──


class TestScopeSpecificity:
    def test_global_lowest(self):
        assert SCOPE_SPECIFICITY[SkillScope.GLOBAL] == 0

    def test_user_highest(self):
        assert SCOPE_SPECIFICITY[SkillScope.USER] > SCOPE_SPECIFICITY[SkillScope.TENANT]


# ── create ──


class TestCreate:
    async def test_create(self):
        db = _mock_db()
        skill = _mock_skill()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill
        db.execute = AsyncMock(return_value=mock_result)
        # Patch Skill constructor
        import unittest.mock as um
        with um.patch("src.repositories.skill.Skill") as MockSkill:
            MockSkill.return_value = skill
            repo = SkillRepository(db)
            result = await repo.create("acme", name="test-skill")
        db.add.assert_called_once()
        db.flush.assert_called_once()


# ── get ──


class TestGet:
    async def test_found(self):
        db = _mock_db()
        skill = _mock_skill()
        db.get = AsyncMock(return_value=skill)
        repo = SkillRepository(db)
        result = await repo.get(skill.id)
        assert result is skill

    async def test_not_found(self):
        db = _mock_db()
        db.get = AsyncMock(return_value=None)
        repo = SkillRepository(db)
        result = await repo.get(uuid4())
        assert result is None


# ── list_by_tenant ──


class TestListByTenant:
    async def test_list_all(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_skill(), _mock_skill()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        result = await repo.list_by_tenant("acme")
        assert len(result) == 2

    async def test_list_by_scope(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_skill(scope=SkillScope.TENANT)]
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        result = await repo.list_by_tenant("acme", scope=SkillScope.TENANT)
        assert len(result) == 1

    async def test_empty(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        result = await repo.list_by_tenant("acme")
        assert result == []


# ── count_by_tenant ──


class TestCountByTenant:
    async def test_count(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 3
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        count = await repo.count_by_tenant("acme")
        assert count == 3

    async def test_count_with_scope(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        count = await repo.count_by_tenant("acme", scope=SkillScope.GLOBAL)
        assert count == 1


# ── update ──


class TestUpdate:
    async def test_update_with_values(self):
        db = _mock_db()
        skill = _mock_skill()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = skill
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        result = await repo.update(skill.id, name="new-name")
        assert result is skill

    async def test_update_no_values_returns_existing(self):
        db = _mock_db()
        skill = _mock_skill()
        db.get = AsyncMock(return_value=skill)
        repo = SkillRepository(db)
        result = await repo.update(skill.id)
        assert result is skill


# ── delete ──


class TestDelete:
    async def test_delete_existing(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 1
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        deleted = await repo.delete(uuid4())
        assert deleted is True

    async def test_delete_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.rowcount = 0
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        deleted = await repo.delete(uuid4())
        assert deleted is False


# ── list_resolved (CSS cascade) ──


class TestListResolved:
    async def test_global_skills_always_included(self):
        db = _mock_db()
        global_skill = _mock_skill(scope=SkillScope.GLOBAL, priority=0)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [global_skill]
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        result = await repo.list_resolved("acme")
        assert len(result) == 1
        assert result[0]["name"] == global_skill.name

    async def test_tool_scoped_filtered_by_tool_ref(self):
        db = _mock_db()
        tool_skill = _mock_skill(scope=SkillScope.TOOL, tool_ref="tool-a", priority=1)
        other_tool_skill = _mock_skill(scope=SkillScope.TOOL, tool_ref="tool-b", priority=1)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [tool_skill, other_tool_skill]
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        result = await repo.list_resolved("acme", tool_ref="tool-a")
        assert all(r["name"] == tool_skill.name for r in result)

    async def test_sorted_by_specificity_desc(self):
        db = _mock_db()
        global_skill = _mock_skill(scope=SkillScope.GLOBAL, name="global", priority=0)
        tenant_skill = _mock_skill(scope=SkillScope.TENANT, name="tenant", priority=0)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [global_skill, tenant_skill]
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        result = await repo.list_resolved("acme")
        assert result[0]["scope"] == SkillScope.TENANT
        assert result[1]["scope"] == SkillScope.GLOBAL

    async def test_user_scoped_with_user_ref(self):
        db = _mock_db()
        user_skill = _mock_skill(scope=SkillScope.USER, user_ref="user-1", priority=2)
        wrong_user = _mock_skill(scope=SkillScope.USER, user_ref="user-2", priority=2)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [user_skill, wrong_user]
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        result = await repo.list_resolved("acme", user_ref="user-1")
        assert len(result) == 1

    async def test_empty_result(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = SkillRepository(db)
        result = await repo.list_resolved("acme")
        assert result == []
