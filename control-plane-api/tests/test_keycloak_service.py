"""Tests for KeycloakService (CAB-1291)"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.keycloak_service import KeycloakService


@pytest.fixture
def svc():
    s = KeycloakService()
    s._admin = MagicMock()
    return s


@pytest.fixture
def disconnected_svc():
    return KeycloakService()


# ── Connection ──


class TestConnect:
    async def test_connect_sets_admin(self):
        svc = KeycloakService()
        with patch("src.services.keycloak_service.KeycloakOpenIDConnection"), \
             patch("src.services.keycloak_service.KeycloakAdmin") as mock_admin:
            mock_admin.return_value = MagicMock()
            await svc.connect()
            assert svc._admin is not None

    async def test_connect_error_raises(self):
        svc = KeycloakService()
        with (
            patch("src.services.keycloak_service.KeycloakOpenIDConnection", side_effect=Exception("fail")),
            pytest.raises(Exception, match="fail"),
        ):
            await svc.connect()


class TestDisconnect:
    async def test_disconnect_clears_admin(self, svc):
        await svc.disconnect()
        assert svc._admin is None


# ── Users ──


class TestGetUsers:
    async def test_not_connected(self, disconnected_svc):
        with pytest.raises(RuntimeError, match="not connected"):
            await disconnected_svc.get_users()

    async def test_all_users(self, svc):
        svc._admin.get_users.return_value = [{"id": "u1"}, {"id": "u2"}]
        users = await svc.get_users()
        assert len(users) == 2

    async def test_filter_by_tenant(self, svc):
        svc._admin.get_users.return_value = [
            {"id": "u1", "attributes": {"tenant_id": ["acme"]}},
            {"id": "u2", "attributes": {"tenant_id": ["globex"]}},
        ]
        users = await svc.get_users(tenant_id="acme")
        assert len(users) == 1
        assert users[0]["id"] == "u1"


class TestGetUser:
    async def test_found(self, svc):
        svc._admin.get_user.return_value = {"id": "u1", "username": "alice"}
        user = await svc.get_user("u1")
        assert user["username"] == "alice"

    async def test_not_found(self, svc):
        svc._admin.get_user.side_effect = Exception("not found")
        user = await svc.get_user("bad")
        assert user is None

    async def test_not_connected(self, disconnected_svc):
        with pytest.raises(RuntimeError):
            await disconnected_svc.get_user("u1")


class TestCreateUser:
    async def test_creates_with_roles(self, svc):
        svc._admin.create_user.return_value = "new-uid"
        svc._admin.get_realm_role.return_value = {"name": "viewer"}
        uid = await svc.create_user("alice", "alice@ex.com", "Alice", "A", "acme", ["viewer"])
        assert uid == "new-uid"
        svc._admin.assign_realm_roles.assert_called_once()

    async def test_creates_with_password(self, svc):
        svc._admin.create_user.return_value = "uid"
        svc._admin.get_realm_role.return_value = {"name": "viewer"}
        await svc.create_user("bob", "bob@ex.com", "Bob", "B", "acme", ["viewer"], temporary_password="pass123")  # noqa: S106
        call_args = svc._admin.create_user.call_args[0][0]
        assert "credentials" in call_args
        assert call_args["credentials"][0]["temporary"] is True

    async def test_not_connected(self, disconnected_svc):
        with pytest.raises(RuntimeError):
            await disconnected_svc.create_user("a", "b", "c", "d", "e", [])


class TestUpdateUser:
    async def test_updates(self, svc):
        result = await svc.update_user("u1", {"firstName": "Bob"})
        assert result is True
        svc._admin.update_user.assert_called_once_with("u1", {"firstName": "Bob"})

    async def test_not_connected(self, disconnected_svc):
        with pytest.raises(RuntimeError):
            await disconnected_svc.update_user("u1", {})


class TestDeleteUser:
    async def test_deletes(self, svc):
        result = await svc.delete_user("u1")
        assert result is True
        svc._admin.delete_user.assert_called_once_with("u1")


# ── Roles ──


class TestGetRoles:
    async def test_returns_roles(self, svc):
        svc._admin.get_realm_roles.return_value = [{"name": "admin"}]
        roles = await svc.get_roles()
        assert len(roles) == 1


class TestAssignRole:
    async def test_assigns(self, svc):
        svc._admin.get_realm_role.return_value = {"name": "viewer"}
        result = await svc.assign_role("u1", "viewer")
        assert result is True


class TestRemoveRole:
    async def test_removes(self, svc):
        svc._admin.get_realm_role.return_value = {"name": "viewer"}
        result = await svc.remove_role("u1", "viewer")
        assert result is True
        svc._admin.delete_realm_roles_of_user.assert_called_once()


# ── Clients ──


class TestGetClients:
    async def test_all(self, svc):
        svc._admin.get_clients.return_value = [{"clientId": "a"}, {"clientId": "b"}]
        clients = await svc.get_clients()
        assert len(clients) == 2

    async def test_filter_by_tenant_attr(self, svc):
        svc._admin.get_clients.return_value = [
            {"clientId": "acme-app", "attributes": {"tenant_id": ["acme"]}},
            {"clientId": "globex-app", "attributes": {"tenant_id": ["globex"]}},
        ]
        clients = await svc.get_clients(tenant_id="acme")
        assert len(clients) == 1

    async def test_filter_by_tenant_prefix(self, svc):
        svc._admin.get_clients.return_value = [
            {"clientId": "acme-my-app", "attributes": {}},
        ]
        clients = await svc.get_clients(tenant_id="acme")
        assert len(clients) == 1


class TestGetClient:
    async def test_found(self, svc):
        svc._admin.get_clients.return_value = [
            {"clientId": "app-1", "id": "uuid-1"},
            {"clientId": "app-2", "id": "uuid-2"},
        ]
        client = await svc.get_client("app-2")
        assert client["id"] == "uuid-2"

    async def test_not_found(self, svc):
        svc._admin.get_clients.return_value = []
        client = await svc.get_client("missing")
        assert client is None


class TestCreateClient:
    async def test_creates(self, svc):
        svc._admin.create_client.return_value = None
        svc._admin.get_clients.return_value = [{"clientId": "acme-myapp", "id": "uuid-1"}]
        svc._admin.get_client_secrets.return_value = {"value": "secret-123"}
        result = await svc.create_client("acme", "myapp", "My App", ["http://localhost"])
        assert result["client_id"] == "acme-myapp"
        assert result["client_secret"] == "secret-123"

    async def test_create_fails(self, svc):
        svc._admin.create_client.return_value = None
        svc._admin.get_clients.return_value = []  # client not found after create
        with pytest.raises(RuntimeError, match="Failed to create client"):
            await svc.create_client("acme", "myapp", "My App", [])


class TestUpdateClient:
    async def test_updates(self, svc):
        result = await svc.update_client("uuid-1", {"enabled": False})
        assert result is True


class TestDeleteClient:
    async def test_deletes(self, svc):
        result = await svc.delete_client("uuid-1")
        assert result is True


class TestRegenerateSecret:
    async def test_regenerates(self, svc):
        svc._admin.generate_client_secrets.return_value = {"value": "new-secret"}
        secret = await svc.regenerate_client_secret("uuid-1")
        assert secret == "new-secret"


# ── Consumer Clients ──


class TestCreateConsumerClient:
    async def test_basic(self, svc):
        svc._admin.create_client.return_value = None
        svc._admin.get_clients.return_value = [{"clientId": "acme-cons1", "id": "cc-uuid"}]
        svc._admin.get_client_secrets.return_value = {"value": "cc-secret"}
        result = await svc.create_consumer_client("acme", "cons1", "consumer-uuid")
        assert result["client_id"] == "acme-cons1"
        assert result["client_secret"] == "cc-secret"

    async def test_with_plan_and_rate_limit(self, svc):
        svc._admin.create_client.return_value = None
        svc._admin.get_clients.return_value = [{"clientId": "acme-cons1", "id": "cc-uuid"}]
        svc._admin.get_client_secrets.return_value = {"value": "s"}
        result = await svc.create_consumer_client(
            "acme", "cons1", "c-uuid", plan_slug="gold", rate_limit=1000
        )
        assert result["client_id"] == "acme-cons1"
        # Verify protocol mappers included plan and rate_limit
        call_args = svc._admin.create_client.call_args[0][0]
        mapper_names = [m["name"] for m in call_args["protocolMappers"]]
        assert "plan_slug" in mapper_names
        assert "rate_limit" in mapper_names

    async def test_create_fails(self, svc):
        svc._admin.create_client.return_value = None
        svc._admin.get_clients.return_value = []
        with pytest.raises(RuntimeError, match="Failed to create consumer"):
            await svc.create_consumer_client("acme", "cons1", "c-uuid")


class TestCreateConsumerClientWithCert:
    async def test_creates_mtls_client(self, svc):
        svc._admin.create_client.return_value = None
        svc._admin.get_clients.return_value = [{"clientId": "acme-cons1", "id": "uuid"}]
        svc._admin.get_client_secrets.return_value = {"value": "secret"}
        result = await svc.create_consumer_client_with_cert("acme", "cons1", "c-uuid", "thumbprint")
        assert result["client_id"] == "acme-cons1"
        call_args = svc._admin.create_client.call_args[0][0]
        mapper_names = [m["name"] for m in call_args["protocolMappers"]]
        assert "cnf-x5t-s256" in mapper_names
        assert call_args["attributes"]["mtls_enabled"] == "true"


class TestUpdateConsumerClientCnf:
    async def test_update_existing_mapper(self, svc):
        svc._admin.get_clients.return_value = [{
            "clientId": "acme-cons1", "id": "uuid",
            "protocolMappers": [{"name": "cnf-x5t-s256", "config": {"claim.value": "old"}}],
        }]
        result = await svc.update_consumer_client_cnf("acme-cons1", "new-thumb")
        assert result is True

    async def test_add_new_mapper(self, svc):
        svc._admin.get_clients.return_value = [{
            "clientId": "acme-cons1", "id": "uuid",
            "protocolMappers": [],
        }]
        result = await svc.update_consumer_client_cnf("acme-cons1", "new-thumb")
        assert result is True

    async def test_client_not_found(self, svc):
        svc._admin.get_clients.return_value = []
        with pytest.raises(RuntimeError, match="not found"):
            await svc.update_consumer_client_cnf("missing", "thumb")


class TestDisableConsumerClient:
    async def test_disables(self, svc):
        svc._admin.get_clients.return_value = [{"clientId": "acme-cons1", "id": "uuid"}]
        result = await svc.disable_consumer_client("acme-cons1")
        assert result is True
        svc._admin.update_client.assert_called_once_with("uuid", {"enabled": False})

    async def test_not_found(self, svc):
        svc._admin.get_clients.return_value = []
        result = await svc.disable_consumer_client("missing")
        assert result is False


class TestDeleteConsumerClient:
    async def test_deletes(self, svc):
        svc._admin.get_clients.return_value = [{"clientId": "acme-cons1", "id": "uuid"}]
        result = await svc.delete_consumer_client("acme-cons1")
        assert result is True

    async def test_not_found(self, svc):
        svc._admin.get_clients.return_value = []
        result = await svc.delete_consumer_client("missing")
        assert result is False


# ── Token Exchange ──


class TestExchangeToken:
    async def test_basic_exchange(self, svc):
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "new-token", "token_type": "bearer"}
        mock_response.raise_for_status = MagicMock()

        with patch("src.services.keycloak_service.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await svc.exchange_token("client-id", "client-secret", "subject-token")
        assert result["access_token"] == "new-token"

    async def test_with_audience_and_scope(self, svc):
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "t"}
        mock_response.raise_for_status = MagicMock()

        with patch("src.services.keycloak_service.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await svc.exchange_token(
                "cid", "cs", "st", audience="aud", scope="openid"
            )
        assert result["access_token"] == "t"


# ── Service Accounts ──


class TestCreateServiceAccount:
    async def test_creates_sa(self, svc):
        svc._admin.create_client.return_value = None
        # client_id = sa-acme-alice-claude-desktop
        svc._admin.get_clients.side_effect = [
            [],  # first call: check existing
            [{"clientId": "sa-acme-alice-claude-desktop", "id": "sa-uuid"}],  # after create
        ]
        svc._admin.get_client_secrets.return_value = {"value": "sa-secret"}
        svc._admin.get_client_service_account_user.return_value = {"id": "sa-user-id"}
        svc._admin.get_realm_role.return_value = {"name": "viewer"}

        result = await svc.create_service_account(
            "user-1", "alice@example.com", "acme", "claude-desktop", roles=["viewer"]
        )
        assert result["client_secret"] == "sa-secret"
        assert result["name"] == "claude-desktop"

    async def test_creates_with_unique_suffix(self, svc):
        """When client_id already exists, a UUID suffix is added."""
        svc._admin.create_client.return_value = None
        # First call: existing client found → suffix added
        # The actual client_id with suffix is unpredictable (UUID), so use a broader mock
        def get_clients_side_effect():
            call_count = 0
            def inner():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First call in get_client → check existing: found
                    return [{"clientId": "sa-acme-alice-claude", "id": "existing"}]
                else:
                    # Second+ calls: return a client that matches any sa-acme- prefix
                    # Since we can't predict the UUID suffix, just return a list and
                    # the test will just verify no exception is raised
                    return [{"clientId": svc._admin.create_client.call_args[0][0]["clientId"], "id": "new-uuid"}]
            return inner
        svc._admin.get_clients.side_effect = get_clients_side_effect()
        svc._admin.get_client_secrets.return_value = {"value": "s"}
        svc._admin.get_client_service_account_user.return_value = {"id": "sa-uid"}

        result = await svc.create_service_account(
            "u1", "alice@example.com", "acme", "claude"
        )
        assert result is not None

    async def test_copies_user_roles_when_none(self, svc):
        svc._admin.create_client.return_value = None
        # client_id = sa-acme-alice-cli
        svc._admin.get_clients.side_effect = [
            [],
            [{"clientId": "sa-acme-alice-cli", "id": "uuid"}],
        ]
        svc._admin.get_client_secrets.return_value = {"value": "s"}
        svc._admin.get_client_service_account_user.return_value = {"id": "sa-uid"}
        svc._admin.get_user.return_value = {"id": "u1"}
        svc._admin.get_realm_roles_of_user.return_value = [
            {"name": "viewer"},
            {"name": "default-roles-stoa"},
        ]

        result = await svc.create_service_account(
            "u1", "alice@example.com", "acme", "cli"
        )
        assert result is not None
        # Only viewer should be assigned (not default-roles-stoa)
        svc._admin.assign_realm_roles.assert_called_once()


class TestListUserServiceAccounts:
    async def test_filters_by_owner(self, svc):
        svc._admin.get_clients.return_value = [
            {"id": "c1", "clientId": "sa-acme-1", "name": "Service Account: cli",
             "description": "MCP SA", "enabled": True,
             "attributes": {"owner_user_id": "u1", "service_account_type": "mcp"}},
            {"id": "c2", "clientId": "other", "name": "Other",
             "attributes": {"owner_user_id": "u2", "service_account_type": "mcp"}},
        ]
        accounts = await svc.list_user_service_accounts("u1")
        assert len(accounts) == 1
        assert accounts[0]["client_id"] == "sa-acme-1"
        assert accounts[0]["name"] == "cli"


class TestDeleteServiceAccount:
    async def test_deletes_owned(self, svc):
        svc._admin.get_client.return_value = {
            "attributes": {"owner_user_id": "u1"},
        }
        result = await svc.delete_service_account("c-uuid", "u1")
        assert result is True

    async def test_not_found(self, svc):
        svc._admin.get_client.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await svc.delete_service_account("bad", "u1")

    async def test_not_owner(self, svc):
        svc._admin.get_client.return_value = {
            "attributes": {"owner_user_id": "other"},
        }
        with pytest.raises(PermissionError, match="Not authorized"):
            await svc.delete_service_account("c-uuid", "u1")


# ── Tenant Group ──


class TestSetupTenantGroup:
    async def test_creates_group(self, svc):
        svc._admin.create_group.return_value = "group-id"
        gid = await svc.setup_tenant_group("acme", "Acme Corp")
        assert gid == "group-id"


class TestAddUserToTenant:
    async def test_adds_with_group(self, svc):
        svc._admin.get_groups.return_value = [{"name": "acme", "id": "g1"}]
        result = await svc.add_user_to_tenant("u1", "acme")
        assert result is True
        svc._admin.group_user_add.assert_called_once_with("u1", "g1")

    async def test_adds_without_group(self, svc):
        svc._admin.get_groups.return_value = []
        result = await svc.add_user_to_tenant("u1", "acme")
        assert result is True
        svc._admin.group_user_add.assert_not_called()

# ── Remove User From Group ──


class TestRemoveUserFromGroup:
    async def test_removes_from_group(self, svc):
        svc._admin.get_groups.return_value = [{"name": "acme", "id": "g1"}]
        result = await svc.remove_user_from_group("u1", "acme")
        assert result is True
        svc._admin.group_user_remove.assert_called_once_with("u1", "g1")

    async def test_group_not_found(self, svc):
        svc._admin.get_groups.return_value = []
        result = await svc.remove_user_from_group("u1", "missing")
        assert result is True  # idempotent
        svc._admin.group_user_remove.assert_not_called()

    async def test_remove_failure_returns_false(self, svc):
        svc._admin.get_groups.return_value = [{"name": "acme", "id": "g1"}]
        svc._admin.group_user_remove.side_effect = Exception("KC error")
        result = await svc.remove_user_from_group("u1", "acme")
        assert result is False

    async def test_not_connected(self, disconnected_svc):
        with pytest.raises(RuntimeError, match="not connected"):
            await disconnected_svc.remove_user_from_group("u1", "acme")


# ── Delete Tenant Group ──


class TestDeleteTenantGroup:
    async def test_deletes_group(self, svc):
        svc._admin.get_groups.return_value = [{"name": "acme", "id": "g1"}]
        result = await svc.delete_tenant_group("acme")
        assert result is True
        svc._admin.delete_group.assert_called_once_with("g1")

    async def test_group_not_found(self, svc):
        svc._admin.get_groups.return_value = []
        result = await svc.delete_tenant_group("missing")
        assert result is True  # idempotent

    async def test_delete_failure_returns_false(self, svc):
        svc._admin.get_groups.return_value = [{"name": "acme", "id": "g1"}]
        svc._admin.delete_group.side_effect = Exception("KC error")
        result = await svc.delete_tenant_group("acme")
        assert result is False

    async def test_not_connected(self, disconnected_svc):
        with pytest.raises(RuntimeError, match="not connected"):
            await disconnected_svc.delete_tenant_group("acme")


# ── Get User Roles ──


class TestGetUserRoles:
    async def test_returns_non_system_roles(self, svc):
        svc._admin.get_realm_roles_of_user.return_value = [
            {"name": "admin"},
            {"name": "viewer"},
            {"name": "default-roles-stoa"},
            {"name": "offline_access"},
            {"name": "uma_authorization"},
        ]
        roles = await svc.get_user_roles("u1")
        assert sorted(roles) == ["admin", "viewer"]

    async def test_empty_roles(self, svc):
        svc._admin.get_realm_roles_of_user.return_value = [
            {"name": "default-roles-stoa"},
        ]
        roles = await svc.get_user_roles("u1")
        assert roles == []

    async def test_not_connected(self, disconnected_svc):
        with pytest.raises(RuntimeError, match="not connected"):
            await disconnected_svc.get_user_roles("u1")
