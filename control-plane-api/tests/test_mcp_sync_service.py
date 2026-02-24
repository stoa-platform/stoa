"""Tests for MCPSyncService + SyncResult (CAB-1291)"""
from unittest.mock import AsyncMock, MagicMock

from src.services.mcp_sync_service import MCPSyncService, SyncResult

# ── SyncResult dataclass ──


class TestSyncResult:
    def test_defaults(self):
        r = SyncResult()
        assert r.success is True
        assert r.servers_synced == 0
        assert r.servers_created == 0
        assert r.servers_updated == 0
        assert r.servers_orphaned == 0
        assert r.tools_synced == 0
        assert r.errors == []

    def test_add_error(self):
        r = SyncResult()
        r.add_error("something broke")
        assert r.success is False
        assert len(r.errors) == 1
        assert r.errors[0] == "something broke"

    def test_multiple_errors(self):
        r = SyncResult()
        r.add_error("err1")
        r.add_error("err2")
        assert len(r.errors) == 2
        assert r.success is False


# ── MCPSyncService._sync_tools ──


class TestSyncTools:
    def _make_server(self, tools=None):
        """Create a mock MCPServer with tools list."""
        server = MagicMock()
        server.id = "server-1"
        server.name = "test-server"
        server.tools = tools or []
        return server

    def _make_tool(self, name, enabled=True):
        tool = MagicMock()
        tool.name = name
        tool.enabled = enabled
        return tool

    async def test_add_new_tools(self):
        db = MagicMock()
        git_svc = MagicMock()
        svc = MCPSyncService(git_service=git_svc, db=db)

        server = self._make_server(tools=[])
        tools_data = [
            {"name": "tool-a", "description": "Tool A"},
            {"name": "tool-b"},
        ]
        count = await svc._sync_tools(server, tools_data)
        assert count == 2
        assert db.add.call_count == 2

    async def test_update_existing_tool(self):
        db = MagicMock()
        git_svc = MagicMock()
        svc = MCPSyncService(git_service=git_svc, db=db)

        existing = self._make_tool("tool-a")
        server = self._make_server(tools=[existing])

        tools_data = [{"name": "tool-a", "description": "Updated", "method": "GET"}]
        count = await svc._sync_tools(server, tools_data)
        assert count == 1
        assert existing.description == "Updated"
        assert existing.method == "GET"

    async def test_disable_orphan_tools(self):
        db = MagicMock()
        git_svc = MagicMock()
        svc = MCPSyncService(git_service=git_svc, db=db)

        orphan = self._make_tool("old-tool", enabled=True)
        server = self._make_server(tools=[orphan])

        # Git has no tools
        count = await svc._sync_tools(server, [])
        assert count == 0
        assert orphan.enabled is False

    async def test_skip_tools_without_name(self):
        db = MagicMock()
        git_svc = MagicMock()
        svc = MCPSyncService(git_service=git_svc, db=db)

        server = self._make_server(tools=[])
        tools_data = [{"description": "no name"}, {"name": "valid"}]
        count = await svc._sync_tools(server, tools_data)
        assert count == 1


# ── MCPSyncService.sync_server ──


class TestSyncServer:
    async def test_server_not_in_git(self):
        db = AsyncMock()
        git_svc = MagicMock()
        git_svc.get_mcp_server = AsyncMock(return_value=None)
        svc = MCPSyncService(git_service=git_svc, db=db)

        result = await svc.sync_server("acme", "nonexistent")
        assert result is None

    async def test_sync_error_updates_status(self):
        db = AsyncMock()
        git_svc = MagicMock()
        git_svc.get_mcp_server = AsyncMock(side_effect=Exception("git error"))
        svc = MCPSyncService(git_service=git_svc, db=db)

        # Mock DB lookup for error handling path
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        result = await svc.sync_server("acme", "broken")
        assert result is None


# ── MCPSyncService.sync_tenant_servers ──


class TestSyncTenantServers:
    async def test_empty_tenant(self):
        db = AsyncMock()
        git_svc = MagicMock()
        git_svc.list_mcp_servers = AsyncMock(return_value=[])
        svc = MCPSyncService(git_service=git_svc, db=db)

        result = await svc.sync_tenant_servers("acme")
        assert result.servers_synced == 0
        assert result.success is True

    async def test_list_error(self):
        db = AsyncMock()
        git_svc = MagicMock()
        git_svc.list_mcp_servers = AsyncMock(side_effect=Exception("git down"))
        svc = MCPSyncService(git_service=git_svc, db=db)

        result = await svc.sync_tenant_servers("acme")
        assert result.success is False
        assert len(result.errors) == 1


# ── MCPSyncService.get_sync_status ──


class TestGetSyncStatus:
    async def test_empty_db(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute.return_value = mock_result

        git_svc = MagicMock()
        svc = MCPSyncService(git_service=git_svc, db=db)

        status = await svc.get_sync_status()
        assert status["total_servers"] == 0
        assert status["last_sync_at"] is None

    async def test_error_returns_error_dict(self):
        db = AsyncMock()
        db.execute.side_effect = Exception("db error")

        git_svc = MagicMock()
        svc = MCPSyncService(git_service=git_svc, db=db)

        status = await svc.get_sync_status()
        assert "error" in status
