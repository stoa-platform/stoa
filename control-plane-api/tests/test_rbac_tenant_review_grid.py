"""Negative cases for tenant scoping: missing tenant, near-miss tenants, foreign ids, roles, admins."""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

API_ID = str(uuid4())
SKILLS = "/v1/tenants/acme/skills"
RECO = "/v1/tenants/acme/reconciliation"
ASSIGN = f"/v1/tenants/acme/apis/{API_ID}"


@pytest.fixture
def reached():
    calls: list[str] = []

    async def fake(self, *args, **kwargs):
        calls.append("reached")
        return []

    async def owned(self, *args, **kwargs):
        return True

    skill = "src.routers.skills.SkillRepository"
    reco = "src.routers.reconciliation.ReconciliationService"
    assign = "src.routers.api_gateway_assignments.ApiGatewayAssignmentRepository"
    with (
        patch(f"{skill}.list_by_tenant", fake),
        patch(f"{skill}.count_by_tenant", AsyncMock(return_value=0)),
        patch(f"{skill}.create", fake),
        patch(f"{skill}.get", fake),
        patch(f"{skill}.update", fake),
        patch(f"{skill}.delete", fake),
        patch(f"{reco}.get_status", fake),
        patch(f"{reco}.reconcile", fake),
        patch(f"{assign}.list_for_api", fake),
        patch(f"{assign}.api_belongs_to_tenant", owned),
    ):
        yield calls


ONE_ROUTE_PER_ROUTER = [
    ("get", SKILLS),
    ("get", f"{RECO}/status"),
    ("get", f"{ASSIGN}/gateway-assignments"),
]
ROUTER_IDS = ["skills", "reconciliation", "assignments"]


@pytest.mark.parametrize(("verb", "url"), ONE_ROUTE_PER_ROUTER, ids=ROUTER_IDS)
def test_user_without_tenant_is_refused(client_as_no_tenant_user, reached, verb, url):
    """N4: a non-admin user without tenant never gets any tenant."""
    assert getattr(client_as_no_tenant_user, verb)(url).status_code == 403
    assert reached == []


@pytest.mark.parametrize("tenant", ["ACME", "acme%20", "%20acme", "acme-"])
def test_near_miss_tenant_is_refused(client_as_tenant_admin, reached, tenant):
    """N5: the tenant comparison is exact."""
    assert client_as_tenant_admin.get(f"/v1/tenants/{tenant}/skills").status_code == 403
    assert reached == []


@pytest.mark.parametrize(
    ("verb", "url", "body"),
    [
        ("post", SKILLS, {"name": "probe"}),
        ("patch", f"{SKILLS}/{uuid4()}", {"name": "probe"}),
        ("delete", f"{SKILLS}/{uuid4()}", None),
        ("post", f"{RECO}/sync", None),
    ],
    ids=["skill-create", "skill-update", "skill-delete", "reconciliation-sync"],
)
def test_viewer_cannot_write(client_as_viewer, reached, verb, url, body):
    """N3: read-only role of the right tenant is refused on writes."""
    call = getattr(client_as_viewer, verb)
    resp = call(url) if body is None else call(url, json=body)
    assert resp.status_code == 403
    assert reached == []


@pytest.mark.parametrize(("verb", "url"), ONE_ROUTE_PER_ROUTER, ids=ROUTER_IDS)
def test_cpi_admin_reaches_any_tenant(client_as_cpi_admin, reached, verb, url):
    """N7: platform administration keeps working (the stubbed service layer is reached)."""
    status = None
    # The stub's return shape may not match the response model: only the auth outcome matters.
    with contextlib.suppress(Exception):
        status = getattr(client_as_cpi_admin, verb)(url).status_code
    assert status not in (401, 403)
    assert reached


def test_foreign_skill_id_under_own_tenant_is_not_found(client_as_tenant_admin):
    """N6 (skills): an id of another tenant under the caller's own tenant answers 404."""
    foreign = SimpleNamespace(tenant_id="other-tenant")
    base = "src.routers.skills.SkillRepository"
    with (
        patch(f"{base}.get", AsyncMock(return_value=foreign)),
        patch(f"{base}.update", AsyncMock()) as update,
        patch(f"{base}.delete", AsyncMock()) as delete,
    ):
        sid = uuid4()
        assert client_as_tenant_admin.get(f"{SKILLS}/{sid}").status_code == 404
        assert client_as_tenant_admin.patch(f"{SKILLS}/{sid}", json={"name": "x"}).status_code == 404
        assert client_as_tenant_admin.delete(f"{SKILLS}/{sid}").status_code == 404
    update.assert_not_awaited()
    delete.assert_not_awaited()


@pytest.mark.parametrize("path", ["/deploy", "/deploy/validate"])
def test_foreign_api_id_under_own_tenant_is_not_found_on_deploy(client_as_tenant_admin, path):
    """N6 (deploy): a catalog id of another tenant does not resolve under the caller's tenant."""
    from src.services.deployment_orchestration_service import ApiNotFoundError

    svc = "src.routers.api_gateway_assignments.DeploymentOrchestrationService"
    body = {"environment": "dev", "gateway_ids": [str(uuid4())]}
    with (
        patch(f"{svc}.deploy_api_to_env", AsyncMock(side_effect=ApiNotFoundError("x"))),
        patch(f"{svc}.preflight_deploy_api_to_env", AsyncMock(side_effect=ApiNotFoundError("x"))),
    ):
        resp = client_as_tenant_admin.post(f"{ASSIGN}{path}", json=body)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "API not found"


async def test_catalog_lookup_by_uuid_is_filtered_by_tenant():
    """N6 (service): the UUID lookup of a catalog entry carries the tenant filter."""
    from src.services.deployment_orchestration_service import ApiNotFoundError, DeploymentOrchestrationService

    statements = []
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()

    async def execute(stmt, *args, **kwargs):
        statements.append(stmt)
        return result

    db.execute = execute
    svc = DeploymentOrchestrationService(db)
    with patch.object(svc, "_sync_api_from_git", AsyncMock(return_value=None)), pytest.raises(ApiNotFoundError):
        await svc._resolve_api_catalog("acme", str(uuid4()))
    first = str(statements[0].compile(dialect=postgresql.dialect()))
    assert "api_catalog.tenant_id" in first


async def test_assignment_delete_statement_joins_tenant():
    """N6 (delete): the delete is scoped by assignment, API and tenant."""
    from src.repositories.api_gateway_assignment import ApiGatewayAssignmentRepository

    captured = []
    db = MagicMock()

    async def execute(stmt):
        captured.append(stmt)
        return SimpleNamespace(rowcount=0)

    db.execute = execute
    await ApiGatewayAssignmentRepository(db).delete_by_id(uuid4(), api_id=uuid4(), tenant_id="acme")
    sql = str(captured[0].compile(dialect=postgresql.dialect()))
    assert "api_gateway_assignments.api_id =" in sql
    assert "api_catalog.tenant_id" in sql
