"""Integration test: Full promotion chain — promote → approve → deploy → sync-ack → PROMOTED.

Tests the complete lifecycle without Kafka or real gateways.
Each step's output feeds the next step, validating the chain end-to-end.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.api_gateway_assignment import ApiGatewayAssignment
from src.models.catalog import APICatalog
from src.models.gateway_deployment import DeploymentSyncStatus, GatewayDeployment
from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus, GatewayType
from src.models.promotion import Promotion, PromotionStatus
from src.services.deployment_orchestration_service import DeploymentOrchestrationService
from src.services.promotion_service import PromotionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_catalog(tenant_id: str = "acme") -> MagicMock:
    api = MagicMock(spec=APICatalog)
    api.id = uuid4()
    api.tenant_id = tenant_id
    api.name = "test-api"
    api.api_id = "test-api"
    return api


def _make_gateway(
    *,
    name: str = "gw-1",
    environment: str = "staging",
    tenant_id: str = "acme",
) -> MagicMock:
    gw = MagicMock(spec=GatewayInstance)
    gw.id = uuid4()
    gw.name = name
    gw.display_name = name
    gw.gateway_type = GatewayType.STOA_EDGE_MCP
    gw.environment = environment
    gw.tenant_id = tenant_id
    gw.base_url = f"https://{name}.example.com"
    gw.auth_config = {"type": "gateway_key"}
    gw.status = GatewayInstanceStatus.ONLINE
    gw.source = "self_register"
    gw.mode = "edge-mcp"
    gw.protected = False
    gw.deleted_at = None
    return gw


def _make_assignment(
    api_catalog_id: uuid.UUID,
    gateway_id: uuid.UUID,
    *,
    environment: str = "staging",
    auto_deploy: bool = True,
) -> MagicMock:
    a = MagicMock(spec=ApiGatewayAssignment)
    a.id = uuid4()
    a.api_id = api_catalog_id
    a.gateway_id = gateway_id
    a.environment = environment
    a.auto_deploy = auto_deploy
    return a


def _make_deployment(
    api_catalog_id: uuid.UUID,
    gateway_id: uuid.UUID,
    *,
    promotion_id: uuid.UUID | None = None,
) -> GatewayDeployment:
    """Create a real GatewayDeployment object (not a mock) so attribute writes persist."""
    dep = GatewayDeployment()
    dep.id = uuid4()
    dep.api_catalog_id = api_catalog_id
    dep.gateway_instance_id = gateway_id
    dep.sync_status = DeploymentSyncStatus.PENDING
    dep.last_sync_attempt = None
    dep.last_sync_success = None
    dep.sync_error = None
    dep.sync_attempts = 0
    dep.promotion_id = promotion_id
    return dep


def _make_promotion(
    api_id: str = "test-api",
    *,
    tenant_id: str = "acme",
    status: str = PromotionStatus.PENDING.value,
) -> Promotion:
    """Create a real Promotion object so attribute writes persist."""
    p = Promotion()
    p.id = uuid4()
    p.tenant_id = tenant_id
    p.api_id = api_id
    p.source_environment = "dev"
    p.target_environment = "staging"
    p.status = status
    p.message = "QA release"
    p.requested_by = "user-creator"
    p.approved_by = None
    p.completed_at = None
    p.created_at = datetime.now(UTC)
    p.updated_at = datetime.now(UTC)
    return p


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPromotionChainIntegration:
    """End-to-end promotion chain with mocked repositories."""

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.notify_promotion_event", new_callable=AsyncMock)
    @patch("src.services.promotion_service.kafka_service")
    async def test_happy_path_single_gateway(self, mock_kafka, _mock_notify, mock_db):
        """1 API, 1 gateway, 1 assignment → promote → approve → deploy → ack → PROMOTED."""
        mock_kafka.emit_audit_event = AsyncMock()
        mock_kafka.publish = AsyncMock()

        api = _make_api_catalog()
        gw = _make_gateway()
        assignment = _make_assignment(api.id, gw.id)
        promo = _make_promotion(api_id=str(api.id))

        # --- Step 1: Create promotion ---
        promo_svc = PromotionService(mock_db)
        promo_svc.repo.get_active_for_target = AsyncMock(return_value=None)
        promo_svc.repo.create = AsyncMock(return_value=promo)

        created = await promo_svc.create_promotion(
            tenant_id="acme",
            api_id=str(api.id),
            source_environment="dev",
            target_environment="staging",
            message="QA release",
            requested_by="user-creator",
            user_id="uid-1",
        )
        assert created.status == PromotionStatus.PENDING.value

        # --- Step 2: Approve promotion → PROMOTING ---
        promo_svc.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)
        promo_svc.repo.update = AsyncMock(side_effect=lambda p: p)

        approved = await promo_svc.approve_promotion(
            tenant_id="acme",
            promotion_id=promo.id,
            approved_by="user-approver",
            user_id="uid-2",
        )
        assert approved.status == PromotionStatus.PROMOTING.value
        assert approved.approved_by == "user-approver"

        # --- Step 3: auto_deploy_on_promotion → creates GatewayDeployment(PENDING) ---
        deployment = _make_deployment(api.id, gw.id)

        orch_svc = DeploymentOrchestrationService(mock_db)
        # Mock _resolve_api_catalog
        orch_svc._resolve_api_catalog = AsyncMock(return_value=api)
        orch_svc.assignment_repo.list_auto_deploy = AsyncMock(return_value=[assignment])
        orch_svc._preflight_gateway_ids = AsyncMock(return_value=[MagicMock(deployable=True)])
        orch_svc.deploy_svc.deploy_api = AsyncMock(return_value=[deployment])

        deployments = await orch_svc.auto_deploy_on_promotion(
            api_id=str(api.id),
            tenant_id="acme",
            target_environment="staging",
            approved_by="user-approver",
            promotion_id=promo.id,
        )

        assert len(deployments) == 1
        assert deployments[0].sync_status == DeploymentSyncStatus.PENDING
        assert deployments[0].promotion_id == promo.id

        # --- Step 4: Simulate route-sync-ack (applied) → SYNCED ---
        dep = deployments[0]
        dep.sync_status = DeploymentSyncStatus.SYNCED
        dep.last_sync_success = datetime.now(UTC)
        dep.sync_error = None

        # --- Step 5: check_promotion_completion → PROMOTED ---
        promo_svc2 = PromotionService(mock_db)
        promo_svc2.gw_deploy_repo.list_by_promotion = AsyncMock(return_value=[dep])
        promo_svc2.repo.get_by_id = AsyncMock(return_value=promo)
        promo_svc2.repo.update = AsyncMock(side_effect=lambda p: p)

        await promo_svc2.check_promotion_completion(promo.id)

        assert promo.status == PromotionStatus.PROMOTED.value
        assert promo.completed_at is not None

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.notify_promotion_event", new_callable=AsyncMock)
    @patch("src.services.promotion_service.kafka_service")
    async def test_happy_path_multi_gateway(self, mock_kafka, _mock_notify, mock_db):
        """1 API, 2 gateways → both must ack(applied) before promotion completes."""
        mock_kafka.emit_audit_event = AsyncMock()
        mock_kafka.publish = AsyncMock()

        api = _make_api_catalog()
        gw1 = _make_gateway(name="gw-1")
        gw2 = _make_gateway(name="gw-2")
        assignment1 = _make_assignment(api.id, gw1.id)
        assignment2 = _make_assignment(api.id, gw2.id)
        promo = _make_promotion(api_id=str(api.id))

        # Create + approve promotion
        promo_svc = PromotionService(mock_db)
        promo_svc.repo.get_active_for_target = AsyncMock(return_value=None)
        promo_svc.repo.create = AsyncMock(return_value=promo)

        await promo_svc.create_promotion(
            tenant_id="acme",
            api_id=str(api.id),
            source_environment="dev",
            target_environment="staging",
            message="QA release",
            requested_by="user-creator",
            user_id="uid-1",
        )

        promo_svc.repo.get_by_id_and_tenant = AsyncMock(return_value=promo)
        promo_svc.repo.update = AsyncMock(side_effect=lambda p: p)

        await promo_svc.approve_promotion(
            tenant_id="acme",
            promotion_id=promo.id,
            approved_by="user-approver",
            user_id="uid-2",
        )
        assert promo.status == PromotionStatus.PROMOTING.value

        # auto_deploy → 2 deployments PENDING
        dep1 = _make_deployment(api.id, gw1.id)
        dep2 = _make_deployment(api.id, gw2.id)

        orch_svc = DeploymentOrchestrationService(mock_db)
        orch_svc._resolve_api_catalog = AsyncMock(return_value=api)
        orch_svc.assignment_repo.list_auto_deploy = AsyncMock(return_value=[assignment1, assignment2])
        orch_svc._preflight_gateway_ids = AsyncMock(
            return_value=[MagicMock(deployable=True), MagicMock(deployable=True)]
        )
        orch_svc.deploy_svc.deploy_api = AsyncMock(return_value=[dep1, dep2])

        deployments = await orch_svc.auto_deploy_on_promotion(
            api_id=str(api.id),
            tenant_id="acme",
            target_environment="staging",
            approved_by="user-approver",
            promotion_id=promo.id,
        )
        assert len(deployments) == 2
        assert all(d.promotion_id == promo.id for d in deployments)

        # --- Gateway 1 acks (applied) — dep2 still PENDING → promotion stays PROMOTING ---
        dep1.sync_status = DeploymentSyncStatus.SYNCED
        dep1.last_sync_success = datetime.now(UTC)

        check_svc = PromotionService(mock_db)
        check_svc.gw_deploy_repo.list_by_promotion = AsyncMock(return_value=[dep1, dep2])
        check_svc.repo.get_by_id = AsyncMock(return_value=promo)
        check_svc.repo.update = AsyncMock(side_effect=lambda p: p)

        await check_svc.check_promotion_completion(promo.id)
        # dep2 still PENDING → no state change
        assert promo.status == PromotionStatus.PROMOTING.value

        # --- Gateway 2 acks (applied) — all SYNCED → PROMOTED ---
        dep2.sync_status = DeploymentSyncStatus.SYNCED
        dep2.last_sync_success = datetime.now(UTC)

        check_svc2 = PromotionService(mock_db)
        check_svc2.gw_deploy_repo.list_by_promotion = AsyncMock(return_value=[dep1, dep2])
        check_svc2.repo.get_by_id = AsyncMock(return_value=promo)
        check_svc2.repo.update = AsyncMock(side_effect=lambda p: p)

        await check_svc2.check_promotion_completion(promo.id)
        assert promo.status == PromotionStatus.PROMOTED.value
        assert promo.completed_at is not None

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.notify_promotion_event", new_callable=AsyncMock)
    @patch("src.services.promotion_service.kafka_service")
    async def test_partial_failure(self, mock_kafka, _mock_notify, mock_db):
        """1 API, 2 gateways — gw1 applied, gw2 failed → promotion FAILED."""
        mock_kafka.emit_audit_event = AsyncMock()
        mock_kafka.publish = AsyncMock()

        api = _make_api_catalog()
        gw1 = _make_gateway(name="gw-1")
        gw2 = _make_gateway(name="gw-2")
        promo = _make_promotion(api_id=str(api.id))

        # Fast-forward: create + approve
        promo.status = PromotionStatus.PROMOTING.value
        promo.approved_by = "user-approver"

        # Create 2 deployments linked to promotion
        dep1 = _make_deployment(api.id, gw1.id, promotion_id=promo.id)
        dep2 = _make_deployment(api.id, gw2.id, promotion_id=promo.id)

        # Gateway 1 succeeds
        dep1.sync_status = DeploymentSyncStatus.SYNCED
        dep1.last_sync_success = datetime.now(UTC)

        # Gateway 2 fails
        dep2.sync_status = DeploymentSyncStatus.ERROR
        dep2.sync_error = "Connection refused"

        # check_promotion_completion → should FAIL the promotion
        check_svc = PromotionService(mock_db)
        check_svc.gw_deploy_repo.list_by_promotion = AsyncMock(return_value=[dep1, dep2])
        check_svc.repo.get_by_id = AsyncMock(return_value=promo)
        check_svc.repo.update = AsyncMock(side_effect=lambda p: p)

        await check_svc.check_promotion_completion(promo.id)

        assert dep1.sync_status == DeploymentSyncStatus.SYNCED
        assert dep2.sync_status == DeploymentSyncStatus.ERROR
        assert promo.status == PromotionStatus.FAILED.value
        assert promo.completed_at is not None

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.notify_promotion_event", new_callable=AsyncMock)
    @patch("src.services.promotion_service.kafka_service")
    async def test_state_machine_guard(self, mock_kafka, _mock_notify, mock_db):
        """Approve rejects non-PENDING promotions; check_completion is a no-op with PENDING deps."""
        mock_kafka.emit_audit_event = AsyncMock()

        # --- Guard 1: approve rejects a PROMOTING promotion ---
        promo_promoting = _make_promotion(status=PromotionStatus.PROMOTING.value)
        svc = PromotionService(mock_db)
        svc.repo.get_by_id_and_tenant = AsyncMock(return_value=promo_promoting)

        with pytest.raises(ValueError, match="Cannot approve"):
            await svc.approve_promotion(
                tenant_id="acme",
                promotion_id=promo_promoting.id,
                approved_by="admin",
                user_id="uid-1",
            )

        # --- Guard 2: approve rejects an already PROMOTED promotion ---
        promo_done = _make_promotion(status=PromotionStatus.PROMOTED.value)
        svc.repo.get_by_id_and_tenant = AsyncMock(return_value=promo_done)

        with pytest.raises(ValueError, match="Cannot approve"):
            await svc.approve_promotion(
                tenant_id="acme",
                promotion_id=promo_done.id,
                approved_by="admin",
                user_id="uid-1",
            )

        # --- Guard 3: check_completion is no-op when deps still PENDING ---
        api = _make_api_catalog()
        gw = _make_gateway()
        dep = _make_deployment(api.id, gw.id, promotion_id=promo_promoting.id)
        promo_wait = _make_promotion(status=PromotionStatus.PROMOTING.value)

        svc2 = PromotionService(mock_db)
        svc2.gw_deploy_repo.list_by_promotion = AsyncMock(return_value=[dep])
        svc2.repo.get_by_id = AsyncMock(return_value=promo_wait)
        svc2.repo.update = AsyncMock(side_effect=lambda p: p)

        await svc2.check_promotion_completion(promo_wait.id)
        # dep is PENDING → no transition
        assert promo_wait.status == PromotionStatus.PROMOTING.value
        svc2.repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    @patch("src.services.promotion_service.notify_promotion_event", new_callable=AsyncMock)
    @patch("src.services.promotion_service.kafka_service")
    async def test_completion_idempotence(self, mock_kafka, _mock_notify, mock_db):
        """Calling check_promotion_completion twice after all SYNCED is idempotent."""
        mock_kafka.emit_audit_event = AsyncMock()

        api = _make_api_catalog()
        gw = _make_gateway()
        promo = _make_promotion(status=PromotionStatus.PROMOTING.value)
        dep = _make_deployment(api.id, gw.id, promotion_id=promo.id)
        dep.sync_status = DeploymentSyncStatus.SYNCED
        dep.last_sync_success = datetime.now(UTC)

        # First call → completes the promotion
        svc = PromotionService(mock_db)
        svc.gw_deploy_repo.list_by_promotion = AsyncMock(return_value=[dep])
        svc.repo.get_by_id = AsyncMock(return_value=promo)
        svc.repo.update = AsyncMock(side_effect=lambda p: p)

        await svc.check_promotion_completion(promo.id)
        assert promo.status == PromotionStatus.PROMOTED.value

        # Second call → should be idempotent (complete_promotion is called again
        # but the ValueError catch in check_promotion_completion handles it).
        # Since complete_promotion doesn't guard status, it will overwrite — but
        # the chain should not raise.
        svc2 = PromotionService(mock_db)
        svc2.gw_deploy_repo.list_by_promotion = AsyncMock(return_value=[dep])
        svc2.repo.get_by_id = AsyncMock(return_value=promo)
        svc2.repo.update = AsyncMock(side_effect=lambda p: p)

        # No exception raised
        await svc2.check_promotion_completion(promo.id)
        assert promo.status == PromotionStatus.PROMOTED.value
