"""Behaviour of the router-level tenant dependency, and why the decorator is not used."""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from src.auth.dependencies import User, get_current_user
from src.auth.rbac import ensure_tenant, require_tenant_access


def _app(user: User | None) -> FastAPI:
    app = FastAPI()
    guarded = APIRouter(prefix="/t/{tenant_id}", dependencies=[Depends(ensure_tenant)])

    @guarded.get("/ping")
    async def ping(tenant_id: str):
        return {"tenant": tenant_id}

    decorated = APIRouter(prefix="/d/{tenant_id}")

    @decorated.get("/ping")
    @require_tenant_access
    async def decorated_ping(tenant_id: str, user=None):
        return {"tenant": tenant_id}

    app.include_router(guarded)
    app.include_router(decorated)
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


def _user(roles, tenant_id):
    return User(id="u", email="u@example.test", username="u", roles=roles, tenant_id=tenant_id)


@pytest.mark.parametrize(
    ("roles", "user_tenant", "expected"),
    [
        (["tenant-admin"], "acme", 200),
        (["viewer"], "acme", 200),
        (["tenant-admin"], "other", 403),
        (["tenant-admin"], None, 403),
        (["cpi-admin"], None, 200),
    ],
)
def test_ensure_tenant(roles, user_tenant, expected):
    client = TestClient(_app(_user(roles, user_tenant)))
    assert client.get("/t/acme/ping").status_code == expected


def test_ensure_tenant_anonymous_is_401():
    client = TestClient(_app(None))
    assert client.get("/t/acme/ping").status_code == 401


def test_decorator_does_not_inject_the_user_dependency():
    """With @wraps, FastAPI reads the wrapped signature: the user is never injected.

    The wrapper then sees the declared default (None) instead of a User, so the
    decorator cannot enforce the tenant check on a route. This documents why the
    router-level dependency is used instead.
    """
    for user in (_user(["tenant-admin"], "other"), None):
        client = TestClient(_app(user), raise_server_exceptions=False)
        # Neither 403 (other tenant) nor 401 (anonymous): the check never ran.
        assert client.get("/d/acme/ping").status_code == 500
