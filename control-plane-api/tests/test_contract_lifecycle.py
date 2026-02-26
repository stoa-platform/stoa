"""Tests for Contract Lifecycle Management — deprecation and versioning (CAB-1335)."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.contract import Contract
from src.schemas.contract import (
    ContractDeprecationInfo,
    ContractVersionsResponse,
    ContractVersionSummary,
    DeprecateContractRequest,
)
from src.services.contract_lifecycle_service import (
    deprecate_contract,
    get_active_version,
    get_sunset_candidates,
    list_versions,
    reactivate_contract,
)

# =============================================================================
# Fixtures
# =============================================================================


def _make_contract(
    tenant_id: str = "test-tenant",
    name: str = "payment-api",
    version: str = "1.0.0",
    status: str = "published",
    **kwargs,
) -> Contract:
    """Create a Contract model instance for testing."""
    contract = Contract(
        id=kwargs.pop("id", uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        version=version,
        status=status,
        display_name=kwargs.pop("display_name", None),
        description=kwargs.pop("description", None),
        created_at=kwargs.pop("created_at", datetime.utcnow()),
        updated_at=kwargs.pop("updated_at", datetime.utcnow()),
        **kwargs,
    )
    return contract


def _mock_db() -> AsyncMock:
    """Create a mock async database session."""
    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    return db


# =============================================================================
# Contract Model Properties
# =============================================================================


class TestContractModelProperties:
    """Test Contract model deprecation properties."""

    def test_is_deprecated_true(self) -> None:
        c = _make_contract(status="deprecated")
        assert c.is_deprecated is True

    def test_is_deprecated_false_published(self) -> None:
        c = _make_contract(status="published")
        assert c.is_deprecated is False

    def test_is_deprecated_false_draft(self) -> None:
        c = _make_contract(status="draft")
        assert c.is_deprecated is False

    def test_is_sunset_no_date(self) -> None:
        c = _make_contract(status="deprecated")
        assert c.is_sunset is False

    def test_is_sunset_future_date(self) -> None:
        c = _make_contract(status="deprecated")
        c.sunset_at = datetime.utcnow() + timedelta(days=30)
        assert c.is_sunset is False

    def test_is_sunset_past_date(self) -> None:
        c = _make_contract(status="deprecated")
        c.sunset_at = datetime.utcnow() - timedelta(days=1)
        assert c.is_sunset is True


# =============================================================================
# Deprecation Service
# =============================================================================


class TestDeprecateContract:
    """Test deprecate_contract service function."""

    @pytest.mark.asyncio
    async def test_deprecate_published_contract(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="published")
        sunset = datetime.utcnow() + timedelta(days=90)

        result = await deprecate_contract(
            db=db,
            contract=contract,
            reason="Replaced by v2",
            sunset_at=sunset,
        )

        assert result.status == "deprecated"
        assert result.deprecated_at is not None
        assert result.sunset_at == sunset
        assert result.deprecation_reason == "Replaced by v2"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deprecate_with_grace_period(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="published")

        before = datetime.utcnow()
        result = await deprecate_contract(
            db=db,
            contract=contract,
            reason="EOL",
            grace_period_days=60,
        )

        assert result.grace_period_days == 60
        assert result.sunset_at is not None
        # sunset_at should be ~60 days from now
        delta = result.sunset_at - before
        assert 59 <= delta.days <= 61

    @pytest.mark.asyncio
    async def test_deprecate_already_deprecated(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="deprecated")

        with pytest.raises(ValueError, match="already deprecated"):
            await deprecate_contract(db=db, contract=contract, reason="Again")

    @pytest.mark.asyncio
    async def test_deprecate_draft_contract(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="draft")

        with pytest.raises(ValueError, match="draft contract"):
            await deprecate_contract(db=db, contract=contract, reason="Not ready")

    @pytest.mark.asyncio
    async def test_deprecate_with_replacement(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="published")
        replacement = _make_contract(
            status="published", version="2.0.0", tenant_id="test-tenant"
        )

        # Mock the replacement lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = replacement
        db.execute = AsyncMock(return_value=mock_result)

        result = await deprecate_contract(
            db=db,
            contract=contract,
            reason="Replaced by v2",
            replacement_contract_id=replacement.id,
        )

        assert result.replacement_contract_id == str(replacement.id)

    @pytest.mark.asyncio
    async def test_deprecate_replacement_not_found(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="published")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="not found"):
            await deprecate_contract(
                db=db,
                contract=contract,
                reason="test",
                replacement_contract_id=uuid.uuid4(),
            )

    @pytest.mark.asyncio
    async def test_deprecate_replacement_wrong_tenant(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="published", tenant_id="tenant-a")
        replacement = _make_contract(status="published", tenant_id="tenant-b")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = replacement
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="same tenant"):
            await deprecate_contract(
                db=db,
                contract=contract,
                reason="test",
                replacement_contract_id=replacement.id,
            )

    @pytest.mark.asyncio
    async def test_deprecate_replacement_itself_deprecated(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="published")
        replacement = _make_contract(status="deprecated", tenant_id="test-tenant")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = replacement
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="itself deprecated"):
            await deprecate_contract(
                db=db,
                contract=contract,
                reason="test",
                replacement_contract_id=replacement.id,
            )

    @pytest.mark.asyncio
    async def test_deprecate_explicit_sunset_overrides_grace_period(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="published")
        explicit_sunset = datetime(2026, 12, 31, tzinfo=UTC)

        result = await deprecate_contract(
            db=db,
            contract=contract,
            reason="Explicit sunset",
            sunset_at=explicit_sunset,
            grace_period_days=30,
        )

        # Explicit sunset wins over grace_period computation
        assert result.sunset_at == explicit_sunset
        assert result.grace_period_days == 30


# =============================================================================
# Reactivation Service
# =============================================================================


class TestReactivateContract:
    """Test reactivate_contract service function."""

    @pytest.mark.asyncio
    async def test_reactivate_deprecated_contract(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="deprecated")
        contract.deprecated_at = datetime.utcnow()
        contract.sunset_at = datetime.utcnow() + timedelta(days=30)
        contract.deprecation_reason = "test"
        contract.replacement_contract_id = str(uuid.uuid4())
        contract.grace_period_days = 30

        result = await reactivate_contract(db=db, contract=contract)

        assert result.status == "published"
        assert result.deprecated_at is None
        assert result.sunset_at is None
        assert result.deprecation_reason is None
        assert result.replacement_contract_id is None
        assert result.grace_period_days is None
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reactivate_non_deprecated(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="published")

        with pytest.raises(ValueError, match="Only deprecated"):
            await reactivate_contract(db=db, contract=contract)

    @pytest.mark.asyncio
    async def test_reactivate_after_sunset(self) -> None:
        db = _mock_db()
        contract = _make_contract(status="deprecated")
        contract.sunset_at = datetime.utcnow() - timedelta(days=1)

        with pytest.raises(ValueError, match="sunset date has passed"):
            await reactivate_contract(db=db, contract=contract)


# =============================================================================
# Version Listing Service
# =============================================================================


class TestListVersions:
    """Test list_versions service function."""

    @pytest.mark.asyncio
    async def test_list_versions_returns_all(self) -> None:
        db = _mock_db()
        v1 = _make_contract(version="1.0.0", status="deprecated")
        v2 = _make_contract(version="2.0.0", status="published")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [v2, v1]
        db.execute = AsyncMock(return_value=mock_result)

        versions = await list_versions(db, "test-tenant", "payment-api")

        assert len(versions) == 2
        assert versions[0].version == "2.0.0"
        assert versions[1].version == "1.0.0"

    @pytest.mark.asyncio
    async def test_list_versions_empty(self) -> None:
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        versions = await list_versions(db, "test-tenant", "nonexistent")
        assert versions == []


class TestGetActiveVersion:
    """Test get_active_version service function."""

    @pytest.mark.asyncio
    async def test_get_active_version_found(self) -> None:
        db = _mock_db()
        active = _make_contract(version="2.0.0", status="published")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = active
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_active_version(db, "test-tenant", "payment-api")
        assert result is not None
        assert result.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_get_active_version_none(self) -> None:
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_active_version(db, "test-tenant", "payment-api")
        assert result is None


class TestGetSunsetCandidates:
    """Test get_sunset_candidates service function."""

    @pytest.mark.asyncio
    async def test_get_sunset_candidates(self) -> None:
        db = _mock_db()
        past = _make_contract(status="deprecated")
        past.sunset_at = datetime.utcnow() - timedelta(days=5)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [past]
        db.execute = AsyncMock(return_value=mock_result)

        candidates = await get_sunset_candidates(db)
        assert len(candidates) == 1

    @pytest.mark.asyncio
    async def test_get_sunset_candidates_with_cutoff(self) -> None:
        db = _mock_db()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=mock_result)

        candidates = await get_sunset_candidates(
            db, before=datetime.utcnow() + timedelta(days=30)
        )
        assert candidates == []


# =============================================================================
# Schema Validation
# =============================================================================


class TestDeprecationSchemas:
    """Test Pydantic schema validation for lifecycle types."""

    def test_deprecate_request_valid(self) -> None:
        req = DeprecateContractRequest(
            reason="Replaced by v2",
            sunset_at=datetime(2026, 6, 1, tzinfo=UTC),
            grace_period_days=90,
        )
        assert req.reason == "Replaced by v2"
        assert req.grace_period_days == 90

    def test_deprecate_request_minimal(self) -> None:
        req = DeprecateContractRequest(reason="EOL")
        assert req.sunset_at is None
        assert req.replacement_contract_id is None
        assert req.grace_period_days is None

    def test_deprecate_request_empty_reason(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DeprecateContractRequest(reason="")

    def test_deprecate_request_grace_period_bounds(self) -> None:
        from pydantic import ValidationError

        req = DeprecateContractRequest(reason="test", grace_period_days=0)
        assert req.grace_period_days == 0

        req = DeprecateContractRequest(reason="test", grace_period_days=730)
        assert req.grace_period_days == 730

        with pytest.raises(ValidationError):
            DeprecateContractRequest(reason="test", grace_period_days=-1)

        with pytest.raises(ValidationError):
            DeprecateContractRequest(reason="test", grace_period_days=731)

    def test_deprecation_info_schema(self) -> None:
        info = ContractDeprecationInfo(
            contract_id=uuid.uuid4(),
            contract_name="test",
            version="1.0.0",
            status="deprecated",
            deprecated_at=datetime.utcnow(),
            is_sunset=False,
        )
        assert info.status == "deprecated"

    def test_version_summary_schema(self) -> None:
        summary = ContractVersionSummary(
            id=uuid.uuid4(),
            version="1.0.0",
            status="published",
            created_at=datetime.utcnow(),
        )
        assert summary.deprecated_at is None
        assert summary.sunset_at is None

    def test_versions_response_schema(self) -> None:
        resp = ContractVersionsResponse(
            contract_name="payment-api",
            tenant_id="test-tenant",
            versions=[],
            latest_version=None,
            active_count=0,
        )
        assert resp.versions == []


# =============================================================================
# Alembic Migration Metadata
# =============================================================================


class TestMigrationMetadata:
    """Verify migration file structure."""

    def test_migration_file_exists(self) -> None:
        import importlib.util
        from pathlib import Path

        migration_path = (
            Path(__file__).parent.parent
            / "alembic"
            / "versions"
            / "047_add_contract_deprecation_fields.py"
        )
        assert migration_path.exists(), f"Migration file not found: {migration_path}"

        spec = importlib.util.spec_from_file_location("migration_047", migration_path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.revision == "047_contract_deprecation"
        assert module.down_revision == "046_llm_budget_tables"
        assert hasattr(module, "upgrade")
        assert hasattr(module, "downgrade")
