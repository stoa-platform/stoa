"""Tests for GatewayPolicyRepository and GatewayPolicyBindingRepository (CAB-1388)."""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.gateway_policy import GatewayPolicy, GatewayPolicyBinding, PolicyType
from src.repositories.gateway_policy import GatewayPolicyBindingRepository, GatewayPolicyRepository


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_policy(**kwargs):
    p = MagicMock(spec=GatewayPolicy)
    p.id = kwargs.get("id", uuid4())
    p.name = kwargs.get("name", "rate-limit-default")
    p.policy_type = kwargs.get("policy_type", PolicyType.RATE_LIMIT)
    p.tenant_id = kwargs.get("tenant_id", None)
    p.enabled = kwargs.get("enabled", True)
    p.priority = kwargs.get("priority", 10)
    return p


def _mock_binding(**kwargs):
    b = MagicMock(spec=GatewayPolicyBinding)
    b.id = kwargs.get("id", uuid4())
    b.policy_id = kwargs.get("policy_id", uuid4())
    b.tenant_id = kwargs.get("tenant_id", "acme")
    b.api_catalog_id = kwargs.get("api_catalog_id", None)
    b.gateway_instance_id = kwargs.get("gateway_instance_id", None)
    b.enabled = kwargs.get("enabled", True)
    return b


# ── GatewayPolicyRepository ──


class TestPolicyCreate:
    async def test_create(self):
        db = _mock_db()
        policy = _mock_policy()
        repo = GatewayPolicyRepository(db)
        result = await repo.create(policy)
        db.add.assert_called_once_with(policy)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(policy)
        assert result is policy


class TestPolicyGetById:
    async def test_found(self):
        db = _mock_db()
        policy = _mock_policy()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = policy
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyRepository(db)
        result = await repo.get_by_id(policy.id)
        assert result is policy

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


class TestPolicyListAll:
    async def test_no_filters(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_policy(), _mock_policy()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyRepository(db)
        items = await repo.list_all()
        assert len(items) == 2

    async def test_with_tenant_filter(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_policy(tenant_id="acme")]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyRepository(db)
        items = await repo.list_all(tenant_id="acme")
        assert len(items) == 1

    async def test_with_policy_type_filter(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_policy()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyRepository(db)
        items = await repo.list_all(policy_type=PolicyType.RATE_LIMIT)
        assert len(items) == 1

    async def test_empty(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyRepository(db)
        items = await repo.list_all()
        assert items == []


class TestPolicyUpdate:
    async def test_update(self):
        db = _mock_db()
        policy = _mock_policy()
        repo = GatewayPolicyRepository(db)
        result = await repo.update(policy)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(policy)
        assert result is policy


class TestPolicyDelete:
    async def test_delete(self):
        db = _mock_db()
        policy = _mock_policy()
        repo = GatewayPolicyRepository(db)
        await repo.delete(policy)
        db.delete.assert_called_once_with(policy)
        db.flush.assert_called_once()


class TestGetPoliciesForDeployment:
    async def test_returns_matching_policies(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_policy(), _mock_policy()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyRepository(db)
        items = await repo.get_policies_for_deployment(
            api_catalog_id=uuid4(),
            gateway_instance_id=uuid4(),
            tenant_id="acme",
        )
        assert len(items) == 2

    async def test_returns_empty_when_no_match(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyRepository(db)
        items = await repo.get_policies_for_deployment(
            api_catalog_id=uuid4(),
            gateway_instance_id=uuid4(),
            tenant_id="acme",
        )
        assert items == []


# ── GatewayPolicyBindingRepository ──


class TestBindingCreate:
    async def test_create(self):
        db = _mock_db()
        binding = _mock_binding()
        repo = GatewayPolicyBindingRepository(db)
        result = await repo.create(binding)
        db.add.assert_called_once_with(binding)
        db.flush.assert_called_once()
        db.refresh.assert_called_once_with(binding)
        assert result is binding


class TestBindingGetById:
    async def test_found(self):
        db = _mock_db()
        binding = _mock_binding()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = binding
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyBindingRepository(db)
        result = await repo.get_by_id(binding.id)
        assert result is binding

    async def test_not_found(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyBindingRepository(db)
        result = await repo.get_by_id(uuid4())
        assert result is None


class TestBindingListByPolicy:
    async def test_returns_list(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [_mock_binding(), _mock_binding()]
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyBindingRepository(db)
        items = await repo.list_by_policy(uuid4())
        assert len(items) == 2

    async def test_empty(self):
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)
        repo = GatewayPolicyBindingRepository(db)
        items = await repo.list_by_policy(uuid4())
        assert items == []


class TestBindingDelete:
    async def test_delete(self):
        db = _mock_db()
        binding = _mock_binding()
        repo = GatewayPolicyBindingRepository(db)
        await repo.delete(binding)
        db.delete.assert_called_once_with(binding)
        db.flush.assert_called_once()
