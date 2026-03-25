"""Tests for credential resolver — Vault-backed gateway auth config resolution."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.credential_resolver import (
    create_adapter_with_credentials,
    resolve_gateway_auth_config,
)


# ── resolve_gateway_auth_config ──


class TestResolveGatewayAuthConfig:
    async def test_passthrough_no_vault_path(self):
        """Auth config without vault_path is returned unchanged."""
        auth = {"api_key": "my-key", "type": "api_key"}
        result = await resolve_gateway_auth_config(auth)
        assert result == auth

    async def test_passthrough_none(self):
        """None auth_config returns empty dict."""
        result = await resolve_gateway_auth_config(None)
        assert result == {}

    async def test_passthrough_empty(self):
        """Empty dict returns empty dict."""
        result = await resolve_gateway_auth_config({})
        assert result == {}

    async def test_resolve_from_vault(self):
        """vault_path present: fetches from Vault and merges."""
        auth = {"vault_path": "gateways/kong-dev", "type": "api_key"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(return_value={"api_key": "vault-secret"})

        with patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault):
            result = await resolve_gateway_auth_config(auth)

        assert result == {"type": "api_key", "api_key": "vault-secret"}
        mock_vault.read_secret.assert_awaited_once_with("gateways/kong-dev")

    async def test_vault_overrides_db_values(self):
        """Vault secrets override existing keys in auth_config."""
        auth = {"vault_path": "gateways/kong-dev", "api_key": "old-key"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(return_value={"api_key": "new-vault-key"})

        with patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault):
            result = await resolve_gateway_auth_config(auth)

        assert result["api_key"] == "new-vault-key"

    async def test_vault_path_removed(self):
        """Resolved dict has no vault_path key."""
        auth = {"vault_path": "gateways/kong-dev"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(return_value={"api_key": "secret"})

        with patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault):
            result = await resolve_gateway_auth_config(auth)

        assert "vault_path" not in result
        assert result["api_key"] == "secret"

    async def test_fallback_vault_disabled(self):
        """When Vault returns None (disabled), returns auth_config minus vault_path."""
        auth = {"vault_path": "gateways/kong-dev", "type": "api_key"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(return_value=None)

        with patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault):
            result = await resolve_gateway_auth_config(auth)

        assert result == {"type": "api_key"}
        assert "vault_path" not in result

    async def test_fallback_vault_unavailable(self):
        """On Vault exception, returns auth_config minus vault_path."""
        auth = {"vault_path": "gateways/kong-dev", "type": "api_key"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(side_effect=Exception("connection refused"))

        with patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault):
            result = await resolve_gateway_auth_config(auth)

        assert result == {"type": "api_key"}
        assert "vault_path" not in result


# ── create_adapter_with_credentials ──


class TestCreateAdapterWithCredentials:
    async def test_creates_adapter_with_resolved_config(self):
        """End-to-end: resolves Vault credentials and creates adapter."""
        auth = {"vault_path": "gateways/kong-dev"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(return_value={"api_key": "kong-token"})

        mock_adapter = MagicMock()
        with patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault), \
             patch("src.services.credential_resolver.AdapterRegistry") as mock_registry:
            mock_registry.create.return_value = mock_adapter

            result = await create_adapter_with_credentials(
                "kong", "http://kong:8001", auth,
            )

        assert result is mock_adapter
        mock_registry.create.assert_called_once_with(
            "kong",
            config={"base_url": "http://kong:8001", "auth_config": {"api_key": "kong-token"}},
        )

    async def test_passthrough_without_vault(self):
        """Without vault_path, auth_config passes through unchanged."""
        auth = {"api_key": "direct-key"}
        mock_adapter = MagicMock()

        with patch("src.services.credential_resolver.AdapterRegistry") as mock_registry:
            mock_registry.create.return_value = mock_adapter

            result = await create_adapter_with_credentials(
                "kong", "http://kong:8001", auth,
            )

        assert result is mock_adapter
        mock_registry.create.assert_called_once_with(
            "kong",
            config={"base_url": "http://kong:8001", "auth_config": {"api_key": "direct-key"}},
        )
