"""Tests for deployment log streaming (CAB-1420)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.events.event_bus import EventBus, Subscriber
from src.models.deployment_log import DeploymentLog, LogLevel
from src.repositories.deployment_log import DeploymentLogRepository
from src.services.deployment_service import DeploymentService

# --- Helpers ---


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    return db


def _mock_log(**kwargs):
    log = MagicMock(spec=DeploymentLog)
    log.id = kwargs.get("id", uuid4())
    log.deployment_id = kwargs.get("deployment_id", uuid4())
    log.tenant_id = kwargs.get("tenant_id", "acme")
    log.seq = kwargs.get("seq", 1)
    log.level = kwargs.get("level", LogLevel.INFO.value)
    log.step = kwargs.get("step", "init")
    log.message = kwargs.get("message", "Deployment queued")
    log.created_at = kwargs.get("created_at")
    return log


# --- Model Tests ---


class TestDeploymentLogModel:
    def test_log_level_enum_values(self):
        assert LogLevel.INFO == "info"
        assert LogLevel.WARN == "warn"
        assert LogLevel.ERROR == "error"
        assert LogLevel.DEBUG == "debug"

    def test_repr(self):
        log = DeploymentLog()
        log.id = uuid4()
        log.deployment_id = uuid4()
        log.seq = 3
        assert "DeploymentLog" in repr(log)
        assert "seq=3" in repr(log)


# --- Repository Tests ---


class TestDeploymentLogRepository:
    class TestCreate:
        async def test_creates_and_flushes(self):
            db = _mock_db()
            repo = DeploymentLogRepository(db)
            log = _mock_log()

            result = await repo.create(log)

            db.add.assert_called_once_with(log)
            db.flush.assert_awaited_once()
            db.refresh.assert_awaited_once_with(log)
            assert result is log

    class TestListByDeployment:
        async def test_returns_logs_ordered_by_seq(self):
            db = _mock_db()
            logs = [_mock_log(seq=1), _mock_log(seq=2), _mock_log(seq=3)]
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = logs
            db.execute = AsyncMock(return_value=mock_result)

            repo = DeploymentLogRepository(db)
            deploy_id = uuid4()
            result = await repo.list_by_deployment(deploy_id, "acme")

            assert len(result) == 3
            db.execute.assert_awaited_once()

        async def test_empty_deployment(self):
            db = _mock_db()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            db.execute = AsyncMock(return_value=mock_result)

            repo = DeploymentLogRepository(db)
            result = await repo.list_by_deployment(uuid4(), "acme")

            assert result == []

    class TestNextSeq:
        async def test_first_log_returns_1(self):
            db = _mock_db()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 0
            db.execute = AsyncMock(return_value=mock_result)

            repo = DeploymentLogRepository(db)
            seq = await repo.next_seq(uuid4())

            assert seq == 1

        async def test_increments_existing(self):
            db = _mock_db()
            mock_result = MagicMock()
            mock_result.scalar.return_value = 5
            db.execute = AsyncMock(return_value=mock_result)

            repo = DeploymentLogRepository(db)
            seq = await repo.next_seq(uuid4())

            assert seq == 6


# --- EventBus Tests ---


class TestEventBus:
    def test_subscribe_and_unsubscribe(self):
        bus = EventBus()
        sub = bus.subscribe(tenant_id="acme")

        assert bus.subscriber_count == 1
        bus.unsubscribe(sub)
        assert bus.subscriber_count == 0

    async def test_publish_delivers_to_matching_subscriber(self):
        bus = EventBus()
        sub = bus.subscribe(tenant_id="acme")

        count = await bus.publish("acme", "deploy-progress", {"msg": "step 1"})

        assert count == 1
        event = sub.queue.get_nowait()
        assert event["event"] == "deploy-progress"
        assert event["data"]["msg"] == "step 1"

    async def test_publish_skips_wrong_tenant(self):
        bus = EventBus()
        bus.subscribe(tenant_id="other-tenant")

        count = await bus.publish("acme", "deploy-progress", {"msg": "test"})

        assert count == 0

    async def test_publish_skips_wrong_event_type(self):
        bus = EventBus()
        bus.subscribe(tenant_id="acme", event_types=["deploy-success"])

        count = await bus.publish("acme", "deploy-progress", {"msg": "test"})

        assert count == 0

    async def test_wildcard_tenant_receives_all(self):
        bus = EventBus()
        sub = bus.subscribe(tenant_id="*")

        await bus.publish("acme", "deploy-progress", {"msg": "1"})
        await bus.publish("other", "deploy-progress", {"msg": "2"})

        assert sub.queue.qsize() == 2

    async def test_full_queue_drops_event(self):
        bus = EventBus()
        sub = bus.subscribe(tenant_id="acme")
        # Fill the queue
        for _i in range(256):
            sub.queue.put_nowait({"event": "filler", "data": {}})

        count = await bus.publish("acme", "deploy-progress", {"msg": "overflow"})

        assert count == 0  # Dropped because queue is full


class TestSubscriber:
    def test_accepts_matching_tenant_and_type(self):
        sub = Subscriber(tenant_id="acme", event_types=["deploy-progress"])
        assert sub.accepts("acme", "deploy-progress") is True

    def test_rejects_wrong_tenant(self):
        sub = Subscriber(tenant_id="acme", event_types=None)
        assert sub.accepts("other", "deploy-progress") is False

    def test_rejects_wrong_event_type(self):
        sub = Subscriber(tenant_id="acme", event_types=["deploy-success"])
        assert sub.accepts("acme", "deploy-progress") is False

    def test_wildcard_accepts_any_tenant(self):
        sub = Subscriber(tenant_id="*")
        assert sub.accepts("anything", "any-event") is True

    def test_no_filter_accepts_any_event_type(self):
        sub = Subscriber(tenant_id="acme", event_types=None)
        assert sub.accepts("acme", "deploy-progress") is True


# --- Service add_log Tests ---


class TestDeploymentServiceAddLog:
    async def test_add_log_creates_entry_and_emits(self):
        db = _mock_db()
        deploy_id = uuid4()
        log_entry = _mock_log(deployment_id=deploy_id, seq=1)

        with (
            patch.object(DeploymentLogRepository, "next_seq", new_callable=AsyncMock, return_value=1),
            patch.object(DeploymentLogRepository, "create", new_callable=AsyncMock, return_value=log_entry),
            patch("src.services.deployment_service.emit_deployment_log", new_callable=AsyncMock) as mock_emit,
        ):
            service = DeploymentService(db)
            result = await service.add_log(deploy_id, "acme", "Test message", step="init")

            assert result is log_entry
            mock_emit.assert_awaited_once()
            call_kwargs = mock_emit.call_args
            assert call_kwargs.kwargs["deployment_id"] == str(deploy_id)
            assert call_kwargs.kwargs["tenant_id"] == "acme"
            assert call_kwargs.kwargs["seq"] == 1

    async def test_get_logs_delegates_to_repo(self):
        db = _mock_db()
        deploy_id = uuid4()
        logs = [_mock_log(seq=1), _mock_log(seq=2)]

        with patch.object(
            DeploymentLogRepository,
            "list_by_deployment",
            new_callable=AsyncMock,
            return_value=logs,
        ):
            service = DeploymentService(db)
            result = await service.get_logs(deploy_id, "acme")

            assert len(result) == 2


# --- Router Tests ---


class TestDeploymentLogsRouter:
    def test_get_logs_returns_entries(self, app_with_tenant_admin, mock_db_session):
        deploy_id = uuid4()
        mock_deployment = MagicMock()
        mock_deployment.id = deploy_id
        mock_deployment.tenant_id = "acme"

        log1 = _mock_log(deployment_id=deploy_id, seq=1, message="Queued")
        log1.id = uuid4()
        log1.created_at = "2026-02-23T10:00:00"

        with (patch("src.routers.deployments.DeploymentService") as MockSvc,):
            instance = MockSvc.return_value
            instance.get_deployment = AsyncMock(return_value=mock_deployment)
            instance.get_logs = AsyncMock(return_value=[log1])

            from starlette.testclient import TestClient

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/tenants/acme/deployments/{deploy_id}/logs")

        assert response.status_code == 200
        data = response.json()
        assert data["deployment_id"] == str(deploy_id)
        assert len(data["logs"]) == 1
        assert data["logs"][0]["message"] == "Queued"

    def test_get_logs_404_for_missing_deployment(self, app_with_tenant_admin, mock_db_session):
        deploy_id = uuid4()

        with patch("src.routers.deployments.DeploymentService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_deployment = AsyncMock(return_value=None)

            from starlette.testclient import TestClient

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/tenants/acme/deployments/{deploy_id}/logs")

        assert response.status_code == 404

    def test_get_logs_with_after_seq(self, app_with_tenant_admin, mock_db_session):
        deploy_id = uuid4()
        mock_deployment = MagicMock()
        mock_deployment.id = deploy_id

        with patch("src.routers.deployments.DeploymentService") as MockSvc:
            instance = MockSvc.return_value
            instance.get_deployment = AsyncMock(return_value=mock_deployment)
            instance.get_logs = AsyncMock(return_value=[])

            from starlette.testclient import TestClient

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/tenants/acme/deployments/{deploy_id}/logs?after_seq=5&limit=10")

        assert response.status_code == 200
        instance.get_logs.assert_awaited_once()
        call_kwargs = instance.get_logs.call_args
        assert call_kwargs.kwargs.get("after_seq") == 5 or call_kwargs[1].get("after_seq") == 5
