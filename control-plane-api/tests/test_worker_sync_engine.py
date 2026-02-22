"""Tests for SyncEngine worker (CAB-1388)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.workers.sync_engine import (
    CONSUMER_GROUP,
    SyncEngine,
)
from src.models.gateway_deployment import DeploymentSyncStatus
from src.models.gateway_instance import GatewayInstanceStatus


# ── Helpers ──


def _make_session_factory(session):
    """Return a mock _get_session_factory that yields the given session."""
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    factory = MagicMock(return_value=mock_cm)
    return MagicMock(return_value=factory)


def _mock_session():
    s = AsyncMock()
    s.commit = AsyncMock()
    return s


def _mock_deployment(**kwargs):
    d = MagicMock()
    d.id = kwargs.get("id", uuid4())
    d.gateway_instance_id = kwargs.get("gateway_instance_id", uuid4())
    d.sync_status = kwargs.get("sync_status", DeploymentSyncStatus.PENDING)
    d.sync_attempts = kwargs.get("sync_attempts", 0)
    d.sync_error = kwargs.get("sync_error", None)
    d.desired_state = kwargs.get("desired_state", {"tenant_id": "acme"})
    d.actual_state = kwargs.get("actual_state", None)
    d.gateway_resource_id = kwargs.get("gateway_resource_id", "gw-res-1")
    d.api_catalog_id = kwargs.get("api_catalog_id", uuid4())
    d.last_sync_attempt = None
    d.last_sync_success = None
    return d


def _mock_gateway(**kwargs):
    from src.models.gateway_instance import GatewayInstanceStatus
    g = MagicMock()
    g.id = kwargs.get("id", uuid4())
    g.name = kwargs.get("name", "test-gw")
    g.status = kwargs.get("status", GatewayInstanceStatus.ONLINE)
    g.gateway_type = MagicMock(value=kwargs.get("gateway_type_value", "stoa"))
    g.base_url = kwargs.get("base_url", "http://gw:8080")
    g.auth_config = kwargs.get("auth_config", {})
    return g


# ── Constants ──


class TestConstants:
    def test_consumer_group(self):
        assert CONSUMER_GROUP == "sync-engine"


# ── Lifecycle ──


class TestSyncEngineLifecycle:
    def test_initial_state(self):
        engine = SyncEngine()
        assert engine._running is False
        assert engine._consumer is None
        assert engine._thread is None
        assert engine._loop is None
        assert engine._semaphore is None

    async def test_stop_with_consumer(self):
        engine = SyncEngine()
        engine._running = True
        mock_consumer = MagicMock()
        engine._consumer = mock_consumer
        await engine.stop()
        assert engine._running is False
        mock_consumer.close.assert_called_once()

    async def test_stop_without_consumer(self):
        engine = SyncEngine()
        engine._running = True
        engine._consumer = None
        await engine.stop()
        assert engine._running is False


# ── _create_consumer ──


class TestCreateConsumer:
    def test_kafka_error_returns_none(self):
        engine = SyncEngine()
        from kafka.errors import KafkaError
        with patch("src.workers.sync_engine.KafkaConsumer", side_effect=KafkaError("refused")):
            result = engine._create_consumer()
            assert result is None

    def test_success_without_sasl(self):
        engine = SyncEngine()
        mock_kafka = MagicMock()
        with patch("src.workers.sync_engine.KafkaConsumer", return_value=mock_kafka):
            with patch("src.workers.sync_engine.settings") as mock_settings:
                mock_settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
                mock_settings.KAFKA_SASL_USERNAME = None
                result = engine._create_consumer()
                assert result is mock_kafka

    def test_success_with_sasl(self):
        engine = SyncEngine()
        mock_kafka = MagicMock()
        with patch("src.workers.sync_engine.KafkaConsumer", return_value=mock_kafka):
            with patch("src.workers.sync_engine.settings") as mock_settings:
                mock_settings.KAFKA_BOOTSTRAP_SERVERS = "kafka:9092"
                mock_settings.KAFKA_SASL_USERNAME = "user"
                mock_settings.KAFKA_SASL_PASSWORD = "pass"
                result = engine._create_consumer()
                assert result is mock_kafka


# ── _handle_sync_event ──


class TestHandleSyncEvent:
    def test_dispatches_reconcile_for_valid_event(self):
        engine = SyncEngine()
        engine._loop = MagicMock()
        dep_id = str(uuid4())
        message = MagicMock()
        message.value = {"payload": {"deployment_id": dep_id}}
        mock_future = MagicMock()

        with patch("asyncio.run_coroutine_threadsafe", return_value=mock_future):
            with patch.object(engine, "_reconcile_one", new_callable=AsyncMock):
                engine._handle_sync_event(message)
                mock_future.add_done_callback.assert_called_once()

    def test_logs_warning_missing_deployment_id(self):
        engine = SyncEngine()
        engine._loop = MagicMock()
        message = MagicMock()
        message.value = {"payload": {}}
        # Should return early without dispatching
        with patch("asyncio.run_coroutine_threadsafe") as mock_dispatch:
            engine._handle_sync_event(message)
            mock_dispatch.assert_not_called()

    def test_no_loop_skips_dispatch(self):
        engine = SyncEngine()
        engine._loop = None
        dep_id = str(uuid4())
        message = MagicMock()
        message.value = {"payload": {"deployment_id": dep_id}}
        with patch("asyncio.run_coroutine_threadsafe") as mock_dispatch:
            engine._handle_sync_event(message)
            mock_dispatch.assert_not_called()

    def test_exception_logs_error(self):
        engine = SyncEngine()
        engine._loop = MagicMock()
        message = MagicMock()
        message.value = None  # causes AttributeError on .get()
        # Should not raise
        engine._handle_sync_event(message)


# ── _reconcile_callback ──


class TestReconcileCallback:
    def test_no_exception_passes(self):
        future = MagicMock()
        future.result.return_value = None
        # Should not raise
        SyncEngine._reconcile_callback(future)
        future.result.assert_called_once()

    def test_exception_logs_error(self):
        future = MagicMock()
        future.result.side_effect = RuntimeError("db down")
        # Should not raise — swallowed
        SyncEngine._reconcile_callback(future)


# ── _consume_thread ──


class TestConsumeThread:
    def test_none_consumer_exits_early(self):
        engine = SyncEngine()
        engine._running = True
        with patch.object(engine, "_create_consumer", return_value=None):
            engine._consume_thread()
            # No exception — returned early

    def test_stops_when_not_running(self):
        engine = SyncEngine()
        engine._running = False
        mock_kafka = MagicMock()
        mock_kafka.poll.return_value = {}
        with patch.object(engine, "_create_consumer", return_value=mock_kafka):
            engine._consume_thread()
            mock_kafka.close.assert_called_once()


# ── _reconcile_all ──


class TestReconcileAll:
    async def test_empty_deployments_returns_early(self):
        engine = SyncEngine()
        session = _mock_session()
        mock_repo = AsyncMock()
        mock_repo.list_by_statuses = AsyncMock(return_value=[])

        with patch("src.workers.sync_engine._get_session_factory", _make_session_factory(session)):
            with patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo):
                # Should return without dispatching any tasks
                await engine._reconcile_all()

    async def test_filters_exceeded_retries(self):
        engine = SyncEngine()
        session = _mock_session()

        dep_ok = _mock_deployment(sync_status=DeploymentSyncStatus.PENDING, sync_attempts=0)
        dep_over = _mock_deployment(sync_status=DeploymentSyncStatus.ERROR, sync_attempts=10)

        mock_repo = AsyncMock()
        mock_repo.list_by_statuses = AsyncMock(return_value=[dep_ok, dep_over])

        reconciled = []

        async def fake_reconcile_one(dep_id):
            reconciled.append(dep_id)

        with patch("src.workers.sync_engine._get_session_factory", _make_session_factory(session)):
            with patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo):
                with patch("src.workers.sync_engine.settings") as mock_settings:
                    mock_settings.SYNC_ENGINE_RETRY_MAX = 3
                    with patch.object(engine, "_reconcile_one", side_effect=fake_reconcile_one):
                        await engine._reconcile_all()

        # Only dep_ok should be reconciled (dep_over exceeded retries)
        assert dep_ok.id in reconciled
        assert dep_over.id not in reconciled

    async def test_dispatches_all_actionable(self):
        engine = SyncEngine()
        session = _mock_session()

        dep1 = _mock_deployment(sync_status=DeploymentSyncStatus.PENDING, sync_attempts=0)
        dep2 = _mock_deployment(sync_status=DeploymentSyncStatus.DRIFTED, sync_attempts=0)

        mock_repo = AsyncMock()
        mock_repo.list_by_statuses = AsyncMock(return_value=[dep1, dep2])

        reconciled = []

        async def fake_reconcile_one(dep_id):
            reconciled.append(dep_id)

        with patch("src.workers.sync_engine._get_session_factory", _make_session_factory(session)):
            with patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_repo):
                with patch("src.workers.sync_engine.settings") as mock_settings:
                    mock_settings.SYNC_ENGINE_RETRY_MAX = 3
                    with patch.object(engine, "_reconcile_one", side_effect=fake_reconcile_one):
                        await engine._reconcile_all()

        assert dep1.id in reconciled
        assert dep2.id in reconciled


# ── _reconcile_one ──


class TestReconcileOne:
    async def test_deployment_not_found_returns_early(self):
        engine = SyncEngine()
        engine._semaphore = asyncio.Semaphore(5)
        session = _mock_session()

        mock_dep_repo = AsyncMock()
        mock_dep_repo.get_by_id = AsyncMock(return_value=None)
        mock_gw_repo = AsyncMock()

        with patch("src.workers.sync_engine._get_session_factory", _make_session_factory(session)):
            with patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_dep_repo):
                with patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo):
                    await engine._reconcile_one(uuid4())

        mock_dep_repo.update.assert_not_called()

    async def test_gateway_not_found_marks_error(self):
        engine = SyncEngine()
        engine._semaphore = asyncio.Semaphore(5)
        session = _mock_session()

        dep = _mock_deployment()
        mock_dep_repo = AsyncMock()
        mock_dep_repo.get_by_id = AsyncMock(return_value=dep)
        mock_dep_repo.update = AsyncMock()

        mock_gw_repo = AsyncMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=None)

        with patch("src.workers.sync_engine._get_session_factory", _make_session_factory(session)):
            with patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_dep_repo):
                with patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo):
                    await engine._reconcile_one(dep.id)

        assert dep.sync_status == DeploymentSyncStatus.ERROR
        mock_dep_repo.update.assert_called_once_with(dep)

    async def test_gateway_offline_skips(self):
        engine = SyncEngine()
        engine._semaphore = asyncio.Semaphore(5)
        session = _mock_session()

        dep = _mock_deployment()
        gw = _mock_gateway(status=GatewayInstanceStatus.OFFLINE)

        mock_dep_repo = AsyncMock()
        mock_dep_repo.get_by_id = AsyncMock(return_value=dep)
        mock_gw_repo = AsyncMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gw)

        with patch("src.workers.sync_engine._get_session_factory", _make_session_factory(session)):
            with patch("src.workers.sync_engine.GatewayDeploymentRepository", return_value=mock_dep_repo):
                with patch("src.workers.sync_engine.GatewayInstanceRepository", return_value=mock_gw_repo):
                    await engine._reconcile_one(dep.id)

        mock_dep_repo.update.assert_not_called()


# ── _handle_sync ──


class TestHandleSync:
    async def test_success_marks_synced(self):
        engine = SyncEngine()
        session = _mock_session()

        dep = _mock_deployment()
        repo = AsyncMock()
        repo.update = AsyncMock()

        adapter = AsyncMock()
        mock_result = MagicMock(success=True, data={"synced": True}, resource_id="res-1", error=None)
        adapter.sync_api = AsyncMock(return_value=mock_result)
        adapter.upsert_policy = AsyncMock()

        with patch("src.repositories.gateway_policy.GatewayPolicyRepository") as mock_policy_repo_cls:
            mock_policy_repo = AsyncMock()
            mock_policy_repo.get_policies_for_deployment = AsyncMock(return_value=[])
            mock_policy_repo_cls.return_value = mock_policy_repo
            await engine._handle_sync(dep, adapter, repo, session)

        assert dep.sync_status == DeploymentSyncStatus.SYNCED
        repo.update.assert_called()
        session.commit.assert_called()

    async def test_failure_marks_error(self):
        engine = SyncEngine()
        session = _mock_session()

        dep = _mock_deployment()
        repo = AsyncMock()
        repo.update = AsyncMock()

        adapter = AsyncMock()
        mock_result = MagicMock(success=False, data=None, resource_id=None, error="Gateway refused")
        adapter.sync_api = AsyncMock(return_value=mock_result)

        await engine._handle_sync(dep, adapter, repo, session)

        assert dep.sync_status == DeploymentSyncStatus.ERROR
        assert dep.sync_error == "Gateway refused"


# ── _handle_delete ──


class TestHandleDelete:
    async def test_success_deletes_deployment(self):
        engine = SyncEngine()
        session = _mock_session()

        dep = _mock_deployment()
        repo = AsyncMock()
        repo.delete = AsyncMock()

        adapter = AsyncMock()
        mock_result = MagicMock(success=True, error=None)
        adapter.delete_api = AsyncMock(return_value=mock_result)

        await engine._handle_delete(dep, adapter, repo, session)

        repo.delete.assert_called_once_with(dep)
        session.commit.assert_called()

    async def test_failure_marks_error(self):
        engine = SyncEngine()
        session = _mock_session()

        dep = _mock_deployment(sync_attempts=0)
        repo = AsyncMock()
        repo.update = AsyncMock()

        adapter = AsyncMock()
        mock_result = MagicMock(success=False, error="Delete refused")
        adapter.delete_api = AsyncMock(return_value=mock_result)

        await engine._handle_delete(dep, adapter, repo, session)

        assert dep.sync_error == "Delete refused"
        assert dep.sync_attempts == 1
        repo.update.assert_called_once_with(dep)


# ── _emit_drift_event ──


class TestEmitDriftEvent:
    async def test_success_publishes_event(self):
        engine = SyncEngine()
        dep = _mock_deployment()

        with patch("src.workers.sync_engine.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock()
            await engine._emit_drift_event(dep, "api_missing")
            mock_kafka.publish.assert_called_once()

    async def test_exception_is_swallowed(self):
        engine = SyncEngine()
        dep = _mock_deployment()

        with patch("src.workers.sync_engine.kafka_service") as mock_kafka:
            mock_kafka.publish = AsyncMock(side_effect=RuntimeError("Kafka down"))
            # Should not raise
            await engine._emit_drift_event(dep, "spec_hash_mismatch")
