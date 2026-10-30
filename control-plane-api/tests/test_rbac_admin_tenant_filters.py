"""Tenant filters on admin list and sync routes for non platform-admin callers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

CONSOLE = "/v1/admin/deployments/console"
CONSOLE_REPO = "src.routers.gateway_deployments.GatewayDeploymentRepository"
APIS = "/v1/admin/catalog/apis"
CATALOG_REPO = "src.routers.catalog_admin.CatalogRepository"
RUNTIME = "src.routers.catalog_admin.load_api_runtime_deployment_summaries"
SYNC = "/v1/admin/catalog/sync/mcp-servers"
SYNC_SVC = "src.routers.catalog_admin.CatalogSyncService"
GET_ASYNC_DB = "src.routers.catalog_admin.get_async_db"


async def _fake_get_db():
    yield MagicMock()


def _console(app, query=""):
    with patch(CONSOLE_REPO) as repo_cls, TestClient(app) as client:
        repo_cls.return_value.list_console_contract = AsyncMock(return_value=([], 0))
        resp = client.get(CONSOLE + query)
        return resp, repo_cls.return_value.list_console_contract


def _apis(app, query=""):
    with (
        patch(CATALOG_REPO) as repo_cls,
        patch(RUNTIME, AsyncMock(return_value={})),
        patch(GET_ASYNC_DB, _fake_get_db),
        TestClient(app) as client,
    ):
        repo_cls.return_value.get_portal_apis = AsyncMock(return_value=([], 0))
        resp = client.get(APIS + query)
        return resp, repo_cls.return_value.get_portal_apis


def _sync(app, query=""):
    svc = MagicMock()
    svc.sync_mcp_servers = AsyncMock()
    with patch(SYNC_SVC, return_value=svc), patch(GET_ASYNC_DB, _fake_get_db), TestClient(app) as client:
        resp = client.post(SYNC + query)
    return resp, svc.sync_mcp_servers


@pytest.mark.parametrize("call", [_console, _apis], ids=["console", "apis"])
@pytest.mark.parametrize("query", ["?tenant_id=other-tenant", ""], ids=["other-tenant", "no-filter"])
def test_read_routes_only_return_own_tenant(app_with_tenant_admin, call, query):
    resp, repo_call = call(app_with_tenant_admin, query)
    assert resp.status_code == 200
    assert repo_call.await_args.kwargs["tenant_id"] == "acme"


@pytest.mark.parametrize("call", [_console, _apis], ids=["console", "apis"])
def test_read_routes_refuse_user_without_tenant(app_with_no_tenant_user, call):
    resp, repo_call = call(app_with_no_tenant_user)
    assert resp.status_code == 403
    repo_call.assert_not_awaited()


@pytest.mark.parametrize("call", [_console, _apis], ids=["console", "apis"])
def test_read_routes_cpi_admin_keeps_free_filter(app_with_cpi_admin, call):
    resp, repo_call = call(app_with_cpi_admin, "?tenant_id=other-tenant")
    assert resp.status_code == 200
    assert repo_call.await_args.kwargs["tenant_id"] == "other-tenant"


@pytest.mark.parametrize("query", ["?tenant_id=other-tenant", ""], ids=["other-tenant", "global"])
def test_sync_tenant_admin_other_or_global_is_403(app_with_tenant_admin, query):
    resp, sync_call = _sync(app_with_tenant_admin, query)
    assert resp.status_code == 403
    sync_call.assert_not_awaited()


def test_sync_tenant_admin_own_tenant_is_allowed(app_with_tenant_admin):
    resp, sync_call = _sync(app_with_tenant_admin, "?tenant_id=acme")
    assert resp.status_code == 200
    sync_call.assert_awaited_once_with("acme")


def test_sync_cpi_admin_global_is_allowed(app_with_cpi_admin):
    resp, sync_call = _sync(app_with_cpi_admin)
    assert resp.status_code == 200
    sync_call.assert_awaited_once_with(None)
