"""Tests for VaultClient (CAB-1291)"""
from unittest.mock import MagicMock, patch

import pytest
from hvac.exceptions import InvalidPath, VaultError

from src.services.vault_client import (
    VaultClient,
    VaultSealedException,
    get_vault_client,
    shutdown_vault_client,
)


# ── VaultSealedException ──


class TestVaultSealedException:
    def test_is_vault_error(self):
        err = VaultSealedException()
        assert isinstance(err, VaultError)
        assert "sealed" in str(err).lower()


# ── VaultClient init ──


class TestInit:
    def test_defaults(self):
        vc = VaultClient(vault_addr="https://vault.example.com")
        assert vc.vault_addr == "https://vault.example.com"
        assert vc.mount_point == "secret"
        assert vc._client is None
        assert vc._vault_token is None
        assert vc._kubernetes_role is None

    def test_with_all_params(self):
        vc = VaultClient(
            vault_addr="https://vault.dev",
            vault_token="tok",
            kubernetes_role="api",
            mount_point="kv",
        )
        assert vc._vault_token == "tok"
        assert vc._kubernetes_role == "api"
        assert vc.mount_point == "kv"


# ── _get_client ──


class TestGetClient:
    def test_returns_cached_if_authenticated(self):
        vc = VaultClient(vault_addr="https://vault.dev")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        vc._client = mock_client
        assert vc._get_client() is mock_client

    def test_token_auth(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="my-token")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        with patch("src.services.vault_client.hvac.Client", return_value=mock_client):
            client = vc._get_client()
        assert client.token == "my-token"

    def test_token_auth_fails(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="bad-token")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = False
        with patch("src.services.vault_client.hvac.Client", return_value=mock_client):
            with pytest.raises(VaultError, match="Failed to authenticate"):
                vc._get_client()

    def test_kubernetes_auth_success(self):
        vc = VaultClient(vault_addr="https://vault.dev", kubernetes_role="api")
        mock_client = MagicMock()

        with patch("src.services.vault_client.hvac.Client", return_value=mock_client), \
             patch("os.path.exists", return_value=True), \
             patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = MagicMock(return_value=MagicMock(read=MagicMock(return_value="jwt-token")))
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            client = vc._get_client()
        assert client is mock_client
        mock_client.auth.kubernetes.login.assert_called_once_with(role="api", jwt="jwt-token")

    def test_kubernetes_auth_fallback_to_token(self):
        vc = VaultClient(vault_addr="https://vault.dev", kubernetes_role="api", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True

        with patch("src.services.vault_client.hvac.Client", return_value=mock_client), \
             patch("os.path.exists", return_value=False):
            client = vc._get_client()
        assert client.token == "tok"

    def test_no_auth_method(self):
        vc = VaultClient(vault_addr="https://vault.dev")
        mock_client = MagicMock()
        with patch("src.services.vault_client.hvac.Client", return_value=mock_client):
            with pytest.raises(VaultError, match="Failed to authenticate"):
                vc._get_client()


# ── _ensure_unsealed ──


class TestEnsureUnsealed:
    def test_sealed_raises(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": True}
        vc._client = mock_client
        with pytest.raises(VaultSealedException):
            vc._ensure_unsealed()

    def test_unsealed_ok(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        vc._client = mock_client
        # Should not raise
        vc._ensure_unsealed()

    def test_health_check_error_is_warning(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.side_effect = Exception("network")
        vc._client = mock_client
        # Should not raise (just warns)
        vc._ensure_unsealed()


# ── store_credential ──


class TestStoreCredential:
    async def test_success(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        vc._client = mock_client

        path = await vc.store_credential("srv-1", {"api_key": "secret"})
        assert path == "secret/data/external-mcp-servers/srv-1"
        mock_client.secrets.kv.v2.create_or_update_secret.assert_called_once()

    async def test_vault_error(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        mock_client.secrets.kv.v2.create_or_update_secret.side_effect = VaultError("write failed")
        vc._client = mock_client

        with pytest.raises(VaultError, match="write failed"):
            await vc.store_credential("srv-1", {"api_key": "secret"})


# ── retrieve_credential ──


class TestRetrieveCredential:
    async def test_found(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        mock_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"api_key": "secret123"}}
        }
        vc._client = mock_client

        result = await vc.retrieve_credential("srv-1")
        assert result == {"api_key": "secret123"}

    async def test_not_found(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        mock_client.secrets.kv.v2.read_secret_version.side_effect = InvalidPath("not found")
        vc._client = mock_client

        result = await vc.retrieve_credential("srv-1")
        assert result is None

    async def test_vault_error(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        mock_client.secrets.kv.v2.read_secret_version.side_effect = VaultError("read error")
        vc._client = mock_client

        with pytest.raises(VaultError, match="read error"):
            await vc.retrieve_credential("srv-1")

    async def test_empty_response(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        mock_client.secrets.kv.v2.read_secret_version.return_value = None
        vc._client = mock_client

        result = await vc.retrieve_credential("srv-1")
        assert result is None


# ── delete_credential ──


class TestDeleteCredential:
    async def test_success(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        vc._client = mock_client

        result = await vc.delete_credential("srv-1")
        assert result is True
        mock_client.secrets.kv.v2.delete_metadata_and_all_versions.assert_called_once()

    async def test_not_found(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        mock_client.secrets.kv.v2.delete_metadata_and_all_versions.side_effect = InvalidPath("nope")
        vc._client = mock_client

        result = await vc.delete_credential("srv-1")
        assert result is False

    async def test_vault_error(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        mock_client.secrets.kv.v2.delete_metadata_and_all_versions.side_effect = VaultError("del fail")
        vc._client = mock_client

        with pytest.raises(VaultError, match="del fail"):
            await vc.delete_credential("srv-1")


# ── health_check ──


class TestHealthCheck:
    def test_healthy(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": False}
        vc._client = mock_client
        assert vc.health_check() is True

    def test_sealed(self):
        vc = VaultClient(vault_addr="https://vault.dev", vault_token="tok")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = True
        mock_client.sys.read_health_status.return_value = {"sealed": True}
        vc._client = mock_client
        assert vc.health_check() is False

    def test_exception(self):
        vc = VaultClient(vault_addr="https://vault.dev")
        mock_client = MagicMock()
        mock_client.is_authenticated.return_value = False
        vc._client = mock_client
        assert vc.health_check() is False


# ── Global helpers ──


class TestGlobalHelpers:
    def test_get_vault_client(self):
        with patch("src.services.vault_client._vault_client", None), \
             patch("src.services.vault_client.settings") as mock_settings:
            mock_settings.BASE_DOMAIN = "gostoa.dev"
            with patch.dict("os.environ", {"VAULT_TOKEN": "test-tok"}):
                client = get_vault_client()
        assert isinstance(client, VaultClient)

    async def test_shutdown(self):
        with patch("src.services.vault_client._vault_client", MagicMock()):
            await shutdown_vault_client()
        # After shutdown, global should be None
        # (we can't check directly due to module-level global, but no error = success)
