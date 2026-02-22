"""Tests for BackendApiRepository and SaasApiKeyRepository (CAB-1388)."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.backend_api import BackendApi, BackendApiAuthType, BackendApiStatus
from src.models.saas_api_key import SaasApiKey, SaasApiKeyStatus
from src.repositories.backend_api import BackendApiRepository, SaasApiKeyRepository


def _mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.delete = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _make_backend_api(tenant_id: str = "acme", name: str = "petstore") -> BackendApi:
    api = MagicMock(spec=BackendApi)
    api.id = uuid4()
    api.tenant_id = tenant_id
    api.name = name
    api.status = BackendApiStatus.DRAFT
    api.created_at = datetime.utcnow()
    return api


def _make_saas_key(tenant_id: str = "acme", name: str = "my-key") -> SaasApiKey:
    key = MagicMock(spec=SaasApiKey)
    key.id = uuid4()
    key.tenant_id = tenant_id
    key.name = name
    key.status = SaasApiKeyStatus.ACTIVE
    key.created_at = datetime.utcnow()
    return key


# ── BackendApiRepository ──


class TestBackendApiRepositoryCreate:
    async def test_create_adds_and_flushes(self):
        session = _mock_session()
        repo = BackendApiRepository(session)
        api = _make_backend_api()

        session.refresh = AsyncMock(return_value=None)
        result = await repo.create(api)

        session.add.assert_called_once_with(api)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(api)
        assert result is api


class TestBackendApiRepositoryGetById:
    async def test_get_by_id_returns_result(self):
        session = _mock_session()
        repo = BackendApiRepository(session)
        api = _make_backend_api()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = api
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_id(api.id)
        assert result is api
        session.execute.assert_awaited_once()

    async def test_get_by_id_returns_none_when_not_found(self):
        session = _mock_session()
        repo = BackendApiRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_id(uuid4())
        assert result is None


class TestBackendApiRepositoryGetByTenantAndName:
    async def test_returns_api_when_found(self):
        session = _mock_session()
        repo = BackendApiRepository(session)
        api = _make_backend_api()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = api
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_tenant_and_name("acme", "petstore")
        assert result is api

    async def test_returns_none_when_not_found(self):
        session = _mock_session()
        repo = BackendApiRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_tenant_and_name("acme", "missing")
        assert result is None


class TestBackendApiRepositoryListByTenant:
    async def test_list_returns_items_and_total(self):
        session = _mock_session()
        repo = BackendApiRepository(session)
        api = _make_backend_api()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [api]

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await repo.list_by_tenant("acme")
        assert total == 1
        assert len(items) == 1
        assert items[0] is api

    async def test_list_with_status_filter(self):
        session = _mock_session()
        repo = BackendApiRepository(session)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await repo.list_by_tenant("acme", status=BackendApiStatus.DRAFT)
        assert total == 0
        assert items == []

    async def test_list_with_pagination(self):
        session = _mock_session()
        repo = BackendApiRepository(session)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 5

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await repo.list_by_tenant("acme", page=2, page_size=2)
        assert total == 5


class TestBackendApiRepositoryUpdate:
    async def test_update_flushes_and_refreshes(self):
        session = _mock_session()
        repo = BackendApiRepository(session)
        api = _make_backend_api()

        result = await repo.update(api)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(api)
        assert result is api


class TestBackendApiRepositoryDelete:
    async def test_delete_calls_delete_and_flush(self):
        session = _mock_session()
        repo = BackendApiRepository(session)
        api = _make_backend_api()

        await repo.delete(api)
        session.delete.assert_called_once_with(api)
        session.flush.assert_awaited_once()


class TestBackendApiRepositoryDeleteAllByTenant:
    async def test_deletes_all_and_returns_count(self):
        session = _mock_session()
        repo = BackendApiRepository(session)
        apis = [_make_backend_api(), _make_backend_api(name="other")]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = apis
        session.execute = AsyncMock(return_value=mock_result)

        count = await repo.delete_all_by_tenant("acme")
        assert count == 2
        assert session.delete.call_count == 2
        session.flush.assert_awaited_once()

    async def test_delete_all_empty_returns_zero(self):
        session = _mock_session()
        repo = BackendApiRepository(session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        count = await repo.delete_all_by_tenant("empty-tenant")
        assert count == 0
        session.flush.assert_not_awaited()


# ── SaasApiKeyRepository ──


class TestSaasApiKeyRepositoryCreate:
    async def test_create_adds_and_flushes(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)
        key = _make_saas_key()

        result = await repo.create(key)
        session.add.assert_called_once_with(key)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(key)
        assert result is key


class TestSaasApiKeyRepositoryGetById:
    async def test_get_by_id_found(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)
        key = _make_saas_key()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = key
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_id(key.id)
        assert result is key

    async def test_get_by_id_not_found(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_id(uuid4())
        assert result is None


class TestSaasApiKeyRepositoryGetByHash:
    async def test_get_by_hash_found(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)
        key = _make_saas_key()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = key
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_hash("abc123hash")
        assert result is key

    async def test_get_by_hash_not_found(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_hash("missing")
        assert result is None


class TestSaasApiKeyRepositoryListByTenant:
    async def test_list_returns_keys_and_total(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)
        key = _make_saas_key()

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [key]

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await repo.list_by_tenant("acme")
        assert total == 1
        assert items[0] is key

    async def test_list_with_status_filter(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 0

        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        session.execute = AsyncMock(side_effect=[count_result, list_result])

        items, total = await repo.list_by_tenant("acme", status=SaasApiKeyStatus.ACTIVE)
        assert total == 0


class TestSaasApiKeyRepositoryUpdate:
    async def test_update_flushes_and_refreshes(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)
        key = _make_saas_key()

        result = await repo.update(key)
        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once_with(key)
        assert result is key


class TestSaasApiKeyRepositoryDeleteAllByTenant:
    async def test_deletes_all_and_returns_count(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)
        keys = [_make_saas_key(), _make_saas_key(name="key2")]

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = keys
        session.execute = AsyncMock(return_value=mock_result)

        count = await repo.delete_all_by_tenant("acme")
        assert count == 2
        assert session.delete.call_count == 2
        session.flush.assert_awaited_once()

    async def test_delete_all_empty_returns_zero(self):
        session = _mock_session()
        repo = SaasApiKeyRepository(session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=mock_result)

        count = await repo.delete_all_by_tenant("empty")
        assert count == 0
        session.flush.assert_not_awaited()
