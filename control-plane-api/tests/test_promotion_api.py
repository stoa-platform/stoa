"""Tests for Promotion service + router (CAB-1706 W2)"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.models.promotion import Promotion, PromotionStatus
from src.services.promotion_service import PromotionService

# ============================================================================
# Service Tests
# ============================================================================


class TestPromotionServiceCreate:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return PromotionService(mock_db)

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.kafka_service")
    async def test_create_valid(self, mock_kafka, service):
        mock_kafka.emit_audit_event = AsyncMock()
        service.repo.get_active_for_target = AsyncMock(return_value=None)
        created = Promotion()
        created.id = uuid.uuid4()
        created.tenant_id = "acme"
        created.api_id = "api-1"
        created.source_environment = "dev"
        created.target_environment = "staging"
        created.status = PromotionStatus.PENDING.value
        created.message = "QA release"
        created.requested_by = "user1"
        service.repo.create = AsyncMock(return_value=created)

        result = await service.create_promotion(
            tenant_id="acme",
            api_id="api-1",
            source_environment="dev",
            target_environment="staging",
            message="QA release",
            requested_by="user1",
            user_id="uid-1",
        )

        assert result.status == PromotionStatus.PENDING.value
        service.repo.create.assert_awaited_once()
        mock_kafka.emit_audit_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_invalid_chain(self, service):
        with pytest.raises(ValueError, match="Invalid promotion chain"):
            await service.create_promotion(
                tenant_id="acme",
                api_id="api-1",
                source_environment="dev",
                target_environment="production",
                message="Skip staging",
                requested_by="user1",
                user_id="uid-1",
            )

    @pytest.mark.asyncio
    async def test_create_active_conflict(self, service):
        existing = Promotion()
        existing.id = uuid.uuid4()
        existing.status = PromotionStatus.PENDING.value
        service.repo.get_active_for_target = AsyncMock(return_value=existing)

        with pytest.raises(ValueError, match="Active promotion already exists"):
            await service.create_promotion(
                tenant_id="acme",
                api_id="api-1",
                source_environment="dev",
                target_environment="staging",
                message="Duplicate",
                requested_by="user1",
                user_id="uid-1",
            )


class TestPromotionServiceApprove:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return PromotionService(mock_db)

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.kafka_service")
    async def test_approve_pending(self, mock_kafka, service):
        mock_kafka.publish = AsyncMock()
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.tenant_id = "acme"
        promo.api_id = "api-1"
        promo.source_environment = "dev"
        promo.target_environment = "staging"
        promo.status = PromotionStatus.PENDING.value
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)
        service.repo.update = AsyncMock(return_value=promo)

        result = await service.approve_promotion(
            tenant_id="acme",
            promotion_id=promo.id,
            approved_by="admin",
            user_id="uid-2",
        )

        assert result.status == PromotionStatus.PROMOTING.value
        assert result.approved_by == "admin"
        mock_kafka.publish.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approve_not_found(self, service):
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await service.approve_promotion(
                tenant_id="acme",
                promotion_id=uuid.uuid4(),
                approved_by="admin",
                user_id="uid-2",
            )

    @pytest.mark.asyncio
    async def test_approve_wrong_status(self, service):
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.status = PromotionStatus.PROMOTED.value
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)

        with pytest.raises(ValueError, match="Cannot approve"):
            await service.approve_promotion(
                tenant_id="acme",
                promotion_id=promo.id,
                approved_by="admin",
                user_id="uid-2",
            )


class TestPromotionServiceRollback:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return PromotionService(mock_db)

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.kafka_service")
    async def test_rollback_promoted(self, mock_kafka, service):
        mock_kafka.emit_audit_event = AsyncMock()
        original = Promotion()
        original.id = uuid.uuid4()
        original.tenant_id = "acme"
        original.api_id = "api-1"
        original.source_environment = "dev"
        original.target_environment = "staging"
        original.status = PromotionStatus.PROMOTED.value
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=original)
        service.repo.update = AsyncMock(return_value=original)

        rollback_promo = Promotion()
        rollback_promo.id = uuid.uuid4()
        rollback_promo.status = PromotionStatus.PROMOTING.value
        service.repo.create = AsyncMock(return_value=rollback_promo)

        result = await service.rollback_promotion(
            tenant_id="acme",
            promotion_id=original.id,
            message="Rollback due to bug",
            requested_by="user1",
            user_id="uid-1",
        )

        assert result.status == PromotionStatus.PROMOTING.value
        assert original.status == PromotionStatus.ROLLED_BACK.value
        mock_kafka.emit_audit_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rollback_wrong_status(self, service):
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.status = PromotionStatus.PENDING.value
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)

        with pytest.raises(ValueError, match="Can only rollback promoted"):
            await service.rollback_promotion(
                tenant_id="acme",
                promotion_id=promo.id,
                message="Nope",
                requested_by="user1",
                user_id="uid-1",
            )


class TestPromotionServiceComplete:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return PromotionService(mock_db)

    @pytest.mark.asyncio
    async def test_complete_success(self, service):
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.status = PromotionStatus.PROMOTING.value
        service.repo.get_by_id = AsyncMock(return_value=promo)
        service.repo.update = AsyncMock(return_value=promo)

        result = await service.complete_promotion(
            promotion_id=promo.id,
            target_deployment_id=uuid.uuid4(),
            spec_diff={"changed": ["version"]},
        )

        assert result.status == PromotionStatus.PROMOTED.value
        assert result.completed_at is not None
        assert result.spec_diff == {"changed": ["version"]}

    @pytest.mark.asyncio
    async def test_fail_promotion(self, service):
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.status = PromotionStatus.PROMOTING.value
        service.repo.get_by_id = AsyncMock(return_value=promo)
        service.repo.update = AsyncMock(return_value=promo)

        result = await service.fail_promotion(promo.id, "Gateway timeout")

        assert result.status == PromotionStatus.FAILED.value
        assert result.completed_at is not None


class TestPromotionServiceDiff:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return PromotionService(mock_db)

    @pytest.mark.asyncio
    async def test_get_diff(self, service):
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.source_environment = "dev"
        promo.target_environment = "staging"
        promo.spec_diff = {"changed_fields": ["version"]}
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)

        result = await service.get_diff("acme", promo.id)

        assert result["source_environment"] == "dev"
        assert result["diff_summary"] == {"changed_fields": ["version"]}

    @pytest.mark.asyncio
    async def test_get_diff_not_found(self, service):
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await service.get_diff("acme", uuid.uuid4())
