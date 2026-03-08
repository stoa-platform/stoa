"""Tests for Promotion model, schema, repository, and chain validation (CAB-1706 W1)"""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from src.models.promotion import (
    VALID_PROMOTION_CHAINS,
    Promotion,
    PromotionStatus,
    validate_promotion_chain,
)
from src.schemas.promotion import (
    PromotionCreate,
    PromotionDiffResponse,
    PromotionListResponse,
    PromotionResponse,
    PromotionRollbackRequest,
)

# ============================================================================
# Chain Validation
# ============================================================================


class TestValidatePromotionChain:
    def test_dev_to_staging_allowed(self):
        validate_promotion_chain("dev", "staging")  # Should not raise

    def test_staging_to_production_allowed(self):
        validate_promotion_chain("staging", "production")  # Should not raise

    def test_dev_to_production_blocked(self):
        with pytest.raises(ValueError, match="Invalid promotion chain: dev→production"):
            validate_promotion_chain("dev", "production")

    def test_same_to_same_blocked(self):
        with pytest.raises(ValueError, match="Cannot promote to the same environment"):
            validate_promotion_chain("staging", "staging")

    def test_production_to_staging_blocked(self):
        with pytest.raises(ValueError, match="Invalid promotion chain"):
            validate_promotion_chain("production", "staging")

    def test_production_to_dev_blocked(self):
        with pytest.raises(ValueError, match="Invalid promotion chain"):
            validate_promotion_chain("production", "dev")

    def test_valid_chains_constant(self):
        assert ("dev", "staging") in VALID_PROMOTION_CHAINS
        assert ("staging", "production") in VALID_PROMOTION_CHAINS
        assert len(VALID_PROMOTION_CHAINS) == 2


# ============================================================================
# Model
# ============================================================================


class TestPromotionModel:
    def test_status_enum_values(self):
        assert PromotionStatus.PENDING == "pending"
        assert PromotionStatus.PROMOTING == "promoting"
        assert PromotionStatus.PROMOTED == "promoted"
        assert PromotionStatus.FAILED == "failed"
        assert PromotionStatus.ROLLED_BACK == "rolled_back"

    def test_repr(self):
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.source_environment = "dev"
        promo.target_environment = "staging"
        promo.status = "promoting"
        r = repr(promo)
        assert "dev→staging" in r
        assert "promoting" in r


# ============================================================================
# Pydantic Schemas
# ============================================================================


class TestPromotionSchemas:
    def test_create_valid(self):
        data = PromotionCreate(
            source_environment="dev",
            target_environment="staging",
            message="Deploy v2.1 to staging for QA",
        )
        assert data.source_environment == "dev"
        assert data.target_environment == "staging"
        assert data.message == "Deploy v2.1 to staging for QA"

    def test_create_message_required(self):
        with pytest.raises(ValidationError):
            PromotionCreate(
                source_environment="dev",
                target_environment="staging",
                # message missing → validation error
            )

    def test_create_message_not_empty(self):
        with pytest.raises(ValidationError):
            PromotionCreate(
                source_environment="dev",
                target_environment="staging",
                message="",
            )

    def test_create_message_max_length(self):
        with pytest.raises(ValidationError):
            PromotionCreate(
                source_environment="dev",
                target_environment="staging",
                message="x" * 1001,
            )

    def test_response_from_attributes(self):
        mock_promo = MagicMock()
        mock_promo.id = uuid.uuid4()
        mock_promo.tenant_id = "acme"
        mock_promo.api_id = "api-123"
        mock_promo.source_environment = "dev"
        mock_promo.target_environment = "staging"
        mock_promo.source_deployment_id = None
        mock_promo.target_deployment_id = None
        mock_promo.status = "promoting"
        mock_promo.spec_diff = None
        mock_promo.message = "QA release"
        mock_promo.requested_by = "user-abc"
        mock_promo.approved_by = None
        mock_promo.completed_at = None
        mock_promo.created_at = datetime.utcnow()
        mock_promo.updated_at = datetime.utcnow()

        resp = PromotionResponse.model_validate(mock_promo, from_attributes=True)
        assert resp.tenant_id == "acme"
        assert resp.status == "promoting"
        assert resp.message == "QA release"

    def test_list_response(self):
        data = PromotionListResponse(items=[], total=0)
        assert data.items == []
        assert data.page == 1
        assert data.page_size == 50

    def test_rollback_request_message_required(self):
        req = PromotionRollbackRequest(message="Reverting due to bug in staging")
        assert req.message == "Reverting due to bug in staging"

        with pytest.raises(ValidationError):
            PromotionRollbackRequest(message="")

    def test_diff_response(self):
        diff = PromotionDiffResponse(
            promotion_id=uuid.uuid4(),
            source_environment="dev",
            target_environment="staging",
            source_spec={"version": "2.0"},
            target_spec={"version": "1.0"},
            diff_summary={"changed_fields": ["version"]},
        )
        assert diff.source_environment == "dev"
        assert diff.diff_summary["changed_fields"] == ["version"]


# ============================================================================
# Repository (unit tests with mocked session)
# ============================================================================


class TestPromotionRepository:
    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def repo(self, mock_db):
        from src.repositories.promotion import PromotionRepository

        return PromotionRepository(mock_db)

    @pytest.mark.asyncio
    async def test_create(self, repo, mock_db):
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.tenant_id = "acme"
        promo.message = "test"

        mock_db.flush = AsyncMock()
        mock_db.refresh = AsyncMock()

        await repo.create(promo)
        mock_db.add.assert_called_once_with(promo)
        mock_db.flush.assert_awaited_once()
        mock_db.refresh.assert_awaited_once_with(promo)

    @pytest.mark.asyncio
    async def test_get_by_id(self, repo, mock_db):
        expected = Promotion()
        expected.id = uuid.uuid4()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_id(expected.id)
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_by_id_and_tenant(self, repo, mock_db):
        expected = Promotion()
        expected.id = uuid.uuid4()
        expected.tenant_id = "acme"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_by_id_and_tenant(expected.id, "acme")
        assert result == expected

    @pytest.mark.asyncio
    async def test_list_by_tenant(self, repo, mock_db):
        mock_count = MagicMock()
        mock_count.scalar.return_value = 2
        mock_items = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [Promotion(), Promotion()]
        mock_items.scalars.return_value = mock_scalars
        mock_db.execute = AsyncMock(side_effect=[mock_count, mock_items])

        items, total = await repo.list_by_tenant("acme")
        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_get_active_for_target(self, repo, mock_db):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await repo.get_active_for_target("api-1", "staging")
        assert result is None
