"""Exercise native tenant resolution before repository access, without external services."""

from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.dependencies import User, get_current_user
from src.database import get_db
from src.routers import mcp_admin, mcp_connectors

SUBSCRIPTIONS = "/v1/admin/mcp/subscriptions"
CONNECTORS = "/v1/admin/mcp-connectors"
READS = [SUBSCRIPTIONS + "/pending", SUBSCRIPTIONS + "/stats", CONNECTORS]
REQUESTS = [
    ("GET", READS[0], None),
    ("GET", READS[1], None),
    ("GET", CONNECTORS, None),
    ("GET", CONNECTORS + "/sample", None),
    ("POST", CONNECTORS + "/sample/authorize", {"tenant_id": "tenant-b"}),
    ("POST", CONNECTORS + "/sample/promote", {"tenant_id": "tenant-b", "target_environment": "staging"}),
    ("DELETE", CONNECTORS + "/sample/disconnect", None),
]
Harness = tuple[TestClient, list[User], list[str], list[tuple[str, str | None]]]


def persona(role: str, tenant: str | None) -> User:
    return User(
        id="synthetic-user", email="person@example.invalid", username="synthetic", roles=[role], tenant_id=tenant,
    )


@pytest.fixture
def tenant_routes(monkeypatch: pytest.MonkeyPatch) -> Iterator[Harness]:
    users = [persona("tenant-admin", "tenant-a")]
    constructed: list[str] = []
    resolved: list[tuple[str, str | None]] = []

    async def pending(*, tenant_id: str | None, page: int, page_size: int) -> tuple[list, int]:
        resolved.append(("pending", tenant_id))
        return [], 0

    async def stats(*, tenant_id: str | None) -> dict:
        resolved.append(("stats", tenant_id))
        return {"total_subscriptions": 0, "by_status": {}, "by_server": {}, "recent_24h": 0}

    async def servers(**kwargs: object) -> tuple[list, int]:
        return [], 0

    async def templates(**kwargs: object) -> list:
        return []

    async def template(slug: str) -> None:
        return None

    async def connected(tenant_id: str | None, *, environment: str | None) -> dict:
        resolved.append(("connectors", tenant_id))
        return {}

    def repository(kind: str, **methods: object):
        def build(db: object) -> SimpleNamespace:
            constructed.append(kind)
            return SimpleNamespace(**methods)

        return build

    monkeypatch.setattr(
        mcp_admin, "MCPSubscriptionRepository", repository("subscription", list_pending=pending, get_stats=stats),
    )
    monkeypatch.setattr(mcp_admin, "MCPServerRepository", repository("server", list_all=servers))
    monkeypatch.setattr(
        mcp_connectors, "ConnectorTemplateRepository", repository("template", list_all=templates, get_by_slug=template),
    )
    monkeypatch.setattr(
        mcp_connectors, "ConnectorServerRepository", repository("connector", list_connected_template_ids=connected),
    )
    app = FastAPI()
    app.include_router(mcp_admin.admin_subscriptions_router)
    app.include_router(mcp_connectors.router)
    # Supply an already-authenticated identity; native role and tenant checks remain intact.
    app.dependency_overrides[get_current_user] = lambda: users[0]
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app) as client:
        yield client, users, constructed, resolved


@pytest.mark.parametrize("tenant", [None, "", "   "])
@pytest.mark.parametrize(("method", "path", "body"), REQUESTS)
def test_regression_missing_tenant_refuses_before_any_repository(
    tenant_routes: Harness, tenant: str | None, method: str, path: str, body: dict | None,
) -> None:
    client, users, constructed, resolved = tenant_routes
    users[0] = persona("tenant-admin", tenant)
    response = client.request(method, path, params={"tenant_id": "tenant-b"}, json=body)
    assert response.status_code == 403
    assert constructed == []
    assert resolved == []


@pytest.mark.parametrize("own", ["tenant-a", "tenant-b"])
@pytest.mark.parametrize("requested", [None, "tenant-foreign"])
@pytest.mark.parametrize("path", READS)
def test_regression_tenant_admin_keeps_own_scope(
    tenant_routes: Harness, own: str, requested: str | None, path: str,
) -> None:
    client, users, constructed, resolved = tenant_routes
    users[0] = persona("tenant-admin", own)
    response = client.get(path, params={} if requested is None else {"tenant_id": requested})
    assert response.status_code == 200
    assert constructed
    assert len(resolved) == 1
    assert resolved[0][1] == own


@pytest.mark.parametrize("own", [None, "tenant-a"])
@pytest.mark.parametrize("requested", [None, "tenant-b"])
@pytest.mark.parametrize("path", READS)
def test_regression_platform_admin_keeps_explicit_or_none_selection(
    tenant_routes: Harness, own: str | None, requested: str | None, path: str,
) -> None:
    client, users, constructed, resolved = tenant_routes
    users[0] = persona("cpi-admin", own)
    response = client.get(path, params={} if requested is None else {"tenant_id": requested})
    assert response.status_code == 200
    assert constructed
    assert len(resolved) == 1
    assert resolved[0][1] == requested


@pytest.mark.parametrize("role", ["viewer", "devops"])
@pytest.mark.parametrize(("method", "path", "body"), REQUESTS)
def test_regression_non_admin_roles_still_refused(
    tenant_routes: Harness, role: str, method: str, path: str, body: dict | None,
) -> None:
    client, users, constructed, resolved = tenant_routes
    users[0] = persona(role, "tenant-a")
    response = client.request(method, path, params={"tenant_id": "tenant-b"}, json=body)
    assert response.status_code == 403
    assert constructed == []
    assert resolved == []


def test_regression_explicit_foreign_subscription_path_still_refused(tenant_routes: Harness) -> None:
    client, users, constructed, resolved = tenant_routes
    users[0] = persona("tenant-admin", "tenant-a")
    response = client.get(SUBSCRIPTIONS + "/tenant/tenant-b")
    assert response.status_code == 403
    assert constructed == []
    assert resolved == []
