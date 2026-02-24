"""Tests for DataGovernanceService — Wave 2

Covers: governance matrix, drift report, reconciliation, drift status computation.

Strategy:
  - Mock AsyncSession with chained execute().scalar()/scalars().all() patterns
  - Test all 3 entity types: api_catalog, mcp_servers, gateway_deployments
  - Test matrix aggregation, drift detail, reconciliation (dry_run + real)
  - Test drift status computation edge cases
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# Shared mock DB helpers


def _mock_scalar(value):
    """Create a mock execute result that returns a scalar value."""
    result = MagicMock()
    result.scalar.return_value = value
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_all(items):
    """Create a mock execute result that returns scalars().all()."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = items
    result.scalars.return_value = scalars_mock
    return result


def _mock_fetchall(rows):
    """Create a mock execute result that returns fetchall()."""
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


# ── Drift Status Computation ─────────────────────────────────────────


class TestComputeDriftStatus:
    """Unit tests for _compute_drift_status static method."""

    def test_errors_return_error(self):
        from src.services.data_governance_service import DataGovernanceService

        result = DataGovernanceService._compute_drift_status(
            {"total": 10, "drifted": 2, "errors": 1}
        )
        assert result.value == "error"

    def test_drifted_returns_drifted(self):
        from src.services.data_governance_service import DataGovernanceService

        result = DataGovernanceService._compute_drift_status(
            {"total": 10, "drifted": 3, "errors": 0}
        )
        assert result.value == "drifted"

    def test_zero_total_returns_unknown(self):
        from src.services.data_governance_service import DataGovernanceService

        result = DataGovernanceService._compute_drift_status(
            {"total": 0, "drifted": 0, "errors": 0}
        )
        assert result.value == "unknown"

    def test_all_clean_returns_clean(self):
        from src.services.data_governance_service import DataGovernanceService

        result = DataGovernanceService._compute_drift_status(
            {"total": 10, "drifted": 0, "errors": 0}
        )
        assert result.value == "clean"

    def test_errors_take_priority_over_drifted(self):
        from src.services.data_governance_service import DataGovernanceService

        result = DataGovernanceService._compute_drift_status(
            {"total": 10, "drifted": 5, "errors": 2}
        )
        assert result.value == "error"


# ── Entity Counts ─────────────────────────────────────────────────────


class TestEntityCounts:
    """Unit tests for _entity_counts dispatching."""

    @pytest.mark.asyncio
    async def test_api_catalog_counts(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        now = datetime.now(UTC)
        # 3 execute calls: total, stale (drifted), last_sync
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar(25),  # total count
                _mock_scalar(3),  # stale/drifted count
                _mock_scalar(now),  # last_sync_at
            ]
        )

        svc = DataGovernanceService(db)
        counts = await svc._entity_counts("api_catalog")

        assert counts["total"] == 25
        assert counts["drifted"] == 3
        assert counts["errors"] == 0
        assert counts["last_sync_at"] == now

    @pytest.mark.asyncio
    async def test_mcp_server_counts(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        now = datetime.now(UTC)
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar(15),  # total
                _mock_scalar(2),  # orphan (drifted)
                _mock_scalar(1),  # error
                _mock_scalar(now),  # last_sync
            ]
        )

        svc = DataGovernanceService(db)
        counts = await svc._entity_counts("mcp_servers")

        assert counts["total"] == 15
        assert counts["drifted"] == 2
        assert counts["errors"] == 1
        assert counts["last_sync_at"] == now

    @pytest.mark.asyncio
    async def test_gateway_deployment_counts(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        now = datetime.now(UTC)
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar(8),  # total
                _mock_scalar(1),  # drifted
                _mock_scalar(0),  # error
                _mock_scalar(now),  # last_sync
            ]
        )

        svc = DataGovernanceService(db)
        counts = await svc._entity_counts("gateway_deployments")

        assert counts["total"] == 8
        assert counts["drifted"] == 1
        assert counts["errors"] == 0

    @pytest.mark.asyncio
    async def test_unknown_entity_type_returns_zeros(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        svc = DataGovernanceService(db)
        counts = await svc._entity_counts("nonexistent")

        assert counts["total"] == 0
        assert counts["drifted"] == 0
        assert counts["errors"] == 0

    @pytest.mark.asyncio
    async def test_null_scalars_default_to_zero(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar(None),  # total → 0
                _mock_scalar(None),  # stale → 0
                _mock_scalar(None),  # last_sync → None
            ]
        )

        svc = DataGovernanceService(db)
        counts = await svc._entity_counts("api_catalog")

        assert counts["total"] == 0
        assert counts["drifted"] == 0


# ── Governance Matrix ─────────────────────────────────────────────────


class TestGovernanceMatrix:
    """Unit tests for get_governance_matrix()."""

    @pytest.mark.asyncio
    async def test_matrix_returns_3_entities(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        now = datetime.now(UTC)
        # 3 entities x 3-4 queries each = 10 execute calls
        db.execute = AsyncMock(
            side_effect=[
                # api_catalog: total, stale, last_sync
                _mock_scalar(20),
                _mock_scalar(2),
                _mock_scalar(now),
                # mcp_servers: total, orphan, error, last_sync
                _mock_scalar(10),
                _mock_scalar(1),
                _mock_scalar(0),
                _mock_scalar(now),
                # gateway_deployments: total, drifted, error, last_sync
                _mock_scalar(5),
                _mock_scalar(0),
                _mock_scalar(0),
                _mock_scalar(now),
            ]
        )

        svc = DataGovernanceService(db)
        result = await svc.get_governance_matrix()

        assert len(result.entities) == 3
        assert result.summary.total_entity_types == 3
        assert result.summary.total_items == 35  # 20 + 10 + 5
        assert result.summary.total_drifted == 3  # 2 + 1 + 0
        assert result.summary.total_errors == 0

    @pytest.mark.asyncio
    async def test_matrix_health_pct_100_when_no_drift(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar(10), _mock_scalar(0), _mock_scalar(None),
                _mock_scalar(5), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
                _mock_scalar(3), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
            ]
        )

        svc = DataGovernanceService(db)
        result = await svc.get_governance_matrix()

        assert result.summary.health_pct == 100.0

    @pytest.mark.asyncio
    async def test_matrix_health_pct_with_drift(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar(10), _mock_scalar(5), _mock_scalar(None),  # 50% drifted
                _mock_scalar(0), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
                _mock_scalar(0), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
            ]
        )

        svc = DataGovernanceService(db)
        result = await svc.get_governance_matrix()

        assert result.summary.health_pct == 50.0

    @pytest.mark.asyncio
    async def test_matrix_health_pct_100_when_zero_items(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
                _mock_scalar(0), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
                _mock_scalar(0), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
            ]
        )

        svc = DataGovernanceService(db)
        result = await svc.get_governance_matrix()

        assert result.summary.health_pct == 100.0

    @pytest.mark.asyncio
    async def test_matrix_entity_metadata(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                _mock_scalar(1), _mock_scalar(0), _mock_scalar(None),
                _mock_scalar(1), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
                _mock_scalar(1), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
            ]
        )

        svc = DataGovernanceService(db)
        result = await svc.get_governance_matrix()

        api_entity = next(e for e in result.entities if e.entity_type == "api_catalog")
        assert api_entity.source_of_truth.value == "git"
        assert api_entity.sync_direction.value == "git\u2192db"
        assert api_entity.drift_detection is True

        gw_entity = next(e for e in result.entities if e.entity_type == "gateway_deployments")
        assert gw_entity.source_of_truth.value == "hybrid"


# ── Drift Report ──────────────────────────────────────────────────────


class TestDriftReport:
    """Unit tests for get_drift_report()."""

    @pytest.mark.asyncio
    async def test_drift_report_aggregates_all_entities(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()

        # Row mocks for fetchall
        api_row = MagicMock()
        api_row.api_id = "api-1"
        api_row.api_name = "Weather API"
        api_row.synced_at = None

        mcp_row = MagicMock()
        mcp_row.name = "mcp-1"
        mcp_row.display_name = "MCP Server 1"
        mcp_row.sync_status = MagicMock()
        mcp_row.sync_status.__eq__ = lambda _s, o: str(o) == "MCPServerSyncStatus.ORPHAN"
        mcp_row.sync_status.value = "orphan"
        mcp_row.sync_error = None
        mcp_row.last_synced_at = None

        # Need to patch the enum comparison properly
        from src.models.mcp_subscription import MCPServerSyncStatus

        mcp_row.sync_status = MCPServerSyncStatus.ORPHAN

        gw_row = MagicMock()
        gw_row.id = "gw-deploy-1"
        gw_row.sync_status = MagicMock()
        gw_row.sync_error = "timeout"
        gw_row.last_sync_attempt = None

        from src.models.gateway_deployment import DeploymentSyncStatus

        gw_row.sync_status = DeploymentSyncStatus.ERROR

        db.execute = AsyncMock(
            side_effect=[
                # api_catalog counts + drift items
                _mock_scalar(10), _mock_scalar(1), _mock_scalar(None),
                _mock_fetchall([api_row]),
                # mcp_servers counts + drift items
                _mock_scalar(5), _mock_scalar(1), _mock_scalar(0), _mock_scalar(None),
                _mock_fetchall([mcp_row]),
                # gateway_deployments counts + drift items
                _mock_scalar(3), _mock_scalar(0), _mock_scalar(1), _mock_scalar(None),
                _mock_fetchall([gw_row]),
            ]
        )

        svc = DataGovernanceService(db)
        result = await svc.get_drift_report()

        assert result.total_entities == 3
        # drifted counts = api(1 drifted + 0 errors) + mcp(1 orphan + 0 errors) + gw(0 drifted + 1 error)
        assert result.total_drifted == 3
        assert len(result.entities) == 3

    @pytest.mark.asyncio
    async def test_drift_report_no_drift(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=[
                # api_catalog: total, stale, last_sync, drift_items
                _mock_scalar(10), _mock_scalar(0), _mock_scalar(None),
                _mock_fetchall([]),
                # mcp_servers: total, orphan, error, last_sync, drift_items
                _mock_scalar(5), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
                _mock_fetchall([]),
                # gateway_deployments: total, drifted, error, last_sync, drift_items
                _mock_scalar(3), _mock_scalar(0), _mock_scalar(0), _mock_scalar(None),
                _mock_fetchall([]),
            ]
        )

        svc = DataGovernanceService(db)
        result = await svc.get_drift_report()

        assert result.total_drifted == 0
        for entity in result.entities:
            assert entity.drifted == 0
            assert len(entity.items) == 0


# ── Reconciliation ────────────────────────────────────────────────────


class TestReconciliation:
    """Unit tests for reconcile()."""

    @pytest.mark.asyncio
    async def test_reconcile_api_catalog_dry_run(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        row = MagicMock()
        row.api_id = "api-1"
        row.api_name = "Test API"
        row.synced_at = None

        db.execute = AsyncMock(return_value=_mock_fetchall([row]))

        svc = DataGovernanceService(db)
        result = await svc.reconcile("api_catalog", dry_run=True)

        assert len(result.results) == 1
        r = result.results[0]
        assert r.entity_type == "api_catalog"
        assert r.action == "mark_for_resync"
        assert r.items_reconciled == 1
        assert r.dry_run is True

    @pytest.mark.asyncio
    async def test_reconcile_api_catalog_real(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        row = MagicMock()
        row.api_id = "api-1"
        row.api_name = "Test API"
        row.synced_at = None

        db.execute = AsyncMock(return_value=_mock_fetchall([row]))

        svc = DataGovernanceService(db)
        result = await svc.reconcile("api_catalog", dry_run=False)

        r = result.results[0]
        assert r.dry_run is False
        assert r.items_reconciled == 1

    @pytest.mark.asyncio
    async def test_reconcile_mcp_servers_dry_run(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()

        from src.models.mcp_subscription import MCPServerSyncStatus

        row = MagicMock()
        row.name = "mcp-1"
        row.display_name = "MCP 1"
        row.sync_status = MCPServerSyncStatus.ORPHAN
        row.sync_error = None
        row.last_synced_at = None

        db.execute = AsyncMock(return_value=_mock_fetchall([row]))

        svc = DataGovernanceService(db)
        result = await svc.reconcile("mcp_servers", dry_run=True)

        r = result.results[0]
        assert r.entity_type == "mcp_servers"
        assert r.action == "reset_to_pending"
        assert r.items_reconciled == 1
        assert r.dry_run is True

    @pytest.mark.asyncio
    async def test_reconcile_mcp_servers_real(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()

        from src.models.mcp_subscription import MCPServerSyncStatus

        row = MagicMock()
        row.name = "mcp-1"
        row.display_name = "MCP 1"
        row.sync_status = MCPServerSyncStatus.ORPHAN
        row.sync_error = None
        row.last_synced_at = None

        # Mock for drift items query
        drift_result = _mock_fetchall([row])
        # Mock for reconcile select (find server by name)
        server_mock = MagicMock()
        server_mock.sync_status = MCPServerSyncStatus.ORPHAN
        server_mock.sync_error = "old error"
        server_result = _mock_scalar(server_mock)

        db.execute = AsyncMock(side_effect=[drift_result, server_result])
        db.commit = AsyncMock()

        svc = DataGovernanceService(db)
        result = await svc.reconcile("mcp_servers", dry_run=False)

        r = result.results[0]
        assert r.dry_run is False
        assert r.items_reconciled == 1
        assert server_mock.sync_status == MCPServerSyncStatus.PENDING
        assert server_mock.sync_error is None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconcile_gateway_deployments_dry_run(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()

        from src.models.gateway_deployment import DeploymentSyncStatus

        row = MagicMock()
        row.id = "gw-1"
        row.sync_status = DeploymentSyncStatus.DRIFTED
        row.sync_error = None
        row.last_sync_attempt = None

        db.execute = AsyncMock(return_value=_mock_fetchall([row]))

        svc = DataGovernanceService(db)
        result = await svc.reconcile("gateway_deployments", dry_run=True)

        r = result.results[0]
        assert r.entity_type == "gateway_deployments"
        assert r.action == "reset_to_pending"
        assert r.dry_run is True

    @pytest.mark.asyncio
    async def test_reconcile_gateway_deployments_real(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()

        from src.models.gateway_deployment import DeploymentSyncStatus

        row = MagicMock()
        row.id = "gw-1"
        row.sync_status = DeploymentSyncStatus.DRIFTED
        row.sync_error = None
        row.last_sync_attempt = None

        deploy_mock = MagicMock()
        deploy_mock.sync_status = DeploymentSyncStatus.DRIFTED
        deploy_mock.sync_error = "old error"

        db.execute = AsyncMock(
            side_effect=[_mock_fetchall([row]), _mock_scalar(deploy_mock)]
        )
        db.commit = AsyncMock()

        svc = DataGovernanceService(db)
        result = await svc.reconcile("gateway_deployments", dry_run=False)

        r = result.results[0]
        assert r.dry_run is False
        assert r.items_reconciled == 1
        assert deploy_mock.sync_status == DeploymentSyncStatus.PENDING
        assert deploy_mock.sync_error is None

    @pytest.mark.asyncio
    async def test_reconcile_unknown_entity_type(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        svc = DataGovernanceService(db)
        result = await svc.reconcile("invalid_type", dry_run=True)

        r = result.results[0]
        assert r.entity_type == "invalid_type"
        assert r.action == "none"
        assert r.items_reconciled == 0
        assert "Unknown entity type" in r.errors[0]

    @pytest.mark.asyncio
    async def test_reconcile_mcp_real_with_exception(self):
        """When a DB exception occurs during reconciliation, it's captured in errors."""
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()

        from src.models.mcp_subscription import MCPServerSyncStatus

        row = MagicMock()
        row.name = "mcp-1"
        row.display_name = "MCP 1"
        row.sync_status = MCPServerSyncStatus.ERROR
        row.sync_error = "connection timeout"
        row.last_synced_at = None

        # drift items returns 1 item, but the reconcile select throws
        db.execute = AsyncMock(
            side_effect=[
                _mock_fetchall([row]),
                Exception("DB connection lost"),
            ]
        )

        svc = DataGovernanceService(db)
        result = await svc.reconcile("mcp_servers", dry_run=False)

        r = result.results[0]
        assert r.items_reconciled == 0
        assert len(r.errors) == 1
        assert "mcp-1" in r.errors[0]

    @pytest.mark.asyncio
    async def test_reconcile_empty_drift_items(self):
        """No drifted items means reconcile does nothing."""
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        db.execute = AsyncMock(return_value=_mock_fetchall([]))

        svc = DataGovernanceService(db)
        result = await svc.reconcile("api_catalog", dry_run=True)

        r = result.results[0]
        assert r.items_reconciled == 0


# ── Drift Items ───────────────────────────────────────────────────────


class TestDriftItems:
    """Unit tests for _get_drift_items and entity-specific drift item queries."""

    @pytest.mark.asyncio
    async def test_api_catalog_drift_items(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        row = MagicMock()
        row.api_id = "api-weather"
        row.api_name = "Weather API"
        row.synced_at = None

        db.execute = AsyncMock(return_value=_mock_fetchall([row]))

        svc = DataGovernanceService(db)
        items = await svc._api_catalog_drift_items()

        assert len(items) == 1
        assert items[0].entity_id == "api-weather"
        assert items[0].drift_type == "stale"
        assert "Never synced" in items[0].detail

    @pytest.mark.asyncio
    async def test_mcp_server_drift_items_orphan(self):
        from src.models.mcp_subscription import MCPServerSyncStatus
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        row = MagicMock()
        row.name = "mcp-openai"
        row.display_name = "OpenAI MCP"
        row.sync_status = MCPServerSyncStatus.ORPHAN
        row.sync_error = None
        row.last_synced_at = None

        db.execute = AsyncMock(return_value=_mock_fetchall([row]))

        svc = DataGovernanceService(db)
        items = await svc._mcp_server_drift_items()

        assert len(items) == 1
        assert items[0].entity_id == "mcp-openai"
        assert items[0].drift_type == "orphan"

    @pytest.mark.asyncio
    async def test_mcp_server_drift_items_error(self):
        from src.models.mcp_subscription import MCPServerSyncStatus
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        row = MagicMock()
        row.name = "mcp-broken"
        row.display_name = "Broken MCP"
        row.sync_status = MCPServerSyncStatus.ERROR
        row.sync_error = "Connection refused"
        row.last_synced_at = None

        db.execute = AsyncMock(return_value=_mock_fetchall([row]))

        svc = DataGovernanceService(db)
        items = await svc._mcp_server_drift_items()

        assert items[0].drift_type == "error"
        assert items[0].detail == "Connection refused"

    @pytest.mark.asyncio
    async def test_gateway_deployment_drift_items(self):
        from src.models.gateway_deployment import DeploymentSyncStatus
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        row = MagicMock()
        row.id = "550e8400-e29b-41d4-a716-446655440000"
        row.sync_status = DeploymentSyncStatus.DRIFTED
        row.sync_error = None
        row.last_sync_attempt = None

        db.execute = AsyncMock(return_value=_mock_fetchall([row]))

        svc = DataGovernanceService(db)
        items = await svc._gateway_deployment_drift_items()

        assert len(items) == 1
        assert items[0].drift_type == "desync"
        assert items[0].entity_name.startswith("deployment-")

    @pytest.mark.asyncio
    async def test_get_drift_items_unknown_type(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        svc = DataGovernanceService(db)
        items = await svc._get_drift_items("nonexistent")
        assert items == []

    @pytest.mark.asyncio
    async def test_api_catalog_drift_item_uses_api_id_as_name_fallback(self):
        from src.services.data_governance_service import DataGovernanceService

        db = AsyncMock()
        row = MagicMock()
        row.api_id = "api-no-name"
        row.api_name = None
        row.synced_at = None

        db.execute = AsyncMock(return_value=_mock_fetchall([row]))

        svc = DataGovernanceService(db)
        items = await svc._api_catalog_drift_items()

        assert items[0].entity_name == "api-no-name"
