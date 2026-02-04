"""Tests for Vault client sealed-state detection (CAB-1042)."""

from unittest.mock import MagicMock, patch

import pytest
from hvac.exceptions import VaultError

from src.services.vault_client import VaultClient, VaultSealedException


@pytest.fixture
def vault_client():
    """Create a VaultClient with a mock token."""
    return VaultClient(
        vault_addr="https://vault.test.local",
        vault_token="test-token",
        mount_point="secret",
    )


@pytest.fixture
def mock_hvac_client():
    """Create a mock hvac.Client."""
    client = MagicMock()
    client.is_authenticated.return_value = True
    return client


class TestVaultSealedException:
    def test_inherits_from_vault_error(self):
        exc = VaultSealedException()
        assert isinstance(exc, VaultError)

    def test_message(self):
        exc = VaultSealedException()
        assert "sealed" in str(exc).lower()


class TestEnsureUnsealed:
    def test_raises_when_sealed(self, vault_client, mock_hvac_client):
        mock_hvac_client.sys.read_health_status.return_value = {"sealed": True}
        vault_client._client = mock_hvac_client

        with pytest.raises(VaultSealedException):
            vault_client._ensure_unsealed()

    def test_passes_when_unsealed(self, vault_client, mock_hvac_client):
        mock_hvac_client.sys.read_health_status.return_value = {"sealed": False}
        vault_client._client = mock_hvac_client

        # Should not raise
        vault_client._ensure_unsealed()

    def test_tolerates_health_check_failure(self, vault_client, mock_hvac_client):
        mock_hvac_client.sys.read_health_status.side_effect = Exception("connection refused")
        vault_client._client = mock_hvac_client

        # Should not raise — tolerant of health check errors
        vault_client._ensure_unsealed()


class TestStoreApiKeySealed:
    @pytest.mark.asyncio
    async def test_store_raises_when_sealed(self, vault_client, mock_hvac_client):
        mock_hvac_client.sys.read_health_status.return_value = {"sealed": True}
        vault_client._client = mock_hvac_client

        with pytest.raises(VaultSealedException):
            await vault_client.store_api_key("sub-123", "key-abc")

    @pytest.mark.asyncio
    async def test_store_works_when_unsealed(self, vault_client, mock_hvac_client):
        mock_hvac_client.sys.read_health_status.return_value = {"sealed": False}
        vault_client._client = mock_hvac_client

        result = await vault_client.store_api_key("sub-123", "key-abc")
        assert "subscriptions/sub-123" in result


class TestRetrieveApiKeySealed:
    @pytest.mark.asyncio
    async def test_retrieve_raises_when_sealed(self, vault_client, mock_hvac_client):
        mock_hvac_client.sys.read_health_status.return_value = {"sealed": True}
        vault_client._client = mock_hvac_client

        with pytest.raises(VaultSealedException):
            await vault_client.retrieve_api_key("sub-123")


class TestDeleteApiKeySealed:
    @pytest.mark.asyncio
    async def test_delete_raises_when_sealed(self, vault_client, mock_hvac_client):
        mock_hvac_client.sys.read_health_status.return_value = {"sealed": True}
        vault_client._client = mock_hvac_client

        with pytest.raises(VaultSealedException):
            await vault_client.delete_api_key("sub-123")


class TestHealthCheck:
    def test_returns_false_when_sealed(self, vault_client, mock_hvac_client):
        mock_hvac_client.sys.read_health_status.return_value = {"sealed": True}
        vault_client._client = mock_hvac_client

        assert vault_client.health_check() is False

    def test_returns_true_when_unsealed(self, vault_client, mock_hvac_client):
        mock_hvac_client.sys.read_health_status.return_value = {"sealed": False}
        vault_client._client = mock_hvac_client

        assert vault_client.health_check() is True
