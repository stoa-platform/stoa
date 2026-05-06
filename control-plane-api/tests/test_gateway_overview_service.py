"""Tests for Gateway Overview read-model."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.models.gateway_deployment import DeploymentSyncStatus, PolicySyncStatus
from src.models.gateway_instance import GatewayInstanceStatus, GatewayType
from src.models.gateway_policy import PolicyType
from src.schemas.gateway_overview import (
    GatewayOverviewMetricsStatus,
    GatewayOverviewRuntimeFreshness,
    GatewayOverviewRuntimeStatus,
    GatewayOverviewSyncStatus,
)
from src.services.gateway_overview_service import GatewayOverviewService

NOW = datetime(2026, 5, 4, 10, 22, 18, tzinfo=UTC)


def _user(roles=None, tenant_id=None):
    return SimpleNamespace(roles=roles or ["cpi-admin"], tenant_id=tenant_id)


def _gateway(**overrides):
    defaults = {
        "id": uuid4(),
        "name": "stoa-gateway-dev-edge-mcp-dev",
        "display_name": "STOA Gateway Dev",
        "gateway_type": GatewayType.STOA_EDGE_MCP,
        "environment": "dev",
        "tenant_id": None,
        "status": GatewayInstanceStatus.ONLINE,
        "mode": "edge-mcp",
        "version": "0.9.21",
        "visibility": None,
        "last_health_check": NOW - timedelta(seconds=18),
        "health_details": {
            "last_heartbeat": (NOW - timedelta(seconds=18)).isoformat(),
            "uptime_seconds": 3600,
            "routes_count": 2,
            "policies_count": 1,
            "discovered_apis_count": 5,
            "requests_total": 100,
            "error_rate": 0.01,
        },
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _catalog(**overrides):
    defaults = {
        "id": uuid4(),
        "tenant_id": "acme",
        "api_id": "users-api",
        "api_name": "Users API",
        "version": "1.4.2",
        "git_path": "tenants/acme/apis/users-api",
        "git_commit_sha": "abc123",
        "synced_at": NOW - timedelta(minutes=2),
        "api_metadata": {"backend_url": "https://users.internal"},
        "openapi_spec": {
            "paths": {
                "/v1/users": {"get": {}, "post": {}},
            }
        },
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _deployment(catalog_id, gateway_id, **overrides):
    defaults = {
        "id": uuid4(),
        "api_catalog_id": catalog_id,
        "gateway_instance_id": gateway_id,
        "desired_state": {
            "spec_hash": "sha256:users",
            "api_name": "Users API",
            "backend_url": "https://users.internal",
            "methods": ["GET", "POST"],
        },
        "actual_state": None,
        "actual_at": NOW - timedelta(minutes=1),
        "sync_status": DeploymentSyncStatus.SYNCED,
        "policy_sync_status": PolicySyncStatus.SYNCED,
        "policy_sync_error": None,
        "last_sync_success": NOW - timedelta(minutes=1),
        "last_sync_attempt": NOW - timedelta(minutes=1),
        "sync_error": None,
        "sync_steps": [],
        "desired_generation": 3,
        "synced_generation": 3,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _policy(**overrides):
    defaults = {
        "id": uuid4(),
        "name": "default-rate-limit",
        "policy_type": PolicyType.RATE_LIMIT,
        "tenant_id": None,
        "enabled": True,
        "priority": 100,
        "config": {"requests_per_minute": 1000},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _binding(**overrides):
    defaults = {
        "id": uuid4(),
        "policy_id": uuid4(),
        "api_catalog_id": None,
        "gateway_instance_id": None,
        "tenant_id": None,
        "enabled": True,
        "created_at": NOW,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _svc(mock_db_session, gateway, api_rows=None, policy_rows=None):
    svc = GatewayOverviewService(mock_db_session, now_fn=lambda: NOW)
    svc._load_gateway = AsyncMock(return_value=gateway)
    svc._load_api_rows = AsyncMock(return_value=api_rows or [])
    svc._load_policy_rows = AsyncMock(return_value=policy_rows or [])
    return svc


@pytest.mark.asyncio
async def test_gateway_without_apis(mock_db_session):
    svc = _svc(mock_db_session, _gateway(), api_rows=[], policy_rows=[])

    overview = await svc.get_overview(uuid4(), _user())

    assert overview.summary.apis_count == 0
    assert overview.summary.expected_routes_count == 0
    assert overview.sync.status == GatewayOverviewSyncStatus.IN_SYNC


@pytest.mark.asyncio
async def test_gateway_with_multiple_apis(mock_db_session):
    gw = _gateway()
    cat1 = _catalog()
    cat2 = _catalog(
        id=uuid4(),
        tenant_id="beta",
        api_id="orders-api",
        api_name="Orders API",
        openapi_spec={"paths": {"/v1/orders": {"get": {}}}},
    )
    dep1 = _deployment(cat1.id, gw.id)
    dep2 = _deployment(cat2.id, gw.id)
    svc = _svc(mock_db_session, gw, api_rows=[(dep1, cat1), (dep2, cat2)])

    overview = await svc.get_overview(gw.id, _user())

    assert overview.summary.apis_count == 2
    assert overview.summary.expected_routes_count == 3
    assert [api.name for api in overview.resolved_config.apis] == ["Users API", "Orders API"]


@pytest.mark.asyncio
async def test_tenant_admin_gets_filtered_visibility(mock_db_session):
    gw = _gateway()
    cat = _catalog(tenant_id="acme")
    dep = _deployment(cat.id, gw.id)
    svc = _svc(mock_db_session, gw, api_rows=[(dep, cat)])

    overview = await svc.get_overview(gw.id, _user(["tenant-admin"], tenant_id="acme"))

    assert overview.visibility.rbac_scope == "tenant"
    assert overview.visibility.tenant_id == "acme"
    assert overview.visibility.filtered is True
    svc._load_api_rows.assert_awaited_once_with(gw.id, "acme")


@pytest.mark.asyncio
async def test_tenant_level_policy_is_applicable(mock_db_session):
    gw = _gateway()
    cat = _catalog()
    dep = _deployment(cat.id, gw.id)
    pol = _policy()
    bind = _binding(policy_id=pol.id, tenant_id="acme")
    svc = _svc(mock_db_session, gw, api_rows=[(dep, cat)], policy_rows=[(pol, bind)])

    overview = await svc.get_overview(gw.id, _user())

    assert overview.summary.effective_policies_count == 1
    assert overview.resolved_config.apis[0].policies_count == 1
    assert overview.resolved_config.policies[0].source_binding.scope == "tenant"


@pytest.mark.asyncio
async def test_api_level_policy_priority_is_preserved(mock_db_session):
    gw = _gateway()
    cat = _catalog()
    dep = _deployment(cat.id, gw.id)
    gateway_policy = _policy(name="gateway-policy", priority=100)
    api_policy = _policy(name="api-policy", priority=10)
    rows = [
        (gateway_policy, _binding(policy_id=gateway_policy.id, gateway_instance_id=gw.id)),
        (api_policy, _binding(policy_id=api_policy.id, api_catalog_id=cat.id, gateway_instance_id=gw.id)),
    ]
    svc = _svc(mock_db_session, gw, api_rows=[(dep, cat)], policy_rows=rows)

    overview = await svc.get_overview(gw.id, _user())

    assert [policy.name for policy in overview.resolved_config.policies] == ["api-policy", "gateway-policy"]
    assert overview.resolved_config.apis[0].policies_count == 2


@pytest.mark.asyncio
async def test_disabled_policy_is_excluded(mock_db_session):
    gw = _gateway()
    cat = _catalog()
    dep = _deployment(cat.id, gw.id)
    disabled = _policy(enabled=False)
    bind = _binding(policy_id=disabled.id, gateway_instance_id=gw.id)
    svc = _svc(mock_db_session, gw, api_rows=[(dep, cat)], policy_rows=[(disabled, bind)])

    overview = await svc.get_overview(gw.id, _user())

    assert overview.summary.effective_policies_count == 0
    assert overview.resolved_config.policies == []


@pytest.mark.asyncio
async def test_failed_policy_sync_is_reported(mock_db_session):
    gw = _gateway()
    cat = _catalog()
    dep = _deployment(
        cat.id,
        gw.id,
        policy_sync_status=PolicySyncStatus.ERROR,
        policy_sync_error="policy apply failed",
    )
    pol = _policy()
    bind = _binding(policy_id=pol.id, gateway_instance_id=gw.id)
    svc = _svc(mock_db_session, gw, api_rows=[(dep, cat)], policy_rows=[(pol, bind)])

    overview = await svc.get_overview(gw.id, _user())

    assert overview.summary.failed_policies_count == 1
    assert overview.resolved_config.policies[0].sync_status == GatewayOverviewSyncStatus.FAILED


@pytest.mark.asyncio
async def test_fresh_heartbeat(mock_db_session):
    svc = _svc(mock_db_session, _gateway())

    overview = await svc.get_overview(uuid4(), _user())

    assert overview.runtime.status == GatewayOverviewRuntimeStatus.HEALTHY
    assert overview.runtime.heartbeat_age_seconds == 18
    assert overview.data_quality.runtime_freshness == GatewayOverviewRuntimeFreshness.FRESH


@pytest.mark.asyncio
async def test_stale_heartbeat(mock_db_session):
    old = NOW - timedelta(seconds=120)
    gw = _gateway(last_health_check=old, health_details={"last_heartbeat": old.isoformat()})
    svc = _svc(mock_db_session, gw)

    overview = await svc.get_overview(gw.id, _user())

    assert overview.runtime.status == GatewayOverviewRuntimeStatus.STALE
    assert overview.data_quality.runtime_freshness == GatewayOverviewRuntimeFreshness.STALE
    assert overview.data_quality.warnings[0].code == "runtime_heartbeat_stale"


@pytest.mark.asyncio
async def test_runtime_absent_uses_null_not_zero(mock_db_session):
    gw = _gateway(
        status=GatewayInstanceStatus.OFFLINE,
        last_health_check=None,
        health_details=None,
    )
    svc = _svc(mock_db_session, gw)

    overview = await svc.get_overview(gw.id, _user())

    assert overview.runtime.status == GatewayOverviewRuntimeStatus.OFFLINE
    assert overview.runtime.reported_routes_count is None
    assert overview.summary.reported_routes_count is None
    assert overview.data_quality.runtime_freshness == GatewayOverviewRuntimeFreshness.MISSING


@pytest.mark.asyncio
async def test_metrics_partial(mock_db_session):
    gw = _gateway(health_details={"last_heartbeat": (NOW - timedelta(seconds=10)).isoformat(), "requests_total": 42})
    svc = _svc(mock_db_session, gw)

    overview = await svc.get_overview(gw.id, _user())

    assert overview.summary.metrics_status == GatewayOverviewMetricsStatus.PARTIAL
    assert any(w.code == "runtime_metrics_partial" for w in overview.data_quality.warnings)


@pytest.mark.asyncio
async def test_redacts_sensitive_values(mock_db_session):
    gw = _gateway()
    cat = _catalog(api_metadata={"backend_url": "https://user:pass@users.internal/v1?token=abc"})
    dep = _deployment(
        cat.id,
        gw.id,
        desired_state={
            "spec_hash": "sha256:redacted",
            "backend_url": "https://user:pass@users.internal/v1?token=abc",
        },
    )
    pol = _policy(
        policy_type=PolicyType.JWT_VALIDATION,
        config={"client_secret": "super-secret", "authorization": "Bearer abc"},
    )
    bind = _binding(policy_id=pol.id, gateway_instance_id=gw.id)
    svc = _svc(mock_db_session, gw, api_rows=[(dep, cat)], policy_rows=[(pol, bind)])

    overview = await svc.get_overview(gw.id, _user())
    rendered = overview.model_dump_json()

    assert "super-secret" not in rendered
    assert "Bearer abc" not in rendered
    assert "user:pass" not in rendered
    assert "token=abc" not in rendered


@pytest.mark.asyncio
async def test_drift_desired_vs_actual(mock_db_session):
    gw = _gateway()
    cat = _catalog()
    dep = _deployment(
        cat.id,
        gw.id,
        sync_status=DeploymentSyncStatus.DRIFTED,
        desired_generation=4,
        synced_generation=3,
    )
    svc = _svc(mock_db_session, gw, api_rows=[(dep, cat)])

    overview = await svc.get_overview(gw.id, _user())

    assert overview.summary.sync_status == GatewayOverviewSyncStatus.DRIFT
    assert overview.sync.drift is True


def test_gateway_overview_router(app_with_cpi_admin):
    overview = {
        "schema_version": "1.0",
        "generated_at": NOW.isoformat(),
        "gateway": {
            "id": str(uuid4()),
            "name": "gw",
            "display_name": "Gateway",
            "gateway_type": "stoa_edge_mcp",
            "environment": "dev",
            "status": "online",
            "mode": "edge-mcp",
            "version": "0.9.21",
        },
        "visibility": {"rbac_scope": "admin", "tenant_id": None, "filtered": False},
        "source": {"control_plane_revision": None, "last_loaded_at": None},
        "summary": {
            "sync_status": "in_sync",
            "runtime_status": "healthy",
            "metrics_status": "partial",
            "apis_count": 0,
            "expected_routes_count": 0,
            "reported_routes_count": None,
            "effective_policies_count": 0,
            "reported_policies_count": None,
            "failed_policies_count": 0,
        },
        "resolved_config": {"apis": [], "policies": []},
        "sync": {
            "desired_generation": None,
            "applied_generation": None,
            "status": "in_sync",
            "drift": False,
            "last_reconciled_at": None,
            "last_error": None,
            "steps": [],
        },
        "runtime": {
            "status": "healthy",
            "last_heartbeat_at": None,
            "heartbeat_age_seconds": None,
            "version": "0.9.21",
            "mode": "edge-mcp",
            "uptime_seconds": None,
            "reported_routes_count": None,
            "reported_policies_count": None,
            "mcp_tools_count": None,
            "requests_total": None,
            "error_rate": None,
            "memory_usage_bytes": None,
        },
        "data_quality": {
            "runtime_freshness": "missing",
            "heartbeat_stale_after_seconds": 90,
            "metrics_status": "partial",
            "metrics_window_seconds": 300,
            "warnings": [],
        },
    }

    with patch("src.routers.gateway_instances.GatewayOverviewService") as MockService:
        MockService.return_value.get_overview = AsyncMock(return_value=overview)
        with TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"/v1/admin/gateways/{uuid4()}/overview")

    assert resp.status_code == 200
    assert resp.json()["schema_version"] == "1.0"
