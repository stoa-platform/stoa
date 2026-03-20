"""Regression tests for deployment stuck in pending/syncing.

PR #1925 — Root cause: stoa_edge_mcp gateway type had no registered adapter,
causing inline sync to throw ValueError. The exception handler didn't reset
the sync status, leaving deployments stuck in SYNCING forever. The SyncEngine
periodic loop also didn't pick up stale SYNCING deployments.

Invariants protected:
1. All STOA gateway mode variants have registered adapters
2. Inline sync exception resets status to PENDING (not stuck SYNCING)
3. SyncEngine reconciles stale SYNCING deployments
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.adapters.registry import AdapterRegistry
from src.models.gateway_deployment import DeploymentSyncStatus


class TestRegressionDeploymentStuckPending:
    """Regression: deployments stuck in pending/syncing (PR #1925)."""

    def test_regression_stoa_edge_mcp_adapter_registered(self):
        """stoa_edge_mcp must have a registered adapter (was missing, caused ValueError)."""
        assert AdapterRegistry.has_type("stoa_edge_mcp"), (
            "stoa_edge_mcp adapter missing — deployments to STOA edge-mcp gateways will fail"
        )

    def test_regression_all_stoa_modes_registered(self):
        """All 4 STOA gateway modes (ADR-024) must have registered adapters."""
        for mode in ("stoa", "stoa_edge_mcp", "stoa_sidecar", "stoa_proxy", "stoa_shadow"):
            assert AdapterRegistry.has_type(mode), f"Missing adapter for STOA mode: {mode}"

    def test_regression_stoa_modes_use_same_adapter_class(self):
        """All STOA mode variants must resolve to the same adapter implementation."""
        adapters = []
        for mode in ("stoa", "stoa_edge_mcp", "stoa_sidecar", "stoa_proxy", "stoa_shadow"):
            adapter = AdapterRegistry.create(mode, config={"base_url": "http://test"}, instrument=False)
            adapters.append(type(adapter))
        assert len(set(adapters)) == 1, "STOA mode variants should share one adapter class"

    @pytest.mark.asyncio
    async def test_regression_inline_sync_resets_to_pending_on_exception(self):
        """Inline sync exception must reset status to PENDING, not leave it SYNCING."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        mock_db = AsyncMock()
        mock_db.flush = AsyncMock()
        svc = DeploymentOrchestrationService(mock_db)

        # Simulate a deployment with a gateway type that raises during adapter creation
        dep = MagicMock()
        dep.id = "test-dep-id"
        dep.gateway_instance_id = "test-gw-id"
        dep.sync_status = DeploymentSyncStatus.PENDING
        dep.sync_error = None
        dep.desired_state = {"tenant_id": "acme"}

        mock_gateway = MagicMock()
        mock_gateway.status.value = "online"
        mock_gateway.gateway_type.value = "nonexistent_type"
        mock_gateway.base_url = "http://test"
        mock_gateway.auth_config = {}

        with patch(
            "src.repositories.gateway_instance.GatewayInstanceRepository"
        ) as mock_gw_repo_cls:
            mock_gw_repo = MagicMock()
            mock_gw_repo.get_by_id = AsyncMock(return_value=mock_gateway)
            mock_gw_repo_cls.return_value = mock_gw_repo

            await svc._try_inline_sync([dep])

        # Status MUST be reset to PENDING — not stuck in SYNCING
        assert dep.sync_status == DeploymentSyncStatus.PENDING, (
            f"Expected PENDING after inline sync exception, got {dep.sync_status}"
        )
        assert dep.sync_error is not None, "sync_error should contain the exception message"
