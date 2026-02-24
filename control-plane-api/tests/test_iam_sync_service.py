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


# ── Additional coverage for uncovered branches ──


class TestSyncTenantWithApps:
    """Tests for the applications sync branch inside sync_tenant()."""

    async def test_syncs_applications_from_config(self):
        """sync_tenant() calls _sync_application for each app in the config."""
        svc = IAMSyncService()
        svc._sync_application = AsyncMock(return_value=True)
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_tenant = AsyncMock(return_value={"display_name": "ACME"})
            mock_kc.setup_tenant_group = AsyncMock()
            # get_file: first call = users (None), second = apps
            mock_git.get_file = AsyncMock(side_effect=[
                None,  # users.yaml → no users
                "applications:\n  - name: myapp\n    display_name: My App\n    redirect_uris: []\n",
            ])
            result = await svc.sync_tenant("acme")
        assert svc._sync_application.call_count == 1
        assert any("Synced application" in a for a in result["actions"])

    async def test_app_sync_error_goes_to_errors(self):
        """A failing _sync_application appends to errors, does not abort."""
        svc = IAMSyncService()
        svc._sync_application = AsyncMock(side_effect=Exception("KC error"))
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_tenant = AsyncMock(return_value={"display_name": "ACME"})
            mock_kc.setup_tenant_group = AsyncMock()
            mock_git.get_file = AsyncMock(side_effect=[
                None,
                "applications:\n  - name: badapp\n",
            ])
            result = await svc.sync_tenant("acme")
        assert any("Failed to sync app" in e for e in result["errors"])

    async def test_user_sync_error_goes_to_errors(self):
        """A failing _sync_user appends to errors, does not abort."""
        svc = IAMSyncService()
        svc._sync_user = AsyncMock(side_effect=Exception("user error"))
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_tenant = AsyncMock(return_value={"display_name": "ACME"})
            mock_kc.setup_tenant_group = AsyncMock()
            mock_git.get_file = AsyncMock(side_effect=[
                "users:\n  - email: bad@acme.com\n",
                None,
            ])
            result = await svc.sync_tenant("acme")
        assert any("Failed to sync user" in e for e in result["errors"])

    async def test_group_setup_exception_is_logged_not_raised(self):
        """setup_tenant_group failing should be swallowed (may already exist)."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_tenant = AsyncMock(return_value={"display_name": "ACME"})
            mock_kc.setup_tenant_group = AsyncMock(side_effect=Exception("group exists"))
            mock_git.get_file = AsyncMock(return_value=None)
            # Should not raise
            result = await svc.sync_tenant("acme")
        # The group error is not added to result["errors"] (only logged)
        assert result["tenant_id"] == "acme"


class TestSyncUserCreateRaisesOnFailure:
    async def test_create_user_exception_propagates(self):
        """_sync_user() re-raises when create_user fails (so caller can catch it)."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_users = AsyncMock(return_value=[])
            mock_kc.create_user = AsyncMock(side_effect=Exception("KC create failed"))
            with pytest.raises(Exception, match="KC create failed"):
                await svc._sync_user("acme", {
                    "email": "new@acme.com",
                    "roles": ["viewer"],
                })

    async def test_assign_role_failure_is_logged_not_raised(self):
        """_sync_user() logs role assignment failures but still returns True."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.assign_role = AsyncMock(side_effect=Exception("role not found"))
            result = await svc._sync_user("acme", {
                "email": "alice@acme.com",
                "roles": ["nonexistent-role"],
            })
        assert result is True  # failure is swallowed for role assignment


class TestSyncApplication:
    async def test_updates_existing_client_with_subscriptions(self):
        """_sync_application() updates attributes when client exists and has api_subscriptions."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_client = AsyncMock(return_value={
                "id": "uuid-1",
                "attributes": {"tenant_id": "acme"},
            })
            mock_kc.update_client = AsyncMock(return_value=True)

            result = await svc._sync_application("acme", {
                "name": "myapp",
                "api_subscriptions": ["api-1", "api-2"],
            })

        assert result is True
        call_attrs = mock_kc.update_client.call_args[0][1]["attributes"]
        import json
        assert json.loads(call_attrs["api_subscriptions"]) == ["api-1", "api-2"]

    async def test_updates_existing_client_without_subscriptions(self):
        """_sync_application() updates client even without api_subscriptions key."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_client = AsyncMock(return_value={
                "id": "uuid-1",
                "attributes": {},
            })
            mock_kc.update_client = AsyncMock(return_value=True)

            result = await svc._sync_application("acme", {"name": "myapp"})

        assert result is True
        mock_kc.update_client.assert_called_once()

    async def test_creates_new_client_when_not_found(self):
        """_sync_application() creates a new KC client when it doesn't exist."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_kc.get_client = AsyncMock(return_value=None)
            mock_kc.create_client = AsyncMock(return_value={
                "client_id": "acme-newapp", "client_secret": "s",
            })

            result = await svc._sync_application("acme", {
                "name": "newapp",
                "display_name": "New App",
                "redirect_uris": ["http://localhost/cb"],
                "description": "desc",
            })

        assert result is True
        mock_kc.create_client.assert_called_once()
        call_kwargs = mock_kc.create_client.call_args[1]
        assert call_kwargs["tenant_id"] == "acme"
        assert call_kwargs["name"] == "newapp"

    async def test_returns_false_when_no_name(self):
        """_sync_application() returns False immediately when app has no name."""
        svc = IAMSyncService()
        result = await svc._sync_application("acme", {})
        assert result is False


class TestGetTenantUsersConfig:
    async def test_returns_parsed_yaml(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git.get_file = AsyncMock(
                return_value="users:\n  - email: alice@acme.com\n"
            )
            result = await svc._get_tenant_users_config("acme")
        assert result is not None
        assert result["users"][0]["email"] == "alice@acme.com"

    async def test_returns_none_when_file_not_found(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git.get_file = AsyncMock(return_value=None)
            result = await svc._get_tenant_users_config("acme")
        assert result is None

    async def test_returns_none_on_exception(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git.get_file = AsyncMock(side_effect=Exception("git error"))
            result = await svc._get_tenant_users_config("acme")
        assert result is None


class TestGetTenantAppsConfig:
    async def test_returns_parsed_yaml(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git.get_file = AsyncMock(
                return_value="applications:\n  - name: myapp\n"
            )
            result = await svc._get_tenant_apps_config("acme")
        assert result is not None
        assert result["applications"][0]["name"] == "myapp"

    async def test_returns_none_when_file_not_found(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git.get_file = AsyncMock(return_value=None)
            result = await svc._get_tenant_apps_config("acme")
        assert result is None

    async def test_returns_none_on_exception(self):
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git.get_file = AsyncMock(side_effect=Exception("git error"))
            result = await svc._get_tenant_apps_config("acme")
        assert result is None


class TestReconcileTenantEdgeCases:
    async def test_empty_gitops_state(self):
        """reconcile_tenant() handles empty GitOps config (no users.yaml)."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_file = AsyncMock(return_value=None)
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "ghost@acme.com"},
            ])
            result = await svc.reconcile_tenant("acme")
        # ghost@acme.com is extra (in KC, not in GitOps)
        assert result["in_sync"] is False
        extra = [d for d in result["drift"] if d["type"] == "extra_user"]
        assert len(extra) == 1

    async def test_exception_in_get_user_roles_skipped(self):
        """reconcile_tenant() continues when get_user_roles raises for one user."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_file = AsyncMock(
                return_value="users:\n  - email: alice@acme.com\n    roles: [admin]"
            )
            mock_kc.get_users = AsyncMock(return_value=[
                {"id": "u1", "email": "alice@acme.com"},
            ])
            mock_kc.get_user_roles = AsyncMock(side_effect=Exception("KC error"))
            # Should not raise; the user is just skipped
            result = await svc.reconcile_tenant("acme")
        # in_sync may be True (no role drift reported since we skipped)
        assert "error" not in result or result.get("error") is None

    async def test_outer_exception_returns_error_field(self):
        """reconcile_tenant() returns report with error field on top-level exception."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git, \
             patch("src.services.iam_sync_service.keycloak_service") as mock_kc:
            mock_git.get_file = AsyncMock(
                return_value="users:\n  - email: alice@acme.com"
            )
            mock_kc.get_users = AsyncMock(side_effect=Exception("KC down"))
            result = await svc.reconcile_tenant("acme")
        assert "error" in result


class TestSyncAllTenantsException:
    async def test_exception_adds_errors(self):
        """sync_all_tenants() catches top-level exception and adds to result."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.git_service") as mock_git:
            mock_git._project = MagicMock()
            mock_git._project.repository_tree.side_effect = Exception("GitLab down")
            result = await svc.sync_all_tenants()
        assert "errors" in result
        assert len(result["errors"]) > 0


class TestHandleTenantEventUserRemovedNoEmail:
    async def test_no_email_in_payload(self):
        """user-removed event with no email is silently ignored."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service"):
            # Should not raise
            await svc.handle_tenant_event({
                "type": "user-removed",
                "tenant_id": "acme",
                "payload": {},  # no email field
            })


class TestCreateApplicationClientKafkaPayload:
    async def test_emits_correct_kafka_event(self):
        """create_application_client() publishes event with app_name and client_id."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc, \
             patch("src.services.iam_sync_service.kafka_service") as mock_kafka:
            mock_kc.create_client = AsyncMock(return_value={
                "client_id": "acme-portal",
                "client_secret": "secret",
                "id": "uuid-1",
            })
            mock_kafka.publish = AsyncMock()

            await svc.create_application_client(
                "acme", "portal", "ACME Portal", ["http://app/cb"]
            )

        call_kwargs = mock_kafka.publish.call_args[1]
        assert call_kwargs["event_type"] == "app-client-created"
        assert call_kwargs["tenant_id"] == "acme"
        assert call_kwargs["payload"]["app_name"] == "portal"
        assert call_kwargs["payload"]["client_id"] == "acme-portal"


class TestRotateClientSecretKafkaPayload:
    async def test_emits_correct_kafka_event(self):
        """rotate_client_secret() publishes event with app_name and client_id."""
        svc = IAMSyncService()
        with patch("src.services.iam_sync_service.keycloak_service") as mock_kc, \
             patch("src.services.iam_sync_service.kafka_service") as mock_kafka:
            mock_kc.get_client = AsyncMock(return_value={"id": "uuid-1"})
            mock_kc.regenerate_client_secret = AsyncMock(return_value="brand-new-secret")
            mock_kafka.publish = AsyncMock()

            result = await svc.rotate_client_secret("acme", "portal")

        assert result == "brand-new-secret"
        call_kwargs = mock_kafka.publish.call_args[1]
        assert call_kwargs["event_type"] == "app-secret-rotated"
        assert call_kwargs["payload"]["app_name"] == "portal"
        assert call_kwargs["payload"]["client_id"] == "acme-portal"
