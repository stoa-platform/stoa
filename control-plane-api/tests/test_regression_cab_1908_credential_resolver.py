"""Regression tests for CAB-1908 — credential resolver silent empty fallback.

When auth_config contains only vault_path and Vault is unavailable,
the resolver must raise ValueError instead of returning an empty dict
(which caused silent HTTP 401 on all third-party gateway adapters).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.credential_resolver import (
    create_adapter_with_credentials,
    resolve_gateway_auth_config,
)


class TestRegressionCAB1908:
    """CAB-1908: vault_path-only config must not silently return empty credentials."""

    async def test_vault_only_raises_on_vault_disabled(self):
        """vault_path-only config with Vault returning None must raise ValueError."""
        auth = {"vault_path": "gateways/kong-prod"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(return_value=None)

        with (
            patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault),
            pytest.raises(ValueError, match="no fallback credentials"),
        ):
            await resolve_gateway_auth_config(auth)

    async def test_vault_only_raises_on_vault_exception(self):
        """vault_path-only config with Vault exception must raise ValueError."""
        auth = {"vault_path": "gateways/kong-prod"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(side_effect=Exception("connection refused"))

        with (
            patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault),
            pytest.raises(ValueError, match="no fallback credentials"),
        ):
            await resolve_gateway_auth_config(auth)

    async def test_hybrid_config_falls_back_to_direct_creds(self):
        """vault_path + direct creds with Vault unavailable must use fallback."""
        auth = {"vault_path": "gateways/kong-prod", "api_key": "direct-fallback-key"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(return_value=None)

        with patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault):
            result = await resolve_gateway_auth_config(auth)

        assert result == {"api_key": "direct-fallback-key"}
        assert "vault_path" not in result

    async def test_create_adapter_propagates_error(self):
        """create_adapter_with_credentials raises ValueError on vault-only failure."""
        auth = {"vault_path": "gateways/kong-prod"}
        mock_vault = MagicMock()
        mock_vault.read_secret = AsyncMock(return_value=None)

        with (
            patch("src.services.credential_resolver.get_vault_client", return_value=mock_vault),
            pytest.raises(ValueError, match="no fallback credentials"),
        ):
            await create_adapter_with_credentials("kong", "http://kong:8001", auth)
