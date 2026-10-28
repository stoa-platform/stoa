"""Regression tests for CAB-2079 P3-03 (audit half): operator calls must be
attributable to one operator key in the audit trail.

Before the fix:
- `get_current_user` accepted `X-Operator-Key` and stored
  `request.state.user = {"sub": "stoa-operator", ...}`. The sha256[:16]
  fingerprint of the key only reached a structlog info line.
- `AuditMiddleware._extract_actor` therefore recorded every operator as
  `{"id": "stoa-operator", "type": "user"}`: two distinct operator keys were
  indistinguishable in the audit index.

After the fix:
- the operator identity on `request.state.user` carries `type="operator"` and
  `operator_fingerprint` (never the raw key);
- the audit actor copies both fields; JWT users are unchanged (`type="user"`,
  no fingerprint).
"""

# regression for CAB-2079
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Request

OPERATOR_KEY = "valid-operator-key"
EXPECTED_FP = hashlib.sha256(OPERATOR_KEY.encode("utf-8")).hexdigest()[:16]


class _Settings:
    KEYCLOAK_URL = "https://auth.test"
    keycloak_internal_url = "https://auth.test"
    KEYCLOAK_REALM = "stoa"
    KEYCLOAK_CLIENT_ID = "control-plane-api"
    gateway_api_keys_list = [OPERATOR_KEY]
    LOG_DEBUG_AUTH_TOKENS = False
    LOG_DEBUG_AUTH_PAYLOAD = False
    LOG_DEBUG_AUTH_HEADERS = False
    STOA_DISABLE_AUTH = False


@pytest.mark.asyncio
async def test_operator_identity_on_request_state_carries_type_and_fingerprint(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from src.auth import dependencies as deps_module
    from src.auth.dependencies import User, get_current_user

    monkeypatch.setattr(deps_module, "settings", _Settings)
    app = FastAPI()

    @app.get("/probe")
    async def probe(request: Request, user: User = Depends(get_current_user)):
        return {"state_user": request.state.user, "user_id": user.id}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/probe", headers={"X-Operator-Key": OPERATOR_KEY})

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == "stoa-operator"
    state_user = body["state_user"]
    assert state_user["sub"] == "stoa-operator"
    assert state_user["type"] == "operator"
    assert state_user["operator_fingerprint"] == EXPECTED_FP
    # The raw key must never be stored anywhere on the request identity.
    assert OPERATOR_KEY not in json.dumps(state_user)


def _fake_request(state_user: dict | None) -> SimpleNamespace:
    state = SimpleNamespace()
    if state_user is not None:
        state.user = state_user
    return SimpleNamespace(
        client=SimpleNamespace(host="203.0.113.10"),
        headers={"User-Agent": "pytest"},
        state=state,
    )


async def _extract_actor(request) -> dict:
    from src.opensearch.audit_middleware import AuditMiddleware

    middleware = AuditMiddleware.__new__(AuditMiddleware)  # no ASGI app needed for this helper
    return await middleware._extract_actor(request)


@pytest.mark.asyncio
async def test_audit_actor_distinguishes_operators_by_fingerprint():
    actor = await _extract_actor(
        _fake_request(
            {
                "sub": "stoa-operator",
                "email": "",
                "name": "stoa-operator",
                "tenant_id": None,
                "type": "operator",
                "operator_fingerprint": EXPECTED_FP,
            }
        )
    )
    assert actor["id"] == "stoa-operator"
    assert actor["type"] == "operator"
    assert actor["operator_fingerprint"] == EXPECTED_FP
    assert OPERATOR_KEY not in json.dumps(actor)


@pytest.mark.asyncio
async def test_audit_actor_for_jwt_user_is_unchanged():
    actor = await _extract_actor(
        _fake_request({"sub": "user-1", "email": "a@example.test", "name": "A", "tenant_id": "tenant-a"})
    )
    assert actor["id"] == "user-1"
    assert actor["type"] == "user"
    assert actor["tenant_id"] == "tenant-a"
    assert "operator_fingerprint" not in actor
