"""Tenant isolation matrix for the gateway-assignment and deploy routes.

Each route lives under /v1/tenants/{tenant_id}/apis/{api_id}/... and is guarded
by a role check. These tests pin the expected tenant behaviour: a tenant-admin
of another tenant must be refused (403) before any repository or service call,
and a viewer must be refused (403) on write routes. The persistence and service
layers are replaced by stubs that record whether they were reached; the
authorization boundary under test (FastAPI dependencies) is real.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

API_ID = str(uuid4())
BASE = f"/v1/tenants/acme/apis/{API_ID}"
ROUTER = "src.routers.api_gateway_assignments"


def _assignment():
    return SimpleNamespace(
        id=uuid4(),
        api_id=uuid4(),
        gateway_id=uuid4(),
        environment="dev",
        auto_deploy=False,
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def reached():
    """Stub the data and service layers and record whether they are reached."""
    calls: list[str] = []

    async def create(self, obj):
        calls.append("create")
        return _assignment()

    async def list_for_api(self, *args, **kwargs):
        calls.append("list")
        return []

    async def delete_by_id(self, *args, **kwargs):
        calls.append("delete")
        return True

    async def deploy(self, **kwargs):
        calls.append("deploy")
        return []

    async def preflight(self, **kwargs):
        calls.append("preflight")
        return []

    async def environments(self, **kwargs):
        calls.append("environments")
        return []

    async def owned(self, *args, **kwargs):
        return True

    repo = f"{ROUTER}.ApiGatewayAssignmentRepository"
    svc = f"{ROUTER}.DeploymentOrchestrationService"
    with (
        patch(f"{repo}.api_belongs_to_tenant", owned),
        patch(f"{repo}.gateway_usable_by_tenant", owned),
        patch(f"{repo}.create", create),
        patch(f"{repo}.list_for_api", list_for_api),
        patch(f"{repo}.delete_by_id", delete_by_id),
        patch(f"{svc}.deploy_api_to_env", deploy),
        patch(f"{svc}.preflight_deploy_api_to_env", preflight),
        patch(f"{svc}.get_deployable_environments", environments),
    ):
        yield calls


DEPLOY_BODY = {"environment": "dev", "gateway_ids": [str(uuid4())]}

ROUTES = [
    ("post", f"{BASE}/gateway-assignments", {"gateway_id": str(uuid4()), "environment": "dev"}),
    ("get", f"{BASE}/gateway-assignments", None),
    ("delete", f"{BASE}/gateway-assignments/{uuid4()}", None),
    ("post", f"{BASE}/deploy", DEPLOY_BODY),
    ("post", f"{BASE}/deploy/validate", DEPLOY_BODY),
    ("get", f"{BASE}/deployable-environments", None),
]
ROUTE_IDS = ["create", "list", "delete", "deploy", "validate", "environments"]


def _call(client, verb, url, body):
    if body is None:
        return getattr(client, verb)(url)
    return getattr(client, verb)(url, json=body)


@pytest.mark.parametrize(("verb", "url", "body"), ROUTES, ids=ROUTE_IDS)
def test_other_tenant_admin_is_refused(client_as_other_tenant, reached, verb, url, body):
    """A tenant-admin of 'other-tenant' must not act on tenant 'acme'."""
    response = _call(client_as_other_tenant, verb, url, body)
    assert response.status_code == 403, (response.status_code, reached)
    assert reached == []


@pytest.mark.parametrize(("verb", "url", "body"), ROUTES, ids=ROUTE_IDS)
def test_own_tenant_admin_is_allowed(client_as_tenant_admin, reached, verb, url, body):
    """The tenant-admin of 'acme' reaches the service layer on every route."""
    response = _call(client_as_tenant_admin, verb, url, body)
    assert response.status_code < 400, (response.status_code, response.text[:200])
    assert reached


WRITE_ROUTES = [r for r, i in zip(ROUTES, ROUTE_IDS, strict=True) if i in {"create", "delete", "deploy"}]


@pytest.mark.parametrize(("verb", "url", "body"), WRITE_ROUTES, ids=["create", "delete", "deploy"])
def test_viewer_cannot_write(client_as_viewer, reached, verb, url, body):
    """A viewer of the same tenant is refused on write routes."""
    response = _call(client_as_viewer, verb, url, body)
    assert response.status_code == 403
    assert reached == []


@pytest.fixture
def foreign_objects(reached):
    """The API (or gateway) in the request does not belong to the caller's tenant."""

    async def not_owned(self, *args, **kwargs):
        return False

    repo = f"{ROUTER}.ApiGatewayAssignmentRepository"
    with patch(f"{repo}.api_belongs_to_tenant", not_owned), patch(f"{repo}.gateway_usable_by_tenant", not_owned):
        yield reached


@pytest.mark.parametrize(("verb", "url", "body"), ROUTES[:2], ids=["create", "list"])
def test_foreign_api_is_not_found(client_as_tenant_admin, foreign_objects, verb, url, body):
    """An API id from another tenant answers a generic 404, before any repository write."""
    response = _call(client_as_tenant_admin, verb, url, body)
    assert response.status_code == 404
    assert foreign_objects == []


def test_delete_is_scoped_to_api_and_tenant(client_as_tenant_admin):
    """The delete passes the path api_id and tenant_id down to the repository."""
    seen: dict = {}

    async def delete_by_id(self, assignment_id, **kwargs):
        seen.update(kwargs)
        return False

    with patch(f"{ROUTER}.ApiGatewayAssignmentRepository.delete_by_id", delete_by_id):
        response = client_as_tenant_admin.delete(f"{BASE}/gateway-assignments/{uuid4()}")
    assert response.status_code == 404
    assert seen == {"api_id": __import__("uuid").UUID(API_ID), "tenant_id": "acme"}


@pytest.mark.parametrize(("verb", "url", "body"), ROUTES, ids=ROUTE_IDS)
def test_anonymous_request_is_refused(client, reached, verb, url, body):
    response = _call(client, verb, url, body)
    assert response.status_code == 401
    assert reached == []


def test_gateway_visibility_rules():
    from src.repositories.api_gateway_assignment import gateway_usable_by_tenant

    def gw(tenant_id=None, visibility=None):
        return SimpleNamespace(tenant_id=tenant_id, visibility=visibility)

    assert gateway_usable_by_tenant(gw(), "acme")
    assert gateway_usable_by_tenant(gw("acme"), "acme")
    assert not gateway_usable_by_tenant(gw("other"), "acme")
    assert gateway_usable_by_tenant(gw(visibility={"tenant_ids": ["acme"]}), "acme")
    assert not gateway_usable_by_tenant(gw(visibility={"tenant_ids": ["other"]}), "acme")
