"""Tests for CredentialMappingRepository — Wave 2

Covers: list_by_tenant (pagination, filters), update, delete,
        list_active_for_sync (decryption), encrypt_credential.

The router tests (test_credential_mappings_router.py) cover create, get_by_id,
get_by_consumer_and_api via integration. This file tests the repository directly
to cover the 45% gap (list_by_tenant, list_active_for_sync, update, delete).
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _mock_mapping(**overrides):
    """Create a mock CredentialMapping object."""
    m = MagicMock()
    defaults = {
        "id": uuid4(),
        "consumer_id": uuid4(),
        "api_id": "weather-api",
        "tenant_id": "acme",
        "auth_type": MagicMock(value="api_key"),
        "header_name": "X-Api-Key",
        "encrypted_value": b"encrypted-data",
        "is_active": True,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


class TestListByTenant:
    """Tests for list_by_tenant with filtering and pagination."""

    @pytest.mark.asyncio
    async def test_list_returns_items_and_total(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        session = AsyncMock()
        mappings = [_mock_mapping(), _mock_mapping()]

        count_result = MagicMock()
        count_result.scalar_one.return_value = 2

        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = mappings
        list_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        repo = CredentialMappingRepository(session)
        items, total = await repo.list_by_tenant("acme")

        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_empty_result(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        list_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        repo = CredentialMappingRepository(session)
        items, total = await repo.list_by_tenant("acme")

        assert total == 0
        assert items == []

    @pytest.mark.asyncio
    async def test_list_with_consumer_filter(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        session = AsyncMock()
        consumer_id = uuid4()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [_mock_mapping(consumer_id=consumer_id)]
        list_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        repo = CredentialMappingRepository(session)
        items, total = await repo.list_by_tenant("acme", consumer_id=consumer_id)

        assert total == 1
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_list_with_api_filter(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        session = AsyncMock()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        list_result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [_mock_mapping(api_id="payments-api")]
        list_result.scalars.return_value = scalars_mock

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        repo = CredentialMappingRepository(session)
        _items, total = await repo.list_by_tenant("acme", api_id="payments-api")

        assert total == 1


class TestUpdate:
    """Tests for update method."""

    @pytest.mark.asyncio
    async def test_update_sets_updated_at(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        session = AsyncMock()
        mapping = _mock_mapping()

        repo = CredentialMappingRepository(session)
        await repo.update(mapping)

        assert mapping.updated_at is not None
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(mapping)


class TestDelete:
    """Tests for delete method."""

    @pytest.mark.asyncio
    async def test_delete_calls_session_delete(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        session = AsyncMock()
        mapping = _mock_mapping()

        repo = CredentialMappingRepository(session)
        await repo.delete(mapping)

        session.delete.assert_awaited_once_with(mapping)
        session.flush.assert_awaited_once()


class TestListActiveForSync:
    """Tests for list_active_for_sync with decryption."""

    @pytest.mark.asyncio
    async def test_returns_decrypted_items(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        session = AsyncMock()
        mapping = _mock_mapping()

        result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [mapping]
        result.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result)

        with patch(
            "src.repositories.credential_mapping.decrypt_auth_config",
            return_value={"value": "decrypted-secret"},
        ):
            repo = CredentialMappingRepository(session)
            items = await repo.list_active_for_sync("acme")

        assert len(items) == 1
        assert items[0]["header_value"] == "decrypted-secret"
        assert items[0]["auth_type"] == "api_key"
        assert items[0]["api_id"] == "weather-api"

    @pytest.mark.asyncio
    async def test_skips_decryption_failure(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        session = AsyncMock()
        good_mapping = _mock_mapping(api_id="good-api")
        bad_mapping = _mock_mapping(api_id="bad-api")

        result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [bad_mapping, good_mapping]
        result.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result)

        call_count = 0

        def mock_decrypt(value):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Decryption failed")
            return {"value": "good-secret"}

        with patch(
            "src.repositories.credential_mapping.decrypt_auth_config",
            side_effect=mock_decrypt,
        ):
            repo = CredentialMappingRepository(session)
            items = await repo.list_active_for_sync("acme")

        assert len(items) == 1
        assert items[0]["api_id"] == "good-api"

    @pytest.mark.asyncio
    async def test_empty_when_no_active_mappings(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        session = AsyncMock()

        result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result.scalars.return_value = scalars_mock
        session.execute = AsyncMock(return_value=result)

        repo = CredentialMappingRepository(session)
        items = await repo.list_active_for_sync("acme")

        assert items == []


class TestEncryptCredential:
    """Tests for encrypt_credential static method."""

    def test_encrypt_calls_service(self):
        from src.repositories.credential_mapping import CredentialMappingRepository

        with patch(
            "src.repositories.credential_mapping.encrypt_auth_config",
            return_value="encrypted-output",
        ) as mock_encrypt:
            result = CredentialMappingRepository.encrypt_credential("my-secret")

        assert result == "encrypted-output"
        mock_encrypt.assert_called_once_with({"value": "my-secret"})
