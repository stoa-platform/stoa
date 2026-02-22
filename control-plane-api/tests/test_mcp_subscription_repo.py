"""Tests for MCPServerRepository, MCPSubscriptionRepository, MCPToolAccessRepository (CAB-1388)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.mcp_subscription import (
    MCPServer,
    MCPServerCategory,
    MCPServerStatus,
    MCPServerSubscription,
    MCPSubscriptionStatus,
    MCPToolAccess,
    MCPToolAccessStatus,
)

# MCPServerCategory: PLATFORM, TENANT, PUBLIC
from src.repositories.mcp_subscription import (
    MCPServerRepository,
    MCPSubscriptionRepository,
    MCPToolAccessRepository,
    _is_visible,
)


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_server(**kwargs):
    s = MagicMock(spec=MCPServer)
    s.id = kwargs.get("id", uuid4())
    s.name = kwargs.get("name", "my-server")
    s.display_name = kwargs.get("display_name", "My Server")
    s.status = kwargs.get("status", MCPServerStatus.ACTIVE)
    s.category = kwargs.get("category", MCPServerCategory.TENANT)
    s.tenant_id = kwargs.get("tenant_id", None)
    s.visibility = kwargs.get("visibility", None)
    return s


def _mock_subscription(**kwargs):
    sub = MagicMock(spec=MCPServerSubscription)
    sub.id = kwargs.get("id", uuid4())
    sub.subscriber_id = kwargs.get("subscriber_id", "user-001")
    sub.tenant_id = kwargs.get("tenant_id", "acme")
    sub.server_id = kwargs.get("server_id", uuid4())
    sub.status = kwargs.get("status", MCPSubscriptionStatus.PENDING)
    sub.api_key_hash = kwargs.get("api_key_hash", None)
    sub.api_key_prefix = kwargs.get("api_key_prefix", None)
    sub.previous_api_key_hash = kwargs.get("previous_api_key_hash", None)
    sub.rotation_count = kwargs.get("rotation_count", 0)
    sub.usage_count = kwargs.get("usage_count", 0)
    sub.expires_at = kwargs.get("expires_at", None)
    return sub


def _mock_tool_access(**kwargs):
    ta = MagicMock(spec=MCPToolAccess)
    ta.id = kwargs.get("id", uuid4())
    ta.subscription_id = kwargs.get("subscription_id", uuid4())
    ta.tool_id = kwargs.get("tool_id", uuid4())
    ta.status = kwargs.get("status", MCPToolAccessStatus.ENABLED)
    ta.usage_count = kwargs.get("usage_count", 0)
    return ta


# ── _is_visible ──


class TestIsVisible:
    def test_cpi_admin_always_visible(self):
        server = _mock_server(visibility={"public": False})
        assert _is_visible(server, ["cpi-admin"]) is True

    def test_public_server_visible_to_all(self):
        server = _mock_server(visibility={"public": True})
        assert _is_visible(server, ["tenant-admin"]) is True

    def test_no_visibility_defaults_to_public(self):
        server = _mock_server(visibility=None)
        assert _is_visible(server, ["viewer"]) is True

    def test_exclude_roles_takes_precedence(self):
        server = _mock_server(visibility={"public": True, "exclude_roles": ["devops"]})
        assert _is_visible(server, ["devops"]) is False

    def test_private_with_allowed_role(self):
        server = _mock_server(visibility={"public": False, "roles": ["tenant-admin"]})
        assert _is_visible(server, ["tenant-admin"]) is True

    def test_private_without_allowed_role(self):
        server = _mock_server(visibility={"public": False, "roles": ["tenant-admin"]})
        assert _is_visible(server, ["viewer"]) is False

    def test_private_no_roles_returns_false(self):
        server = _mock_server(visibility={"public": False})
        assert _is_visible(server, ["viewer"]) is False


# ── MCPServerRepository ──


class TestServerCreate:
    async def test_create(self):
        db = _mock_db()
        server = _mock_server()
        repo = MCPServerRepository(db)
        result = await repo.create(server)
        db.add.assert_called_once_with(server)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(server)
        assert result is server


class TestServerGetById:
    async def test_found(self):
        db = _mock_db()
        server = _mock_server()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = server
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPServerRepository(db)
        result = await repo.get_by_id(server.id)
        assert result is server

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPServerRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


class TestServerGetByName:
    async def test_found(self):
        db = _mock_db()
        server = _mock_server(name="my-server")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = server
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPServerRepository(db)
        result = await repo.get_by_name("my-server")
        assert result is server


class TestServerListVisibleForUser:
    async def test_filters_by_visibility(self):
        db = _mock_db()
        visible = _mock_server(visibility={"public": True})
        hidden = _mock_server(visibility={"public": False, "roles": ["cpi-admin"]})
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [visible, hidden]
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPServerRepository(db)
        items, total = await repo.list_visible_for_user(user_roles=["viewer"])
        assert total == 1
        assert items[0] is visible

    async def test_cpi_admin_sees_all(self):
        db = _mock_db()
        servers = [_mock_server(visibility={"public": False}) for _ in range(3)]
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = servers
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPServerRepository(db)
        items, total = await repo.list_visible_for_user(user_roles=["cpi-admin"])
        assert total == 3


class TestServerListAll:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_server(), _mock_server()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MCPServerRepository(db)
        items, total = await repo.list_all()
        assert total == 2
        assert len(items) == 2

    async def test_with_filters(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_server()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MCPServerRepository(db)
        items, total = await repo.list_all(category=MCPServerCategory.TENANT, status=MCPServerStatus.ACTIVE)
        assert total == 1


class TestServerUpdate:
    async def test_update(self):
        db = _mock_db()
        server = _mock_server()
        repo = MCPServerRepository(db)
        result = await repo.update(server)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(server)
        assert result is server


class TestServerDelete:
    async def test_delete(self):
        db = _mock_db()
        server = _mock_server()
        repo = MCPServerRepository(db)
        await repo.delete(server)
        db.delete.assert_called_once_with(server)
        db.flush.assert_called_once()


# ── MCPSubscriptionRepository ──


class TestSubscriptionCreate:
    async def test_create(self):
        db = _mock_db()
        sub = _mock_subscription()
        repo = MCPSubscriptionRepository(db)
        result = await repo.create(sub)
        db.add.assert_called_once_with(sub)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(sub)
        assert result is sub


class TestSubscriptionGetById:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_subscription()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPSubscriptionRepository(db)
        result = await repo.get_by_id(sub.id)
        assert result is sub


class TestSubscriptionGetByApiKeyHash:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_subscription()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPSubscriptionRepository(db)
        result = await repo.get_by_api_key_hash("hash-abc")
        assert result is sub


class TestSubscriptionGetByPreviousKeyHash:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_subscription()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPSubscriptionRepository(db)
        result = await repo.get_by_previous_key_hash("old-hash")
        assert result is sub


class TestSubscriptionGetBySubscriberAndServer:
    async def test_found(self):
        db = _mock_db()
        sub = _mock_subscription()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sub
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPSubscriptionRepository(db)
        result = await repo.get_by_subscriber_and_server("user-001", uuid4())
        assert result is sub


class TestSubscriptionListBySubscriber:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 2
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_subscription(), _mock_subscription()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MCPSubscriptionRepository(db)
        items, total = await repo.list_by_subscriber("user-001")
        assert total == 2

    async def test_with_status_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_subscription(status=MCPSubscriptionStatus.ACTIVE)]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MCPSubscriptionRepository(db)
        items, total = await repo.list_by_subscriber("user-001", status=MCPSubscriptionStatus.ACTIVE)
        assert total == 1


class TestSubscriptionListByTenant:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 3
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_subscription()] * 3
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MCPSubscriptionRepository(db)
        items, total = await repo.list_by_tenant("acme")
        assert total == 3


class TestSubscriptionListPending:
    async def test_basic(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_subscription()]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MCPSubscriptionRepository(db)
        items, total = await repo.list_pending()
        assert total == 1

    async def test_with_tenant_filter(self):
        db = _mock_db()
        mock_count = MagicMock()
        mock_count.scalar_one.return_value = 1
        mock_list = MagicMock()
        mock_list.scalars.return_value.all.return_value = [_mock_subscription(tenant_id="acme")]
        db.execute = AsyncMock(side_effect=[mock_count, mock_list])
        repo = MCPSubscriptionRepository(db)
        items, total = await repo.list_pending(tenant_id="acme")
        assert total == 1


class TestSubscriptionUpdateStatus:
    async def test_approve(self):
        db = _mock_db()
        sub = _mock_subscription()
        repo = MCPSubscriptionRepository(db)
        result = await repo.update_status(sub, MCPSubscriptionStatus.ACTIVE, actor_id="admin-1")
        assert sub.status == MCPSubscriptionStatus.ACTIVE
        assert sub.approved_by == "admin-1"
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(sub)

    async def test_revoke(self):
        db = _mock_db()
        sub = _mock_subscription()
        repo = MCPSubscriptionRepository(db)
        result = await repo.update_status(sub, MCPSubscriptionStatus.REVOKED, reason="expired", actor_id="admin-1")
        assert sub.status == MCPSubscriptionStatus.REVOKED
        assert sub.status_reason == "expired"
        assert sub.revoked_by == "admin-1"


class TestSubscriptionSetApiKey:
    async def test_set_key(self):
        db = _mock_db()
        sub = _mock_subscription()
        repo = MCPSubscriptionRepository(db)
        result = await repo.set_api_key(sub, "hash-xyz", "sk-xyz", vault_path="/path/key")
        assert sub.api_key_hash == "hash-xyz"
        assert sub.api_key_prefix == "sk-xyz"
        assert sub.vault_path == "/path/key"


class TestSubscriptionRotateKey:
    async def test_rotate(self):
        db = _mock_db()
        sub = _mock_subscription(api_key_hash="old-hash", rotation_count=0)
        repo = MCPSubscriptionRepository(db)
        result = await repo.rotate_key(sub, "new-hash", "sk-new", grace_period_hours=12)
        assert sub.previous_api_key_hash == "old-hash"
        assert sub.api_key_hash == "new-hash"
        assert sub.rotation_count == 1


class TestSubscriptionUpdateUsage:
    async def test_update_usage(self):
        db = _mock_db()
        sub = _mock_subscription(usage_count=5)
        repo = MCPSubscriptionRepository(db)
        result = await repo.update_usage(sub)
        assert sub.usage_count == 6
        db.flush.assert_called_once()


class TestSubscriptionSetExpiration:
    async def test_set_expiry(self):
        db = _mock_db()
        sub = _mock_subscription()
        expiry = datetime(2026, 12, 31)
        repo = MCPSubscriptionRepository(db)
        result = await repo.set_expiration(sub, expiry)
        assert sub.expires_at == expiry

    async def test_remove_expiry(self):
        db = _mock_db()
        sub = _mock_subscription()
        repo = MCPSubscriptionRepository(db)
        result = await repo.set_expiration(sub, None)
        assert sub.expires_at is None


class TestSubscriptionGetStats:
    async def test_stats_with_tenant(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 10
        mock_status = MagicMock()
        mock_status.__iter__ = MagicMock(return_value=iter([]))
        mock_recent = MagicMock()
        mock_recent.scalar_one.return_value = 2
        mock_server = MagicMock()
        mock_server.__iter__ = MagicMock(return_value=iter([]))
        db.execute = AsyncMock(side_effect=[mock_total, mock_status, mock_recent, mock_server])
        repo = MCPSubscriptionRepository(db)
        stats = await repo.get_stats(tenant_id="acme")
        assert stats["total_subscriptions"] == 10
        assert stats["recent_24h"] == 2
        assert "by_status" in stats
        assert "by_server" in stats

    async def test_stats_global(self):
        db = _mock_db()
        mock_total = MagicMock()
        mock_total.scalar_one.return_value = 50
        mock_status = MagicMock()
        mock_status.__iter__ = MagicMock(return_value=iter([]))
        mock_recent = MagicMock()
        mock_recent.scalar_one.return_value = 5
        mock_server = MagicMock()
        mock_server.__iter__ = MagicMock(return_value=iter([]))
        db.execute = AsyncMock(side_effect=[mock_total, mock_status, mock_recent, mock_server])
        repo = MCPSubscriptionRepository(db)
        stats = await repo.get_stats()
        assert stats["total_subscriptions"] == 50


# ── MCPToolAccessRepository ──


class TestToolAccessCreate:
    async def test_create(self):
        db = _mock_db()
        ta = _mock_tool_access()
        repo = MCPToolAccessRepository(db)
        result = await repo.create(ta)
        db.add.assert_called_once_with(ta)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(ta)
        assert result is ta


class TestToolAccessCreateMany:
    async def test_create_many(self):
        db = _mock_db()
        accesses = [_mock_tool_access() for _ in range(3)]
        repo = MCPToolAccessRepository(db)
        result = await repo.create_many(accesses)
        db.add_all.assert_called_once_with(accesses)
        db.flush.assert_called_once()
        assert result == accesses


class TestToolAccessGetBySubscriptionAndTool:
    async def test_found(self):
        db = _mock_db()
        ta = _mock_tool_access()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ta
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPToolAccessRepository(db)
        result = await repo.get_by_subscription_and_tool(uuid4(), uuid4())
        assert result is ta


class TestToolAccessListBySubscription:
    async def test_returns_list(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_tool_access(), _mock_tool_access()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = MCPToolAccessRepository(db)
        items = await repo.list_by_subscription(uuid4())
        assert len(items) == 2


class TestToolAccessUpdateStatus:
    async def test_enable(self):
        db = _mock_db()
        ta = _mock_tool_access(status=MCPToolAccessStatus.DISABLED)
        repo = MCPToolAccessRepository(db)
        result = await repo.update_status(ta, MCPToolAccessStatus.ENABLED, actor_id="admin-1")
        assert ta.status == MCPToolAccessStatus.ENABLED
        assert ta.granted_by == "admin-1"

    async def test_disable(self):
        db = _mock_db()
        ta = _mock_tool_access(status=MCPToolAccessStatus.ENABLED)
        repo = MCPToolAccessRepository(db)
        result = await repo.update_status(ta, MCPToolAccessStatus.DISABLED)
        assert ta.status == MCPToolAccessStatus.DISABLED


class TestToolAccessUpdateUsage:
    async def test_increments_count(self):
        db = _mock_db()
        ta = _mock_tool_access(usage_count=3)
        repo = MCPToolAccessRepository(db)
        result = await repo.update_usage(ta)
        assert ta.usage_count == 4
        db.flush.assert_called_once()
