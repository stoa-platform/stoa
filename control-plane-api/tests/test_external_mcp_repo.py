"""Tests for ExternalMCPServerRepository + ToolRepository (CAB-1291)"""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.repositories.external_mcp_server import (
    ExternalMCPServerRepository,
    ExternalMCPServerToolRepository,
)


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_server(**kwargs):
    srv = MagicMock()
    srv.id = kwargs.get("id", uuid4())
    srv.name = kwargs.get("name", "test-mcp")
    srv.tenant_id = kwargs.get("tenant_id", "acme")
    srv.enabled = kwargs.get("enabled", True)
    srv.health_status = kwargs.get("health_status", "healthy")
    srv.last_health_check = kwargs.get("last_health_check", None)
    srv.sync_error = kwargs.get("sync_error", None)
    srv.last_sync_at = kwargs.get("last_sync_at", None)
    srv.created_at = kwargs.get("created_at", datetime(2026, 2, 16))
    srv.updated_at = kwargs.get("updated_at", None)
    srv.tools = kwargs.get("tools", [])
    return srv


def _mock_tool(**kwargs):
    tool = MagicMock()
    tool.id = kwargs.get("id", uuid4())
    tool.server_id = kwargs.get("server_id", uuid4())
    tool.name = kwargs.get("name", "get_weather")
    tool.namespaced_name = kwargs.get("namespaced_name", "test-mcp__get_weather")
    tool.display_name = kwargs.get("display_name", "Get Weather")
    tool.description = kwargs.get("description", "Gets weather data")
    tool.input_schema = kwargs.get("input_schema", {})
    tool.enabled = kwargs.get("enabled", True)
    tool.synced_at = kwargs.get("synced_at", None)
    return tool


# ── ExternalMCPServerRepository ──


class TestServerCreate:
    async def test_creates(self):
        db = _mock_db()
        repo = ExternalMCPServerRepository(db)
        srv = _mock_server()

        result = await repo.create(srv)
        db.add.assert_called_once_with(srv)
        db.flush.assert_awaited_once()
        assert result is srv


class TestServerGetById:
    async def test_found(self):
        db = _mock_db()
        srv = _mock_server()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = srv
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        result = await repo.get_by_id(srv.id)
        assert result is srv

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


class TestServerGetByName:
    async def test_found(self):
        db = _mock_db()
        srv = _mock_server()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = srv
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        result = await repo.get_by_name("test-mcp")
        assert result is srv


class TestServerListAll:
    async def test_returns_list(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_server(), _mock_server()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = ExternalMCPServerRepository(db)
        items, total = await repo.list_all()
        assert total == 2
        assert len(items) == 2

    async def test_with_tenant(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_server()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = ExternalMCPServerRepository(db)
        items, total = await repo.list_all(tenant_id="acme")
        assert total == 1

    async def test_enabled_only(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_server()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])

        repo = ExternalMCPServerRepository(db)
        items, total = await repo.list_all(enabled_only=True)
        assert total == 1


class TestServerListEnabledWithTools:
    async def test_returns(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_server()]
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        result = await repo.list_enabled_with_tools()
        assert len(result) == 1


class TestServerUpdate:
    async def test_updates(self):
        db = _mock_db()
        repo = ExternalMCPServerRepository(db)
        srv = _mock_server()

        result = await repo.update(srv)
        db.flush.assert_awaited_once()
        assert result is srv


class TestServerDelete:
    async def test_deletes(self):
        db = _mock_db()
        repo = ExternalMCPServerRepository(db)
        srv = _mock_server()

        await repo.delete(srv)
        db.delete.assert_awaited_once_with(srv)
        db.flush.assert_awaited_once()


class TestServerUpdateHealthStatus:
    async def test_healthy(self):
        db = _mock_db()
        srv = _mock_server()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = srv
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        result = await repo.update_health_status(srv.id, "healthy")
        assert srv.health_status == "healthy"
        assert srv.sync_error is None
        db.flush.assert_awaited_once()

    async def test_unhealthy(self):
        db = _mock_db()
        srv = _mock_server()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = srv
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        from src.models.external_mcp_server import ExternalMCPHealthStatus
        result = await repo.update_health_status(srv.id, ExternalMCPHealthStatus.UNHEALTHY, error="timeout")
        assert srv.health_status == ExternalMCPHealthStatus.UNHEALTHY
        assert srv.sync_error == "timeout"

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        result = await repo.update_health_status(uuid4(), "healthy")
        assert result is None


class TestServerSyncTools:
    async def test_adds_new_tools(self):
        db = _mock_db()
        srv = _mock_server(tools=[])
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = srv
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        new_tool = _mock_tool(name="new_tool")
        synced, removed = await repo.sync_tools(srv.id, [new_tool])
        assert synced == 1
        assert removed == 0
        db.flush.assert_awaited_once()

    async def test_removes_old_tools(self):
        db = _mock_db()
        old_tool = _mock_tool(name="old_tool")
        srv = _mock_server(tools=[old_tool])
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = srv
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        synced, removed = await repo.sync_tools(srv.id, [])
        assert synced == 0
        assert removed == 1
        db.delete.assert_awaited_once_with(old_tool)

    async def test_updates_existing(self):
        db = _mock_db()
        existing = _mock_tool(name="tool_a")
        srv = _mock_server(tools=[existing])
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = srv
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        updated = _mock_tool(name="tool_a", display_name="Updated")
        synced, removed = await repo.sync_tools(srv.id, [updated])
        assert synced == 1
        assert removed == 0

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        synced, removed = await repo.sync_tools(uuid4(), [])
        assert synced == 0
        assert removed == 0


class TestServerSetSyncError:
    async def test_sets_error(self):
        db = _mock_db()
        srv = _mock_server()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = srv
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        result = await repo.set_sync_error(srv.id, "connection refused")
        assert srv.sync_error == "connection refused"

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerRepository(db)
        result = await repo.set_sync_error(uuid4(), "error")
        assert result is None


# ── ExternalMCPServerToolRepository ──


class TestToolGetById:
    async def test_found(self):
        db = _mock_db()
        tool = _mock_tool()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tool
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerToolRepository(db)
        result = await repo.get_by_id(tool.id)
        assert result is tool


class TestToolGetByServerAndName:
    async def test_found(self):
        db = _mock_db()
        tool = _mock_tool()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tool
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerToolRepository(db)
        result = await repo.get_by_server_and_name(tool.server_id, "get_weather")
        assert result is tool


class TestToolListByServer:
    async def test_returns_all(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_tool(), _mock_tool()]
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerToolRepository(db)
        result = await repo.list_by_server(uuid4())
        assert len(result) == 2

    async def test_enabled_only(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_tool()]
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerToolRepository(db)
        result = await repo.list_by_server(uuid4(), enabled_only=True)
        assert len(result) == 1


class TestToolUpdateEnabled:
    async def test_enables(self):
        db = _mock_db()
        tool = _mock_tool(enabled=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = tool
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerToolRepository(db)
        result = await repo.update_enabled(tool.id, True)
        assert tool.enabled is True
        db.flush.assert_awaited_once()

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        repo = ExternalMCPServerToolRepository(db)
        result = await repo.update_enabled(uuid4(), True)
        assert result is None
