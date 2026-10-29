"""Regression tests: the X-Operator-Key check must compare keys in constant time.

Before the fix, ``get_current_user`` tested ``operator_key in
settings.gateway_api_keys_list``: a plain ``str`` equality that returns as
soon as the first byte differs, which leaks the position of the first
mismatch through timing.  Every other shared-secret check of the service
(webhooks, invite codes, internal HMAC) already goes through
``hmac.compare_digest``.

After the fix, each configured key is compared with ``hmac.compare_digest``
and the behaviour is otherwise unchanged: a configured key authenticates the
operator, an unknown key (even one sharing a prefix with a configured key)
falls through to the bearer-token path and ends in 401.
"""

from __future__ import annotations

import hmac

import pytest
from fastapi import Depends, FastAPI, Request

OPERATOR_KEY = "valid-operator-key-0123456789abcdef"
OTHER_KEY = "second-operator-key-fedcba9876543210"


class _Settings:
    KEYCLOAK_URL = "https://auth.test"
    keycloak_internal_url = "https://auth.test"
    KEYCLOAK_REALM = "stoa"
    KEYCLOAK_CLIENT_ID = "control-plane-api"
    gateway_api_keys_list = [OTHER_KEY, OPERATOR_KEY]
    LOG_DEBUG_AUTH_TOKENS = False
    LOG_DEBUG_AUTH_PAYLOAD = False
    LOG_DEBUG_AUTH_HEADERS = False
    STOA_DISABLE_AUTH = False


def _app(monkeypatch) -> FastAPI:
    from src.auth import dependencies as deps_module
    from src.auth.dependencies import User, get_current_user

    monkeypatch.setattr(deps_module, "settings", _Settings)
    app = FastAPI()

    @app.get("/probe")
    async def probe(request: Request, user: User = Depends(get_current_user)):
        return {"user_id": user.id, "type": request.state.user.get("type")}

    return app


def _spy_compare_digest(monkeypatch) -> list[tuple[bytes, bytes]]:
    """Record every hmac.compare_digest call made while a request is handled."""
    calls: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    return calls


@pytest.mark.asyncio
async def test_operator_key_is_checked_with_compare_digest(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    app = _app(monkeypatch)
    calls = _spy_compare_digest(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/probe", headers={"X-Operator-Key": OPERATOR_KEY})

    assert resp.status_code == 200
    assert resp.json() == {"user_id": "stoa-operator", "type": "operator"}
    compared = {b for _, b in calls} | {a for a, _ in calls}
    assert OPERATOR_KEY.encode() in compared, "the presented key never went through hmac.compare_digest"


@pytest.mark.asyncio
async def test_unknown_operator_key_sharing_a_prefix_is_rejected(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    app = _app(monkeypatch)
    calls = _spy_compare_digest(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/probe", headers={"X-Operator-Key": OPERATOR_KEY[:-1] + "X"})

    # Falls through to the bearer path: no credentials -> 401, exactly as before.
    assert resp.status_code == 401
    # Every configured key was compared in constant time (no `in` shortcut).
    assert len(calls) >= len(_Settings.gateway_api_keys_list)


@pytest.mark.asyncio
async def test_missing_operator_key_does_not_compare_anything(monkeypatch):
    from httpx import ASGITransport, AsyncClient

    app = _app(monkeypatch)
    calls = _spy_compare_digest(monkeypatch)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/probe")

    assert resp.status_code == 401
    assert calls == []
