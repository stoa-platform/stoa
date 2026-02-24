"""Unit tests for MCPSyncService and SyncResult.

Covers:
- SyncResult dataclass (defaults, add_error, success flag, error isolation)
- sync_server: creates new server, updates existing, not found in git, rollback on exception,
  platform tenant_id maps to None, category/status enum mapping, commit_sha stored
- _sync_tools: adds new tools, updates existing, marks orphans disabled, skips nameless,
  returns count, preserves enabled tools, new tool defaults
- sync_tenant_servers: success count, git list error, individual failure continues, nameless skip
- sync_all_servers: created/updated counter, marks orphans, git error, individual failure continues,
  nameless skip, commit called
- get_sync_status: counts by status, untracked, last_sync_at most recent, empty db,
  error list content, exception returns error dict
"""
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.mcp_subscription import (
    MCPServerCategory,
    MCPServerStatus,
    MCPServerSyncStatus,
)
from src.services.mcp_sync_service import MCPSyncService, SyncResult

# ─────────────────────────────────────────────
# Helpers / factories
# ─────────────────────────────────────────────


def _make_db() -> AsyncMock:
    """Return a minimal AsyncSession mock."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


def _make_git() -> MagicMock:
    """Return a minimal GitLabService mock."""
    git = MagicMock()
    git.get_mcp_server = AsyncMock(return_value=None)
    git.list_mcp_servers = AsyncMock(return_value=[])
    git.list_all_mcp_servers = AsyncMock(return_value=[])
    return git


def _make_server_data(**overrides) -> dict:
    """Build a minimal server_data dict as returned by git_service.get_mcp_server()."""
    defaults = {
        "name": "test-server",
        "display_name": "Test Server",
        "description": "A test server",
        "icon": None,
        "category": "public",
        "tenant_id": "_platform",
        "visibility": {"public": True},
        "requires_approval": False,
        "auto_approve_roles": [],
        "status": "active",
        "version": "1.0.0",
        "documentation_url": None,
        "git_path": "platform/mcp-servers/test-server",
        "tools": [],
        "backend": {},
    }
    defaults.update(overrides)
    return defaults


def _make_server_orm(**overrides) -> MagicMock:
    """Return a MagicMock that looks like an MCPServer ORM instance."""
    server = MagicMock()
    server.id = uuid.uuid4()
    server.name = overrides.get("name", "test-server")
    server.tools = overrides.get("tools", [])
    server.sync_status = overrides.get("sync_status", MCPServerSyncStatus.SYNCED)
    server.sync_error = overrides.get("sync_error")
    server.git_path = overrides.get("git_path", "platform/mcp-servers/test-server")
    server.last_synced_at = overrides.get("last_synced_at")
    for k, v in overrides.items():
        setattr(server, k, v)
    return server


def _make_tool_orm(name: str, **overrides) -> MagicMock:
    """Return a MagicMock that looks like an MCPServerTool ORM instance."""
    tool = MagicMock()
    tool.name = name
    tool.enabled = overrides.get("enabled", True)
    for k, v in overrides.items():
        setattr(tool, k, v)
    return tool


def _exec_returning(scalar=None) -> MagicMock:
    """Return db.execute() mock with scalar_one_or_none() configured."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    scalars = MagicMock()
    scalars.all.return_value = []
    scalars.__iter__ = MagicMock(return_value=iter([]))
    result.scalars.return_value = scalars
    return result


def _exec_scalars(items: list) -> MagicMock:
    """Return db.execute() mock that yields items from scalars()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    scalars = MagicMock()
    scalars.all.return_value = items
    scalars.__iter__ = MagicMock(return_value=iter(items))
    result.scalars.return_value = scalars
    return result


# ─────────────────────────────────────────────
# SyncResult dataclass
# ─────────────────────────────────────────────


class TestSyncResult:
    def test_defaults_are_zero_and_success(self):
        r = SyncResult()
        assert r.success is True
        assert r.servers_synced == 0
        assert r.servers_created == 0
        assert r.servers_updated == 0
        assert r.servers_orphaned == 0
        assert r.tools_synced == 0
        assert r.errors == []

    def test_add_error_appends_message(self):
        r = SyncResult()
        r.add_error("something failed")
        assert "something failed" in r.errors

    def test_add_error_sets_success_false(self):
        r = SyncResult()
        r.add_error("fail")
        assert r.success is False

    def test_multiple_errors_accumulate(self):
        r = SyncResult()
        r.add_error("error 1")
        r.add_error("error 2")
        assert len(r.errors) == 2
        assert r.success is False

    def test_errors_list_independent_between_instances(self):
        r1 = SyncResult()
        r2 = SyncResult()
        r1.add_error("only in r1")
        assert r2.errors == []


# ─────────────────────────────────────────────
# sync_server — create new server
# ─────────────────────────────────────────────


class TestSyncServerCreate:
    async def test_creates_new_server_when_not_in_db(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data()
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        result = await svc.sync_server("_platform", "test-server")

        db.add.assert_called()
        db.commit.assert_awaited()

    async def test_new_server_sets_synced_status(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data()
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.sync_status == MCPServerSyncStatus.SYNCED

    async def test_platform_tenant_id_maps_to_none(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data(tenant_id="_platform")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.tenant_id is None

    async def test_real_tenant_id_preserved(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data(tenant_id="acme")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("acme", "test-server")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.tenant_id == "acme"

    async def test_category_public_maps_to_enum(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data(category="public")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.category == MCPServerCategory.PUBLIC

    async def test_category_platform_maps_to_enum(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data(category="platform")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.category == MCPServerCategory.PLATFORM

    async def test_category_tenant_maps_to_enum(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data(category="tenant")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("acme", "test-server")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.category == MCPServerCategory.TENANT

    async def test_unknown_category_defaults_to_public(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data(category="weird")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.category == MCPServerCategory.PUBLIC

    async def test_status_active_maps_to_enum(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data(status="active")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.status == MCPServerStatus.ACTIVE

    async def test_status_maintenance_maps_to_enum(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data(status="maintenance")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.status == MCPServerStatus.MAINTENANCE

    async def test_commit_sha_stored_on_create(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data()
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server", commit_sha="abc123")

        add_call_args = db.add.call_args[0][0]
        assert add_call_args.git_commit_sha == "abc123"


# ─────────────────────────────────────────────
# sync_server — update existing server
# ─────────────────────────────────────────────


class TestSyncServerUpdate:
    async def test_updates_existing_server_fields(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data(
            display_name="Updated Name",
            description="New desc",
        )
        existing = _make_server_orm(tools=[])
        db.execute.return_value = _exec_returning(scalar=existing)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        assert existing.display_name == "Updated Name"
        assert existing.description == "New desc"

    async def test_existing_server_sync_status_set_to_synced(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data()
        existing = _make_server_orm(tools=[], sync_status=MCPServerSyncStatus.ERROR)
        db.execute.return_value = _exec_returning(scalar=existing)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        assert existing.sync_status == MCPServerSyncStatus.SYNCED

    async def test_existing_server_sync_error_cleared(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data()
        existing = _make_server_orm(tools=[], sync_error="previous error")
        db.execute.return_value = _exec_returning(scalar=existing)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        assert existing.sync_error is None

    async def test_does_not_call_db_add_for_update(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data()
        existing = _make_server_orm(tools=[])
        db.execute.return_value = _exec_returning(scalar=existing)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        db.add.assert_not_called()

    async def test_commit_called_after_update(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data()
        existing = _make_server_orm(tools=[])
        db.execute.return_value = _exec_returning(scalar=existing)

        svc = MCPSyncService(git, db)
        await svc.sync_server("_platform", "test-server")

        db.commit.assert_awaited()


# ─────────────────────────────────────────────
# sync_server — not found in GitLab
# ─────────────────────────────────────────────


class TestSyncServerNotFound:
    async def test_git_returns_none_yields_none(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = None

        svc = MCPSyncService(git, db)
        result = await svc.sync_server("_platform", "missing-server")

        assert result is None
        db.add.assert_not_called()
        db.commit.assert_not_awaited()


# ─────────────────────────────────────────────
# sync_server — exception handling
# ─────────────────────────────────────────────


class TestSyncServerException:
    async def test_exception_triggers_rollback(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.side_effect = RuntimeError("gitlab failure")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        result = await svc.sync_server("_platform", "test-server")

        assert result is None
        db.rollback.assert_awaited()

    async def test_exception_returns_none(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.side_effect = ValueError("bad data")
        db.execute.return_value = _exec_returning(scalar=None)

        svc = MCPSyncService(git, db)
        result = await svc.sync_server("_platform", "test-server")

        assert result is None

    async def test_exception_in_tools_sync_sets_error_on_existing(self):
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.return_value = _make_server_data()
        existing = _make_server_orm(tools=[])
        db.execute.return_value = _exec_returning(scalar=existing)

        svc = MCPSyncService(git, db)
        with patch.object(svc, "_sync_tools", AsyncMock(side_effect=RuntimeError("tools fail"))):
            await svc.sync_server("_platform", "test-server")

        db.rollback.assert_awaited()

    async def test_inner_exception_in_error_handler_is_swallowed(self):
        """Exception in the 'set ERROR status' block should not bubble up."""
        db = _make_db()
        git = _make_git()
        git.get_mcp_server.side_effect = RuntimeError("git failure")
        db.execute.side_effect = RuntimeError("db also failed")

        svc = MCPSyncService(git, db)
        result = await svc.sync_server("_platform", "test-server")

        assert result is None  # no uncaught exception


# ─────────────────────────────────────────────
# _sync_tools
# ─────────────────────────────────────────────


class TestSyncTools:
    async def test_adds_new_tools_to_db(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        server = _make_server_orm(tools=[])
        tools_data = [{"name": "search", "description": "Search tool"}]

        count = await svc._sync_tools(server, tools_data)

        assert count == 1
        db.add.assert_called_once()

    async def test_adds_multiple_new_tools(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        server = _make_server_orm(tools=[])
        tools_data = [{"name": "tool-a"}, {"name": "tool-b"}]

        count = await svc._sync_tools(server, tools_data)

        assert count == 2
        assert db.add.call_count == 2

    async def test_updates_existing_tool_fields(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        existing_tool = _make_tool_orm("search", description="old")
        server = _make_server_orm(tools=[existing_tool])
        tools_data = [{"name": "search", "description": "new description", "method": "GET"}]

        count = await svc._sync_tools(server, tools_data)

        assert count == 1
        assert existing_tool.description == "new description"
        assert existing_tool.method == "GET"
        db.add.assert_not_called()

    async def test_orphan_tools_disabled(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        orphan = _make_tool_orm("old-tool", enabled=True)
        server = _make_server_orm(tools=[orphan])
        tools_data = []  # nothing from git → old-tool is orphan

        await svc._sync_tools(server, tools_data)

        assert orphan.enabled is False

    async def test_orphan_tools_not_deleted_from_db(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        orphan = _make_tool_orm("old-tool")
        server = _make_server_orm(tools=[orphan])

        await svc._sync_tools(server, [])

        db.add.assert_not_called()

    async def test_returns_correct_count(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        server = _make_server_orm(tools=[])
        tools_data = [{"name": "t1"}, {"name": "t2"}, {"name": "t3"}]

        count = await svc._sync_tools(server, tools_data)
        assert count == 3

    async def test_tool_without_name_is_skipped(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        server = _make_server_orm(tools=[])
        tools_data = [{"description": "no name"}]

        count = await svc._sync_tools(server, tools_data)
        assert count == 0
        db.add.assert_not_called()

    async def test_empty_tools_data_returns_zero(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        server = _make_server_orm(tools=[])
        count = await svc._sync_tools(server, [])
        assert count == 0

    async def test_new_tool_uses_correct_defaults(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        server = _make_server_orm(tools=[])
        tools_data = [{"name": "minimal-tool"}]

        await svc._sync_tools(server, tools_data)

        new_tool = db.add.call_args[0][0]
        assert new_tool.name == "minimal-tool"
        assert new_tool.enabled is True
        assert new_tool.method == "POST"
        assert new_tool.timeout == "30s"
        assert new_tool.rate_limit == 60

    async def test_keeps_active_tools_enabled(self):
        db = _make_db()
        git = _make_git()
        svc = MCPSyncService(git, db)

        existing_tool = _make_tool_orm("active-tool", enabled=True)
        server = _make_server_orm(tools=[existing_tool])
        tools_data = [{"name": "active-tool"}]

        await svc._sync_tools(server, tools_data)

        assert existing_tool.enabled is True


# ─────────────────────────────────────────────
# sync_tenant_servers
# ─────────────────────────────────────────────


class TestSyncTenantServers:
    async def test_success_returns_sync_result(self):
        db = _make_db()
        git = _make_git()
        git.list_mcp_servers.return_value = [
            _make_server_data(name="srv-1"),
            _make_server_data(name="srv-2"),
        ]

        svc = MCPSyncService(git, db)
        # Patch sync_server so it succeeds without needing a real GitLab round-trip
        svc.sync_server = AsyncMock(
            side_effect=lambda tid, name, commit_sha=None: _make_server_orm(name=name, tools=[])
        )

        result = await svc.sync_tenant_servers("_platform")

        assert isinstance(result, SyncResult)
        assert result.servers_synced == 2

    async def test_git_list_error_adds_to_result(self):
        db = _make_db()
        git = _make_git()
        git.list_mcp_servers.side_effect = RuntimeError("git down")

        svc = MCPSyncService(git, db)
        result = await svc.sync_tenant_servers("acme")

        assert result.success is False
        assert any("Failed to list" in e for e in result.errors)

    async def test_individual_sync_failure_continues_with_others(self):
        db = _make_db()
        git = _make_git()
        git.list_mcp_servers.return_value = [
            _make_server_data(name="ok-server"),
            _make_server_data(name="bad-server"),
        ]

        svc = MCPSyncService(git, db)

        async def patched_sync(tenant_id, server_name, commit_sha=None):
            if server_name == "bad-server":
                raise RuntimeError("sync failed")
            return _make_server_orm(name=server_name, tools=[])

        svc.sync_server = patched_sync
        result = await svc.sync_tenant_servers("acme")

        assert result.servers_synced == 1
        assert result.success is False
        assert any("bad-server" in e for e in result.errors)

    async def test_skips_servers_without_name(self):
        db = _make_db()
        git = _make_git()
        git.list_mcp_servers.return_value = [{"description": "nameless server"}]

        svc = MCPSyncService(git, db)
        result = await svc.sync_tenant_servers("_platform")

        assert result.servers_synced == 0
        assert result.success is True

    async def test_empty_tenant_succeeds_with_zero(self):
        db = _make_db()
        git = _make_git()
        git.list_mcp_servers.return_value = []

        svc = MCPSyncService(git, db)
        result = await svc.sync_tenant_servers("_platform")

        assert result.success is True
        assert result.servers_synced == 0


# ─────────────────────────────────────────────
# sync_all_servers
# ─────────────────────────────────────────────


class TestSyncAllServers:
    async def test_success_increments_synced_counter(self):
        db = _make_db()
        git = _make_git()
        git.list_all_mcp_servers.return_value = [
            _make_server_data(name="srv-1", git_path="p/1"),
        ]

        call_num = {"n": 0}

        async def patched_execute(query):
            call_num["n"] += 1
            if call_num["n"] == 1:
                return _exec_returning(scalar=None)  # existence check
            return _exec_scalars([])  # orphan scan

        db.execute = patched_execute
        svc = MCPSyncService(git, db)

        async def patched_sync(tenant_id, server_name, commit_sha=None):
            return _make_server_orm(name=server_name, tools=[])

        svc.sync_server = patched_sync
        result = await svc.sync_all_servers()

        assert result.servers_synced == 1

    async def test_marks_new_server_as_created(self):
        db = _make_db()
        git = _make_git()
        git.list_all_mcp_servers.return_value = [
            _make_server_data(name="new-srv", git_path="p/new"),
        ]

        call_num = {"n": 0}

        async def patched_execute(query):
            call_num["n"] += 1
            if call_num["n"] == 1:
                return _exec_returning(scalar=None)  # not in DB
            return _exec_scalars([])

        db.execute = patched_execute
        svc = MCPSyncService(git, db)
        svc.sync_server = AsyncMock(return_value=_make_server_orm(name="new-srv", tools=[]))

        result = await svc.sync_all_servers()

        assert result.servers_created == 1
        assert result.servers_updated == 0

    async def test_marks_existing_server_as_updated(self):
        db = _make_db()
        git = _make_git()
        git.list_all_mcp_servers.return_value = [
            _make_server_data(name="existing-srv", git_path="p/existing"),
        ]

        call_num = {"n": 0}

        async def patched_execute(query):
            call_num["n"] += 1
            if call_num["n"] == 1:
                return _exec_returning(scalar=_make_server_orm())  # already in DB
            return _exec_scalars([])

        db.execute = patched_execute
        svc = MCPSyncService(git, db)
        svc.sync_server = AsyncMock(return_value=_make_server_orm(name="existing-srv", tools=[]))

        result = await svc.sync_all_servers()

        assert result.servers_created == 0
        assert result.servers_updated == 1

    async def test_marks_orphan_servers(self):
        db = _make_db()
        git = _make_git()
        git.list_all_mcp_servers.return_value = []  # nothing from git

        orphan = _make_server_orm(git_path="old/path/server")
        orphan.sync_status = MCPServerSyncStatus.SYNCED

        async def patched_execute(query):
            return _exec_scalars([orphan])

        db.execute = patched_execute
        svc = MCPSyncService(git, db)
        result = await svc.sync_all_servers()

        assert orphan.sync_status == MCPServerSyncStatus.ORPHAN
        assert result.servers_orphaned == 1
        db.commit.assert_awaited()

    async def test_git_list_error_adds_to_result(self):
        db = _make_db()
        git = _make_git()
        git.list_all_mcp_servers.side_effect = RuntimeError("gitlab down")

        svc = MCPSyncService(git, db)
        result = await svc.sync_all_servers()

        assert result.success is False
        assert any("Full sync failed" in e for e in result.errors)

    async def test_individual_server_sync_failure_continues(self):
        db = _make_db()
        git = _make_git()
        git.list_all_mcp_servers.return_value = [
            _make_server_data(name="ok-server", git_path="p/ok"),
            _make_server_data(name="bad-server", git_path="p/bad"),
        ]

        call_num = {"n": 0}

        async def patched_execute(query):
            call_num["n"] += 1
            if call_num["n"] <= 2:
                return _exec_returning(scalar=None)
            return _exec_scalars([])

        db.execute = patched_execute
        svc = MCPSyncService(git, db)

        async def patched_sync(tenant_id, server_name, commit_sha=None):
            if server_name == "bad-server":
                raise RuntimeError("sync failed")
            return _make_server_orm(name=server_name, tools=[])

        svc.sync_server = patched_sync
        result = await svc.sync_all_servers()

        assert result.servers_synced == 1
        assert result.success is False

    async def test_skips_servers_without_name(self):
        db = _make_db()
        git = _make_git()
        git.list_all_mcp_servers.return_value = [
            {"tenant_id": "_platform", "git_path": "some/path"}
        ]
        db.execute.return_value = _exec_scalars([])

        svc = MCPSyncService(git, db)
        result = await svc.sync_all_servers()

        assert result.servers_synced == 0

    async def test_commit_called_at_end(self):
        db = _make_db()
        git = _make_git()
        git.list_all_mcp_servers.return_value = []
        db.execute.return_value = _exec_scalars([])

        svc = MCPSyncService(git, db)
        await svc.sync_all_servers()

        db.commit.assert_awaited()


# ─────────────────────────────────────────────
# get_sync_status
# ─────────────────────────────────────────────


class TestGetSyncStatus:
    async def test_counts_by_sync_status(self):
        db = _make_db()
        git = _make_git()

        servers = [
            _make_server_orm(sync_status=MCPServerSyncStatus.SYNCED, last_synced_at=None, sync_error=None),
            _make_server_orm(sync_status=MCPServerSyncStatus.SYNCED, last_synced_at=None, sync_error=None),
            _make_server_orm(sync_status=MCPServerSyncStatus.PENDING, last_synced_at=None, sync_error=None),
            _make_server_orm(sync_status=MCPServerSyncStatus.ERROR, last_synced_at=None, sync_error="fail"),
            _make_server_orm(sync_status=MCPServerSyncStatus.ORPHAN, last_synced_at=None, sync_error=None),
        ]
        db.execute.return_value = _exec_scalars(servers)

        svc = MCPSyncService(git, db)
        status = await svc.get_sync_status()

        assert status["total_servers"] == 5
        assert status["synced"] == 2
        assert status["pending"] == 1
        assert status["error"] == 1
        assert status["orphan"] == 1

    async def test_untracked_servers_counted(self):
        db = _make_db()
        git = _make_git()

        server = _make_server_orm(sync_status=None, last_synced_at=None, sync_error=None)
        db.execute.return_value = _exec_scalars([server])

        svc = MCPSyncService(git, db)
        status = await svc.get_sync_status()

        assert status["untracked"] == 1

    async def test_last_sync_at_is_most_recent(self):
        db = _make_db()
        git = _make_git()

        old_dt = datetime(2026, 1, 1, 0, 0, 0)
        new_dt = datetime(2026, 2, 1, 0, 0, 0)

        servers = [
            _make_server_orm(sync_status=MCPServerSyncStatus.SYNCED, last_synced_at=old_dt, sync_error=None),
            _make_server_orm(sync_status=MCPServerSyncStatus.SYNCED, last_synced_at=new_dt, sync_error=None),
        ]
        db.execute.return_value = _exec_scalars(servers)

        svc = MCPSyncService(git, db)
        status = await svc.get_sync_status()

        assert status["last_sync_at"] == new_dt.isoformat()

    async def test_empty_db_returns_zeros(self):
        db = _make_db()
        git = _make_git()
        db.execute.return_value = _exec_scalars([])

        svc = MCPSyncService(git, db)
        status = await svc.get_sync_status()

        assert status["total_servers"] == 0
        assert status["last_sync_at"] is None
        assert status["errors"] == []

    async def test_error_list_includes_server_errors(self):
        db = _make_db()
        git = _make_git()

        error_server = _make_server_orm(
            name="broken-server",
            sync_status=MCPServerSyncStatus.ERROR,
            last_synced_at=None,
            sync_error="connection refused",
        )
        db.execute.return_value = _exec_scalars([error_server])

        svc = MCPSyncService(git, db)
        status = await svc.get_sync_status()

        assert len(status["errors"]) == 1
        assert status["errors"][0]["server"] == "broken-server"
        assert status["errors"][0]["error"] == "connection refused"

    async def test_error_list_excludes_non_error_servers(self):
        db = _make_db()
        git = _make_git()

        ok_server = _make_server_orm(
            sync_status=MCPServerSyncStatus.SYNCED,
            last_synced_at=None,
            sync_error=None,
        )
        db.execute.return_value = _exec_scalars([ok_server])

        svc = MCPSyncService(git, db)
        status = await svc.get_sync_status()

        assert status["errors"] == []

    async def test_exception_returns_error_dict(self):
        db = _make_db()
        git = _make_git()
        db.execute.side_effect = RuntimeError("db down")

        svc = MCPSyncService(git, db)
        status = await svc.get_sync_status()

        assert "error" in status
        assert "db down" in status["error"]
