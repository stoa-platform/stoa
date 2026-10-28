"""Regression test: a mutation whose actor has no tenant (operator key, platform
user without a tenant claim) must reach the PostgreSQL audit trail with the same
technical tenant as the OpenSearch document.

Before the fix, `AuditMiddleware.dispatch` sent `tenant_id = "platform"` to
OpenSearch (`actor.get("tenant_id") or "platform"`) but
`actor.get("tenant_id", "unknown")` to the PostgreSQL dual-write: the key is
present with the value `None`, so `None` was passed to a NOT NULL column, the
insert failed and the failure was swallowed by contract. No such mutation ever
entered the immutable trail.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from src.opensearch.audit_middleware import AuditMiddleware

OPERATOR_IDENTITY = {
    "sub": "stoa-operator",
    "email": "",
    "name": "stoa-operator",
    "tenant_id": None,
    "type": "operator",
    "operator_fingerprint": "0123456789abcdef",
}
PLATFORM_USER_IDENTITY = {"sub": "user-platform", "email": "p@example.test", "name": "P", "tenant_id": None}
TENANT_USER_IDENTITY = {"sub": "user-acme", "email": "a@example.test", "name": "A", "tenant_id": "acme"}


def _build_app(monkeypatch, state_user: dict | None) -> tuple[FastAPI, AsyncMock, AsyncMock]:
    app = FastAPI()

    @app.post("/v1/tenants/acme/apis")
    async def create_api(request: Request):
        if state_user is not None:
            request.state.user = dict(state_user)  # what get_current_user does
        return {"ok": True}

    audit_logger = MagicMock()
    audit_logger.log = AsyncMock()
    pg_write = AsyncMock()
    app.add_middleware(AuditMiddleware, audit_logger=audit_logger)
    monkeypatch.setattr(AuditMiddleware, "_write_pg_audit", pg_write)
    return app, audit_logger.log, pg_write


async def _post(app: FastAPI) -> int:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.post("/v1/tenants/acme/apis", json={})
    return resp.status_code


@pytest.mark.asyncio
async def test_operator_mutation_reaches_pg_with_the_same_tenant_as_opensearch(monkeypatch):
    app, os_log, pg_write = _build_app(monkeypatch, OPERATOR_IDENTITY)
    assert await _post(app) == 200

    os_tenant = os_log.await_args.args[0].tenant_id
    assert os_tenant == "platform"
    pg_tenant = pg_write.await_args.kwargs["tenant_id"]
    assert isinstance(pg_tenant, str) and pg_tenant, f"tenant_id passed to PG = {pg_tenant!r}"
    assert pg_tenant == os_tenant


@pytest.mark.asyncio
async def test_platform_user_without_tenant_claim_is_attributed_to_platform(monkeypatch):
    app, os_log, pg_write = _build_app(monkeypatch, PLATFORM_USER_IDENTITY)
    assert await _post(app) == 200
    assert pg_write.await_args.kwargs["tenant_id"] == "platform"
    assert os_log.await_args.args[0].tenant_id == "platform"


@pytest.mark.asyncio
async def test_tenant_user_keeps_its_tenant(monkeypatch):
    app, os_log, pg_write = _build_app(monkeypatch, TENANT_USER_IDENTITY)
    assert await _post(app) == 200
    assert pg_write.await_args.kwargs["tenant_id"] == "acme"
    assert os_log.await_args.args[0].tenant_id == "acme"


@pytest.mark.asyncio
async def test_actor_without_tenant_key_is_attributed_to_platform(monkeypatch):
    """Service / anonymous actors have no `tenant_id` key at all: PG used to get
    "unknown" while OpenSearch got "platform"; both stores now agree."""
    app, os_log, pg_write = _build_app(monkeypatch, None)
    assert await _post(app) == 200
    assert os_log.await_args.args[0].tenant_id == "platform"
    assert pg_write.await_args.kwargs["tenant_id"] == "platform"
