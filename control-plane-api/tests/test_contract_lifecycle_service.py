"""Tests for contract lifecycle service (CAB-1335 / CAB-1558)."""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.contract_lifecycle_service import (
    deprecate_contract,
    get_active_version,
    get_sunset_candidates,
    list_versions,
    reactivate_contract,
)


def _make_contract(**overrides) -> MagicMock:
    """Build a mock Contract with sensible defaults."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "acme",
        "name": "pet-api",
        "display_name": "Pet API",
        "version": "1.0.0",
        "status": "published",
        "deprecated_at": None,
        "sunset_at": None,
        "replacement_contract_id": None,
        "deprecation_reason": None,
        "grace_period_days": None,
        "is_sunset": False,
        "created_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _mock_db() -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    return db


# ── deprecate_contract ──


class TestDeprecateContract:
    @pytest.mark.asyncio
    async def test_already_deprecated_raises(self):
        contract = _make_contract(status="deprecated")
        db = _mock_db()
        with pytest.raises(ValueError, match="already deprecated"):
            await deprecate_contract(db, contract, reason="obsolete")

    @pytest.mark.asyncio
    async def test_draft_raises(self):
        contract = _make_contract(status="draft")
        db = _mock_db()
        with pytest.raises(ValueError, match="Cannot deprecate a draft"):
            await deprecate_contract(db, contract, reason="unused")

    @pytest.mark.asyncio
    async def test_replacement_not_found_raises(self):
        contract = _make_contract(status="published")
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        with pytest.raises(ValueError, match="not found"):
            await deprecate_contract(
                db,
                contract,
                reason="replaced",
                replacement_contract_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_replacement_different_tenant_raises(self):
        contract = _make_contract(status="published", tenant_id="acme")
        replacement = _make_contract(status="published", tenant_id="other-tenant")
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = replacement
        db.execute.return_value = result_mock

        with pytest.raises(ValueError, match="same tenant"):
            await deprecate_contract(
                db,
                contract,
                reason="replaced",
                replacement_contract_id=replacement.id,
            )

    @pytest.mark.asyncio
    async def test_replacement_deprecated_raises(self):
        contract = _make_contract(status="published", tenant_id="acme")
        replacement = _make_contract(status="deprecated", tenant_id="acme")
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = replacement
        db.execute.return_value = result_mock

        with pytest.raises(ValueError, match="itself deprecated"):
            await deprecate_contract(
                db,
                contract,
                reason="replaced",
                replacement_contract_id=replacement.id,
            )

    @pytest.mark.asyncio
    async def test_success_sets_fields(self):
        contract = _make_contract(status="published")
        db = _mock_db()

        result = await deprecate_contract(db, contract, reason="end of life")

        assert result.status == "deprecated"
        assert result.deprecation_reason == "end of life"
        assert result.deprecated_at is not None
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_grace_period_computes_sunset(self):
        contract = _make_contract(status="published")
        db = _mock_db()

        result = await deprecate_contract(db, contract, reason="eol", grace_period_days=30)

        assert result.sunset_at is not None
        assert result.grace_period_days == 30

    @pytest.mark.asyncio
    async def test_explicit_sunset_at(self):
        contract = _make_contract(status="published")
        db = _mock_db()
        sunset = datetime.utcnow() + timedelta(days=60)

        result = await deprecate_contract(db, contract, reason="eol", sunset_at=sunset)

        assert result.sunset_at == sunset

    @pytest.mark.asyncio
    async def test_replacement_success(self):
        contract = _make_contract(status="published", tenant_id="acme")
        replacement = _make_contract(status="published", tenant_id="acme")
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = replacement
        db.execute.return_value = result_mock

        result = await deprecate_contract(
            db,
            contract,
            reason="replaced by v2",
            replacement_contract_id=replacement.id,
        )

        assert result.replacement_contract_id == str(replacement.id)
        assert result.status == "deprecated"


# ── reactivate_contract ──


class TestReactivateContract:
    @pytest.mark.asyncio
    async def test_not_deprecated_raises(self):
        contract = _make_contract(status="published")
        db = _mock_db()
        with pytest.raises(ValueError, match="Only deprecated"):
            await reactivate_contract(db, contract)

    @pytest.mark.asyncio
    async def test_sunset_passed_raises(self):
        contract = _make_contract(status="deprecated", is_sunset=True)
        db = _mock_db()
        with pytest.raises(ValueError, match="sunset date has passed"):
            await reactivate_contract(db, contract)

    @pytest.mark.asyncio
    async def test_success_resets_fields(self):
        contract = _make_contract(
            status="deprecated",
            is_sunset=False,
            deprecated_at=datetime.utcnow(),
            sunset_at=datetime.utcnow() + timedelta(days=30),
            replacement_contract_id=str(uuid.uuid4()),
            deprecation_reason="old",
            grace_period_days=30,
        )
        db = _mock_db()

        result = await reactivate_contract(db, contract)

        assert result.status == "published"
        assert result.deprecated_at is None
        assert result.sunset_at is None
        assert result.replacement_contract_id is None
        assert result.deprecation_reason is None
        assert result.grace_period_days is None
        db.flush.assert_awaited_once()


# ── list_versions ──


class TestListVersions:
    @pytest.mark.asyncio
    async def test_returns_versions(self):
        db = _mock_db()
        v1 = _make_contract(version="1.0.0")
        v2 = _make_contract(version="2.0.0")
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [v2, v1]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        versions = await list_versions(db, "acme", "pet-api")

        assert len(versions) == 2
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        db = _mock_db()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        versions = await list_versions(db, "acme", "unknown-api")

        assert versions == []


# ── get_active_version ──


class TestGetActiveVersion:
    @pytest.mark.asyncio
    async def test_returns_latest_published(self):
        db = _mock_db()
        contract = _make_contract(status="published")
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = contract
        db.execute.return_value = result_mock

        active = await get_active_version(db, "acme", "pet-api")

        assert active is not None
        assert active.status == "published"

    @pytest.mark.asyncio
    async def test_returns_none_when_all_deprecated(self):
        db = _mock_db()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db.execute.return_value = result_mock

        active = await get_active_version(db, "acme", "pet-api")

        assert active is None


# ── get_sunset_candidates ──


class TestGetSunsetCandidates:
    @pytest.mark.asyncio
    async def test_returns_candidates(self):
        db = _mock_db()
        c1 = _make_contract(status="deprecated", sunset_at=datetime.utcnow() - timedelta(days=1))
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = [c1]
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        candidates = await get_sunset_candidates(db)

        assert len(candidates) == 1
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_custom_before_date(self):
        db = _mock_db()
        scalars_mock = MagicMock()
        scalars_mock.all.return_value = []
        result_mock = MagicMock()
        result_mock.scalars.return_value = scalars_mock
        db.execute.return_value = result_mock

        candidates = await get_sunset_candidates(db, before=datetime.utcnow() + timedelta(days=90))

        assert candidates == []
        db.execute.assert_awaited_once()
