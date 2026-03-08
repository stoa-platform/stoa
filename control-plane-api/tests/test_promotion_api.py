"""Tests for Promotion service + router (CAB-1706 W2 + W3)"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.models.deployment import Deployment
from src.models.promotion import Promotion, PromotionStatus
from src.notifications.templates import format_message
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
        promo.api_id = "api-1"
        promo.source_environment = "dev"
        promo.target_environment = "staging"
        promo.spec_diff = {"changed_fields": ["version"]}
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)
        service.deployment_repo.get_latest_success = AsyncMock(return_value=None)

        result = await service.get_diff("acme", promo.id)

        assert result["source_environment"] == "dev"
        assert result["diff_summary"] == {"changed_fields": ["version"]}
        assert result["source_spec"] is None
        assert result["target_spec"] is None

    @pytest.mark.asyncio
    async def test_get_diff_not_found(self, service):
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="not found"):
            await service.get_diff("acme", uuid.uuid4())


# ============================================================================
# W3 — Self-Approve Guard + Computed Diff
# ============================================================================


class TestPromotionSelfApproveGuard:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return PromotionService(mock_db)

    @pytest.mark.asyncio
    async def test_self_approve_blocked_for_production(self, service):
        """4-eyes principle: requester cannot approve their own promotion to production."""
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.tenant_id = "acme"
        promo.api_id = "api-1"
        promo.source_environment = "staging"
        promo.target_environment = "production"
        promo.status = PromotionStatus.PENDING.value
        promo.requested_by = "alice@acme.com"
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)

        with pytest.raises(ValueError, match="4-eyes principle"):
            await service.approve_promotion(
                tenant_id="acme",
                promotion_id=promo.id,
                approved_by="alice@acme.com",
                user_id="uid-alice",
            )

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.kafka_service")
    async def test_self_approve_allowed_for_staging(self, mock_kafka, service):
        """2-eyes principle: requester can self-approve dev→staging promotions."""
        mock_kafka.publish = AsyncMock()
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.tenant_id = "acme"
        promo.api_id = "api-1"
        promo.source_environment = "dev"
        promo.target_environment = "staging"
        promo.status = PromotionStatus.PENDING.value
        promo.requested_by = "alice@acme.com"
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)
        service.repo.update = AsyncMock(return_value=promo)

        result = await service.approve_promotion(
            tenant_id="acme",
            promotion_id=promo.id,
            approved_by="alice@acme.com",
            user_id="uid-alice",
        )

        assert result.approved_by == "alice@acme.com"
        assert result.status == PromotionStatus.PROMOTING.value

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.kafka_service")
    async def test_different_user_can_approve(self, mock_kafka, service):
        """A different user can approve the promotion."""
        mock_kafka.publish = AsyncMock()
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.tenant_id = "acme"
        promo.api_id = "api-1"
        promo.source_environment = "dev"
        promo.target_environment = "staging"
        promo.status = PromotionStatus.PENDING.value
        promo.requested_by = "alice@acme.com"
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)
        service.repo.update = AsyncMock(return_value=promo)

        result = await service.approve_promotion(
            tenant_id="acme",
            promotion_id=promo.id,
            approved_by="bob@acme.com",
            user_id="uid-bob",
        )

        assert result.approved_by == "bob@acme.com"
        assert result.status == PromotionStatus.PROMOTING.value


class TestPromotionComputedDiff:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return PromotionService(mock_db)

    @pytest.mark.asyncio
    async def test_diff_with_deployment_specs(self, service):
        """get_diff returns actual deployment specs from source and target."""
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.api_id = "payment-api"
        promo.source_environment = "dev"
        promo.target_environment = "staging"
        promo.spec_diff = {"changed_fields": ["version"]}
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)

        source_deploy = Deployment()
        source_deploy.id = uuid.uuid4()
        source_deploy.version = "2.0.0"
        source_deploy.spec_hash = "abc123"
        source_deploy.commit_sha = "def456"
        source_deploy.deployed_by = "alice"
        source_deploy.completed_at = datetime(2026, 3, 8, 10, 0, 0, tzinfo=UTC)

        target_deploy = Deployment()
        target_deploy.id = uuid.uuid4()
        target_deploy.version = "1.0.0"
        target_deploy.spec_hash = "xyz789"
        target_deploy.commit_sha = "uvw012"
        target_deploy.deployed_by = "bob"
        target_deploy.completed_at = datetime(2026, 3, 7, 10, 0, 0, tzinfo=UTC)

        env_map = {"dev": source_deploy, "staging": target_deploy}
        service.deployment_repo.get_latest_success = AsyncMock(
            side_effect=lambda **kwargs: env_map.get(kwargs.get("environment"))
        )

        result = await service.get_diff("acme", promo.id)

        assert result["source_spec"]["version"] == "2.0.0"
        assert result["target_spec"]["version"] == "1.0.0"
        assert result["diff_summary"] == {"changed_fields": ["version"]}

    @pytest.mark.asyncio
    async def test_diff_no_target_deployment(self, service):
        """get_diff returns None for target_spec when no deployment exists yet."""
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.api_id = "new-api"
        promo.source_environment = "dev"
        promo.target_environment = "staging"
        promo.spec_diff = None
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)

        source_deploy = Deployment()
        source_deploy.id = uuid.uuid4()
        source_deploy.version = "1.0.0"
        source_deploy.spec_hash = "abc123"
        source_deploy.commit_sha = "def456"
        source_deploy.deployed_by = "alice"
        source_deploy.completed_at = datetime(2026, 3, 8, 10, 0, 0, tzinfo=UTC)

        env_map = {"dev": source_deploy}
        service.deployment_repo.get_latest_success = AsyncMock(
            side_effect=lambda **kwargs: env_map.get(kwargs.get("environment"))
        )

        result = await service.get_diff("acme", promo.id)

        assert result["source_spec"] is not None
        assert result["target_spec"] is None


# ============================================================================
# Promotion Notification Templates (CAB-1706)
# ============================================================================


class TestPromotionNotificationTemplates:
    def test_pending_approval_staging(self):
        msg = format_message(
            "promotion.pending_approval",
            {
                "api_id": "orders-api",
                "tenant_id": "acme",
                "source_environment": "dev",
                "target_environment": "staging",
                "requested_by": "torpedo",
                "message": "Ready for QA",
                "console_url": "https://console.gostoa.dev",
            },
        )
        assert msg is not None
        assert "orders-api" in msg
        assert "DEV" in msg
        assert "STAGING" in msg
        assert "torpedo" in msg
        assert "self-approval allowed" in msg
        assert "Ready for QA" in msg
        assert "console.gostoa.dev" in msg

    def test_pending_approval_production_4eyes(self):
        msg = format_message(
            "promotion.pending_approval",
            {
                "api_id": "billing-api",
                "tenant_id": "acme",
                "source_environment": "staging",
                "target_environment": "production",
                "requested_by": "torpedo",
            },
        )
        assert msg is not None
        assert "4-eyes required" in msg
        assert "PRODUCTION" in msg

    def test_approved(self):
        msg = format_message(
            "promotion.approved",
            {
                "api_id": "orders-api",
                "source_environment": "dev",
                "target_environment": "staging",
                "approved_by": "admin",
            },
        )
        assert msg is not None
        assert "approved" in msg.lower()
        assert "admin" in msg

    def test_rolled_back(self):
        msg = format_message(
            "promotion.rolled_back",
            {
                "api_id": "orders-api",
                "source_environment": "dev",
                "target_environment": "staging",
                "requested_by": "torpedo",
            },
        )
        assert msg is not None
        assert "rolled back" in msg.lower()
        assert "torpedo" in msg

    def test_unknown_event_returns_none(self):
        assert format_message("promotion.unknown", {}) is None


class TestPromotionServiceNotifications:
    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db):
        return PromotionService(mock_db)

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.notify_promotion_event")
    @patch("src.services.promotion_service.kafka_service")
    async def test_create_sends_slack_notification(self, mock_kafka, mock_notify, service):
        mock_kafka.emit_audit_event = AsyncMock()
        mock_notify.return_value = None
        service.repo.get_active_for_target = AsyncMock(return_value=None)
        created = Promotion()
        created.id = uuid.uuid4()
        created.tenant_id = "acme"
        created.api_id = "api-1"
        created.source_environment = "dev"
        created.target_environment = "staging"
        created.status = PromotionStatus.PENDING.value
        created.message = "QA release"
        created.requested_by = "torpedo"
        service.repo.create = AsyncMock(return_value=created)

        await service.create_promotion(
            tenant_id="acme",
            api_id="api-1",
            source_environment="dev",
            target_environment="staging",
            message="QA release",
            requested_by="torpedo",
            user_id="uid-1",
        )

        mock_notify.assert_awaited_once()
        call_args = mock_notify.call_args
        assert call_args[0][0] == "promotion.pending_approval"
        payload = call_args[0][1]
        assert payload["api_id"] == "api-1"
        assert payload["requested_by"] == "torpedo"
        assert "console_url" in payload

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.notify_promotion_event")
    @patch("src.services.promotion_service.kafka_service")
    async def test_approve_sends_slack_notification(self, mock_kafka, mock_notify, service):
        mock_kafka.publish = AsyncMock()
        mock_notify.return_value = None
        promo = Promotion()
        promo.id = uuid.uuid4()
        promo.tenant_id = "acme"
        promo.api_id = "api-1"
        promo.source_environment = "dev"
        promo.target_environment = "staging"
        promo.status = PromotionStatus.PENDING.value
        promo.requested_by = "torpedo"
        service.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)
        service.repo.update = AsyncMock(return_value=promo)

        await service.approve_promotion(
            tenant_id="acme",
            promotion_id=promo.id,
            approved_by="admin",
            user_id="uid-2",
        )

        mock_notify.assert_awaited_once_with(
            "promotion.approved",
            {
                "api_id": "api-1",
                "source_environment": "dev",
                "target_environment": "staging",
                "approved_by": "admin",
            },
        )
