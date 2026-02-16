"""Tests for IAMSyncService (CAB-1291 + CAB-1292)"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.iam_sync_service import IAMSyncService


class TestInit:
    def test_defaults(self):
        svc = IAMSyncService()
        assert svc._last_sync is None


class TestHandleTenantEvent:
    async def test_missing_tenant_id(self):
        svc = IAMSyncService()
        await svc.handle_tenant_event({"type": "tenant-created"})

    async def test_tenant_created_calls_sync(self):
        svc = IAMSyncService()
        svc.sync_tenant = AsyncMock(return_value={"actions": [], "errors": []})
        await svc.handle_tenant_event({"type": "tenant-created", "tenant_id": "acme"})
        svc.sync_tenant.assert_called_once_with("acme")

    async def test_user_added_calls_sync_user(self):
        svc = IAMSyncService()
        svc._sync_user = AsyncMock(return_value=True)
        await svc.handle_tenant_event({
            "type": "user-added",
            "tenant_id": "acme",
            "payload": {"email": "alice@acme.com", "roles": ["admin"]},
        })
        svc._sync_user.assert_called_once_with("acme", {"email": "alice@acme.com", "roles": ["admin"]})

    async def test_unknown_event_type(self):
        svc = IAMSyncService()
        await svc.handle_tenant_event({"type": "unknown", "tenant_id": "acme"})


class TestHandleTenantEventDeleted:
    async def test_full_cleanup(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_clients = AsyncMock(return_value=[
                {"id": "c1", "clientId": "acme-app1"},
            ])
            mock_kc.delete_client = AsyncMock()
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.remove_user_from_group = AsyncMock(return_value=True)
            mock_kc.delete_tenant_group = AsyncMock(return_value=True)

            await svc.handle_tenant_event({"type": "tenant-deleted", "tenant_id": "acme"})

            mock_kc.delete_client.assert_called_once_with("c1")
            mock_kc.remove_user_from_group.assert_called_once_with("u1", "acme")
            mock_kc.delete_tenant_group.assert_called_once_with("acme")

    async def test_partial_failure_continues(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_clients = AsyncMock(return_value=[
                {"id": "c1", "clientId": "acme-app1"},
            ])
            mock_kc.delete_client = AsyncMock(side_effect=Exception("client error"))
            mock_kc.get_users = AsyncMock(return_value=[])
            mock_kc.delete_tenant_group = AsyncMock(return_value=True)

            # Should not raise despite client deletion failure
            await svc.handle_tenant_event({"type": "tenant-deleted", "tenant_id": "acme"})
            mock_kc.delete_tenant_group.assert_called_once_with("acme")

    async def test_empty_tenant(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_clients = AsyncMock(return_value=[])
            mock_kc.get_users = AsyncMock(return_value=[])
            mock_kc.delete_tenant_group = AsyncMock(return_value=True)

            await svc.handle_tenant_event({"type": "tenant-deleted", "tenant_id": "acme"})
            mock_kc.delete_tenant_group.assert_called_once_with("acme")


class TestHandleTenantEventUserRemoved:
    async def test_removes_user_from_group(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.remove_user_from_group = AsyncMock(return_value=True)

            await svc.handle_tenant_event({
                "type": "user-removed",
                "tenant_id": "acme",
                "payload": {"email": "alice@acme.com"},
            })
            mock_kc.remove_user_from_group.assert_called_once_with("u1", "acme")

    async def test_user_not_found(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_users = AsyncMock(return_value=[])
            # Should not raise
            await svc.handle_tenant_event({
                "type": "user-removed",
                "tenant_id": "acme",
                "payload": {"email": "unknown@acme.com"},
            })

    async def test_kc_failure_logged(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.remove_user_from_group = AsyncMock(side_effect=Exception("KC error"))
            # Should not raise, just log error
            await svc.handle_tenant_event({
                "type": "user-removed",
                "tenant_id": "acme",
                "payload": {"email": "alice@acme.com"},
            })


class TestSyncTenant:
    async def test_tenant_not_in_git(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git.get_tenant = AsyncMock(return_value=None)
            result = await svc.sync_tenant("missing")
        assert len(result["errors"]) == 1
        assert "not found" in result["errors"][0]

    async def test_tenant_found_syncs_group(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_tenant = AsyncMock(return_value={"display_name": "ACME"})
            mock_git.get_file = AsyncMock(return_value=None)
            mock_kc.setup_tenant_group = AsyncMock()
            result = await svc.sync_tenant("acme")
        assert any("Ensured group" in a for a in result["actions"])

    async def test_syncs_users_from_config(self):
        svc = IAMSyncService()
        svc._sync_user = AsyncMock(return_value=True)
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_tenant = AsyncMock(return_value={"display_name": "ACME"})
            mock_kc.setup_tenant_group = AsyncMock()
            mock_git.get_file = AsyncMock(
                return_value="users:\n  - email: alice@acme.com\n    roles: [admin]"
            )
            result = await svc.sync_tenant("acme")
        assert svc._sync_user.call_count == 1
        assert any("Synced user" in a for a in result["actions"])

    async def test_exception_returns_error(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git.get_tenant = AsyncMock(side_effect=Exception("connection error"))
            result = await svc.sync_tenant("acme")
        assert len(result["errors"]) == 1


class TestSyncUser:
    async def test_no_email(self):
        svc = IAMSyncService()
        result = await svc._sync_user("acme", {})
        assert result is False

    async def test_existing_user_assign_roles(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.assign_role = AsyncMock()
            result = await svc._sync_user("acme", {"email": "alice@acme.com", "roles": ["admin"]})
        assert result is True
        mock_kc.assign_role.assert_called_once_with("u1", "admin")

    async def test_new_user_created(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_users = AsyncMock(return_value=[])
            mock_kc.create_user = AsyncMock()
            result = await svc._sync_user("acme", {
                "email": "bob@acme.com",
                "username": "bob",
                "first_name": "Bob",
                "last_name": "Smith",
                "roles": ["viewer"],
            })
        assert result is True
        mock_kc.create_user.assert_called_once()

    async def test_default_roles_viewer(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u2", "email": "carol@acme.com"},
            ])
            mock_kc.assign_role = AsyncMock()
            await svc._sync_user("acme", {"email": "carol@acme.com"})
        mock_kc.assign_role.assert_called_once_with("u2", "viewer")


class TestSyncAllTenants:
    async def test_git_not_connected(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git._project = None
            result = await svc.sync_all_tenants()
        assert "GitLab not connected" in result.get("errors", [])

    async def test_syncs_each_tenant(self):
        svc = IAMSyncService()
        svc.sync_tenant = AsyncMock(return_value={"actions": ["a"], "errors": []})
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git._project = MagicMock()
            mock_git._project.repository_tree.return_value = [
                {"type": "tree", "name": "acme"},
                {"type": "tree", "name": "corp"},
                {"type": "blob", "name": ".gitkeep"},
            ]
            result = await svc.sync_all_tenants()
        assert svc.sync_tenant.call_count == 2
        assert result["total_actions"] == 2
        assert svc._last_sync is not None


class TestReconcileTenant:
    async def test_in_sync(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_file = AsyncMock(
                return_value="users:\n  - email: alice@acme.com\n    roles: [viewer]"
            )
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.get_user_roles = AsyncMock(return_value=["viewer"])
            result = await svc.reconcile_tenant("acme")
        assert result["in_sync"] is True
        assert result["drift"] == []

    async def test_drift_detected(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_file = AsyncMock(
                return_value="users:\n  - email: alice@acme.com\n  - email: bob@acme.com"
            )
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
                {"id": "u3", "email": "charlie@acme.com"},
            ])
            mock_kc.get_user_roles = AsyncMock(return_value=["viewer"])
            result = await svc.reconcile_tenant("acme")
        assert result["in_sync"] is False
        drift_types = {d["type"] for d in result["drift"]}
        assert "missing_user" in drift_types
        assert "extra_user" in drift_types


class TestReconcileTenantRoleDrift:
    async def test_missing_role(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_file = AsyncMock(
                return_value="users:\n  - email: alice@acme.com\n    roles: [admin, viewer]"
            )
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.get_user_roles = AsyncMock(return_value=["viewer"])
            result = await svc.reconcile_tenant("acme")
        assert result["in_sync"] is False
        missing = [d for d in result["drift"] if d["type"] == "missing_role"]
        assert len(missing) == 1
        assert missing[0]["role"] == "admin"

    async def test_extra_role(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_file = AsyncMock(
                return_value="users:\n  - email: alice@acme.com\n    roles: [viewer]"
            )
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.get_user_roles = AsyncMock(return_value=["viewer", "admin"])
            result = await svc.reconcile_tenant("acme")
        assert result["in_sync"] is False
        extra = [d for d in result["drift"] if d["type"] == "extra_role"]
        assert len(extra) == 1
        assert extra[0]["role"] == "admin"

    async def test_roles_in_sync(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_file = AsyncMock(
                return_value="users:\n  - email: alice@acme.com\n    roles: [admin, viewer]"
            )
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.get_user_roles = AsyncMock(return_value=["admin", "viewer"])
            result = await svc.reconcile_tenant("acme")
        assert result["in_sync"] is True
        assert result["drift"] == []


class TestCreateApplicationClient:
    async def test_creates_and_emits(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc,              patch("src.services.iam_sync_service.kafka_service") as mock_kafka:
            mock_kc.create_client = AsyncMock(return_value={
                "client_id": "acme-myapp",
                "client_secret": "secret123",
            })
            mock_kafka.publish = AsyncMock()
            result = await svc.create_application_client(
                "acme", "myapp", "My App", ["http://localhost:3000/callback"]
            )
        assert result["client_id"] == "acme-myapp"
        mock_kafka.publish.assert_called_once()

    async def test_failure_raises(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.create_client = AsyncMock(side_effect=Exception("KC error"))
            with pytest.raises(Exception, match="KC error"):
                await svc.create_application_client("acme", "bad", "Bad", [])


class TestRotateClientSecret:
    async def test_rotates_and_emits(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc,              patch("src.services.iam_sync_service.kafka_service") as mock_kafka:
            mock_kc.get_client = AsyncMock(return_value={"id": "uuid-1"})
            mock_kc.regenerate_client_secret = AsyncMock(return_value="new-secret")
            mock_kafka.publish = AsyncMock()
            result = await svc.rotate_client_secret("acme", "myapp")
        assert result == "new-secret"
        mock_kafka.publish.assert_called_once()

    async def test_client_not_found(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_client = AsyncMock(return_value=None)
            with pytest.raises(ValueError, match="not found"):
                await svc.rotate_client_secret("acme", "nonexistent")
