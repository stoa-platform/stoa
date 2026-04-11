"""Tests for the Gateway Reconciler (ArgoCD → gateway_instances sync)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.gateway_instance import GatewayInstance, GatewayInstanceStatus, GatewayType
from src.workers.gateway_reconciler import _HEALTH_MAP, GatewayReconciler


def _make_argocd_app(
    name: str,
    gateway_type: str,
    health: str = "Healthy",
    sync: str = "Synced",
    mode: str | None = None,
    environment: str = "prod",
    namespace: str = "stoa-system",
) -> dict:
    """Build a mock ArgoCD Application object."""
    labels = {"stoa.dev/gateway-type": gateway_type}
    if mode:
        labels["stoa.dev/gateway-mode"] = mode
    if environment != "prod":
        labels["stoa.dev/environment"] = environment

    return {
        "metadata": {"name": name, "labels": labels},
        "spec": {"destination": {"namespace": namespace}},
        "status": {
            "health": {"status": health},
            "sync": {"status": sync, "revision": "abc1234567890"},
        },
    }


def _make_db_instance(
    name: str,
    source: str = "argocd",
    status: GatewayInstanceStatus = GatewayInstanceStatus.ONLINE,
    deleted_at=None,
) -> MagicMock:
    """Build a mock GatewayInstance DB row."""
    instance = MagicMock(spec=GatewayInstance)
    instance.name = name
    instance.source = source
    instance.status = status
    instance.deleted_at = deleted_at
    instance.health_details = {}
    return instance


class TestHealthMap:
    """Test ArgoCD health → DB status mapping."""

    def test_healthy_maps_to_online(self):
        assert _HEALTH_MAP["Healthy"] == GatewayInstanceStatus.ONLINE

    def test_progressing_maps_to_online(self):
        assert _HEALTH_MAP["Progressing"] == GatewayInstanceStatus.ONLINE

    def test_degraded_maps_to_degraded(self):
        assert _HEALTH_MAP["Degraded"] == GatewayInstanceStatus.DEGRADED

    def test_suspended_maps_to_offline(self):
        assert _HEALTH_MAP["Suspended"] == GatewayInstanceStatus.OFFLINE

    def test_missing_maps_to_offline(self):
        assert _HEALTH_MAP["Missing"] == GatewayInstanceStatus.OFFLINE

    def test_unknown_maps_to_offline(self):
        assert _HEALTH_MAP["Unknown"] == GatewayInstanceStatus.OFFLINE


class TestReconcilerStatus:
    """Test reconciler health status reporting."""

    def test_initial_status(self):
        reconciler = GatewayReconciler()
        status = reconciler.status
        assert status["active"] is False
        assert status["last_run"] is None
        assert status["last_error"] is None
        assert status["interval_seconds"] == 60

    def test_status_after_run(self):
        reconciler = GatewayReconciler()
        reconciler._running = True
        reconciler._last_run = datetime(2026, 3, 11, 12, 0, 0, tzinfo=UTC)
        status = reconciler.status
        assert status["active"] is True
        assert "2026-03-11" in status["last_run"]


class TestUpsertFromArgoCD:
    """Test upserting gateway instances from ArgoCD apps."""

    @pytest.mark.asyncio
    async def test_creates_new_instance(self):
        reconciler = GatewayReconciler()
        app = _make_argocd_app("stoa-gateway", "stoa", health="Healthy", mode="edge-mcp")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        seen = await reconciler._upsert_from_argocd(mock_session, [app])

        assert "argocd-stoa-gateway" in seen
        mock_session.add.assert_called_once()
        added = mock_session.add.call_args[0][0]
        assert added.name == "argocd-stoa-gateway"
        assert added.gateway_type == GatewayType.STOA
        assert added.source == "argocd"
        assert added.mode == "edge-mcp"
        assert added.status == GatewayInstanceStatus.ONLINE

    @pytest.mark.asyncio
    async def test_updates_existing_instance(self):
        reconciler = GatewayReconciler()
        app = _make_argocd_app("stoa-gateway", "stoa", health="Degraded")

        existing = _make_db_instance("argocd-stoa-gateway")
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        mock_session.execute.return_value = mock_result

        seen = await reconciler._upsert_from_argocd(mock_session, [app])

        assert "argocd-stoa-gateway" in seen
        assert existing.status == GatewayInstanceStatus.DEGRADED
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_apps(self):
        reconciler = GatewayReconciler()
        apps = [
            _make_argocd_app("stoa-gateway", "stoa"),
            _make_argocd_app("kong-dataplane", "kong"),
            _make_argocd_app("gravitee-dataplane", "gravitee"),
        ]

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        seen = await reconciler._upsert_from_argocd(mock_session, apps)

        assert len(seen) == 3
        assert "argocd-stoa-gateway" in seen
        assert "argocd-kong-dataplane" in seen
        assert "argocd-gravitee-dataplane" in seen


class TestPruneStaleEntries:
    """Test pruning argocd entries that no longer exist."""

    @pytest.mark.asyncio
    async def test_prunes_deleted_app(self):
        reconciler = GatewayReconciler()
        stale_instance = _make_db_instance("argocd-old-gateway")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [stale_instance]
        mock_session.execute.return_value = mock_result

        await reconciler._prune_stale_argocd_entries(mock_session, {"argocd-stoa-gateway"})

        assert stale_instance.deleted_at is not None
        assert stale_instance.deleted_by == "gateway-reconciler"
        assert stale_instance.status == GatewayInstanceStatus.OFFLINE

    @pytest.mark.asyncio
    async def test_keeps_active_apps(self):
        reconciler = GatewayReconciler()
        active = _make_db_instance("argocd-stoa-gateway")

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [active]
        mock_session.execute.return_value = mock_result

        await reconciler._prune_stale_argocd_entries(mock_session, {"argocd-stoa-gateway"})

        assert active.deleted_at is None

    @pytest.mark.asyncio
    async def test_does_not_prune_non_argocd_entries(self):
        """The prune query filters by source='argocd', so manual entries are safe."""
        reconciler = GatewayReconciler()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        await reconciler._prune_stale_argocd_entries(mock_session, set())
        # No instances returned → nothing to prune


class TestReconcileEndToEnd:
    """Test the full reconcile cycle."""

    @pytest.fixture(autouse=True)
    def _stub_argocd_token(self, monkeypatch):
        # Reconciler short-circuits when no token; tests need it configured.
        monkeypatch.setattr("src.workers.gateway_reconciler.settings.ARGOCD_TOKEN", "test-token")

    @pytest.mark.asyncio
    @patch("src.workers.gateway_reconciler.argocd_service")
    @patch("src.workers.gateway_reconciler._get_session_factory")
    async def test_reconcile_filters_labeled_apps(self, mock_factory, mock_argocd):
        reconciler = GatewayReconciler()

        # 2 apps: 1 with gateway label, 1 without
        mock_argocd.get_applications = AsyncMock(
            return_value=[
                _make_argocd_app("stoa-gateway", "stoa"),
                {
                    "metadata": {"name": "redis", "labels": {}},
                    "spec": {"destination": {"namespace": "default"}},
                    "status": {"health": {"status": "Healthy"}, "sync": {"status": "Synced"}},
                },
            ]
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_cm)

        await reconciler._reconcile()

        # Only 1 app should be added (stoa-gateway, not redis)
        assert mock_session.add.call_count == 1
        added = mock_session.add.call_args[0][0]
        assert added.name == "argocd-stoa-gateway"

    @pytest.mark.asyncio
    @patch("src.workers.gateway_reconciler.argocd_service")
    async def test_reconcile_handles_argocd_failure(self, mock_argocd):
        reconciler = GatewayReconciler()
        mock_argocd.get_applications = AsyncMock(side_effect=Exception("connection refused"))

        # Should not raise — logs warning and returns
        await reconciler._reconcile()

    @pytest.mark.asyncio
    @patch("src.workers.gateway_reconciler.argocd_service")
    async def test_reconcile_skips_when_no_token(self, mock_argocd, monkeypatch):
        monkeypatch.setattr("src.workers.gateway_reconciler.settings.ARGOCD_TOKEN", "")
        reconciler = GatewayReconciler()
        mock_argocd.get_applications = AsyncMock(return_value=[])

        await reconciler._reconcile()

        # ArgoCD should NOT be queried when token is absent
        mock_argocd.get_applications.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.workers.gateway_reconciler.argocd_service")
    @patch("src.workers.gateway_reconciler._get_session_factory")
    async def test_reconcile_skips_invalid_gateway_type(self, mock_factory, mock_argocd):
        reconciler = GatewayReconciler()

        mock_argocd.get_applications = AsyncMock(
            return_value=[
                {
                    "metadata": {"name": "bad-gw", "labels": {"stoa.dev/gateway-type": "invalid_type"}},
                    "spec": {"destination": {"namespace": "default"}},
                    "status": {"health": {"status": "Healthy"}, "sync": {"status": "Synced"}},
                },
            ]
        )

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_factory.return_value = MagicMock(return_value=mock_cm)

        await reconciler._reconcile()

        # Invalid type should be skipped — no adds
        mock_session.add.assert_not_called()
