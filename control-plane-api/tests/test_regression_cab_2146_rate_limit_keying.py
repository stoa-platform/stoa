"""Regression tests for CAB-2146 (Security MEGA CAB-2079 — rate-limit keying bug).

Before the fix:
- `src/auth/dependencies.py` sets `request.state.user` as a **dict**
  (`{"sub": user_id, "tenant_id": ..., ...}`).
- `src/middleware/rate_limit.py` reads it with `getattr(user, "sub", "unknown")`,
  which always returns the default for dicts (dicts don't expose keys as
  attributes). Same for `tenant_id` and `azp`.
- Conséquence: every JWT user collapsed to the key
  `tenant:default:user:unknown` → one noisy user rate-limits all others.
- For `X-Operator-Key` requests, every operator collapsed to
  `tenant:default:user:stoa-operator` → operators share a single bucket.

After the fix:
- `get_rate_limit_key` uses `user.get(...)` dict access and yields a distinct
  key per (tenant, user) pair.
- When `X-Operator-Key` is validated, `dependencies.py` exposes
  `request.state.operator_fingerprint = sha256(key)[:16]`. The limiter branches
  on it so each operator key gets its own bucket.
"""

# regression for CAB-2079
import hashlib

import pytest
from starlette.requests import Request

from src.middleware.rate_limit import get_rate_limit_key


def _make_request(
    *,
    user: dict | None = None,
    operator_fingerprint: str | None = None,
    headers: dict[str, str] | None = None,
    client_host: str = "10.0.0.1",
) -> Request:
    """Build a minimal Starlette Request with the given state + headers."""
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "query_string": b"",
        "headers": raw_headers,
        "client": (client_host, 12345),
    }
    req = Request(scope)
    if user is not None:
        req.state.user = user
    if operator_fingerprint is not None:
        req.state.operator_fingerprint = operator_fingerprint
    return req


class TestDictUserKeying:
    """After the fix, dict-based `request.state.user` must yield distinct keys."""

    def test_regression_no_collapse_on_unknown(self):
        """The literal bug: dict user + getattr returned `user:unknown`."""
        key = get_rate_limit_key(_make_request(user={"sub": "alice", "tenant_id": "acme"}))
        assert key == "tenant:acme:user:alice"
        assert "unknown" not in key

    def test_distinct_users_same_tenant(self):
        key_alice = get_rate_limit_key(_make_request(user={"sub": "alice", "tenant_id": "acme"}))
        key_bob = get_rate_limit_key(_make_request(user={"sub": "bob", "tenant_id": "acme"}))
        assert key_alice != key_bob

    def test_distinct_tenants_same_user(self):
        key_acme = get_rate_limit_key(_make_request(user={"sub": "alice", "tenant_id": "acme"}))
        key_oasis = get_rate_limit_key(_make_request(user={"sub": "alice", "tenant_id": "oasis"}))
        assert key_acme != key_oasis

    def test_missing_tenant_falls_back_to_azp_then_default(self):
        # No tenant_id → use azp; no azp → "default"
        key_azp = get_rate_limit_key(_make_request(user={"sub": "alice", "tenant_id": None, "azp": "portal"}))
        assert key_azp == "tenant:portal:user:alice"

        key_default = get_rate_limit_key(_make_request(user={"sub": "alice", "tenant_id": None}))
        assert key_default == "tenant:default:user:alice"


class TestOperatorKeyFingerprint:
    """X-Operator-Key requests must key on fingerprint, not `sub=stoa-operator`."""

    def test_fingerprint_takes_precedence_over_user(self):
        fp = hashlib.sha256(b"op-key-1").hexdigest()[:16]
        key = get_rate_limit_key(
            _make_request(
                user={"sub": "stoa-operator", "tenant_id": None},
                operator_fingerprint=fp,
            )
        )
        assert key == f"operator:{fp}"
        assert "stoa-operator" not in key

    def test_distinct_operator_keys_distinct_buckets(self):
        fp_a = hashlib.sha256(b"op-key-A").hexdigest()[:16]
        fp_b = hashlib.sha256(b"op-key-B").hexdigest()[:16]
        key_a = get_rate_limit_key(
            _make_request(
                user={"sub": "stoa-operator", "tenant_id": None},
                operator_fingerprint=fp_a,
            )
        )
        key_b = get_rate_limit_key(
            _make_request(
                user={"sub": "stoa-operator", "tenant_id": None},
                operator_fingerprint=fp_b,
            )
        )
        assert key_a != key_b


class TestNonJwtFallbacks:
    """API key and IP fallbacks must still work."""

    def test_api_key_header_yields_apikey_prefix(self):
        key = get_rate_limit_key(_make_request(headers={"X-API-Key": "sekret-key-value-1234567890"}))
        assert key.startswith("apikey:")
        # Prefix-only — the full key must not leak into the bucket id
        assert "sekret-key-value-1234567890" not in key

    def test_ip_fallback_when_anonymous(self):
        key = get_rate_limit_key(_make_request(client_host="203.0.113.42"))
        assert key.startswith("ip:")


class TestOperatorFingerprintDerivation:
    """The fingerprint must be stable for the same key and different across keys."""

    def test_fingerprint_length_and_stability(self):
        fp1 = hashlib.sha256(b"same-key").hexdigest()[:16]
        fp2 = hashlib.sha256(b"same-key").hexdigest()[:16]
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_fingerprint_changes_across_keys(self):
        fp1 = hashlib.sha256(b"key-1").hexdigest()[:16]
        fp2 = hashlib.sha256(b"key-2").hexdigest()[:16]
        assert fp1 != fp2


@pytest.mark.asyncio
async def test_dependencies_sets_operator_fingerprint_on_state(monkeypatch):
    """Integration: when X-Operator-Key is valid, get_current_user must expose
    `request.state.operator_fingerprint` so the limiter can key on it."""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from src.auth import dependencies as deps_module
    from src.auth.dependencies import User, get_current_user

    class _Settings:
        KEYCLOAK_URL = "https://auth.test"
        keycloak_internal_url = "https://auth.test"
        KEYCLOAK_REALM = "stoa"
        KEYCLOAK_CLIENT_ID = "control-plane-api"
        gateway_api_keys_list = ["valid-operator-key"]
        LOG_DEBUG_AUTH_TOKENS = False
        LOG_DEBUG_AUTH_PAYLOAD = False
        LOG_DEBUG_AUTH_HEADERS = False

    monkeypatch.setattr(deps_module, "settings", _Settings)

    app = FastAPI()

    @app.get("/probe")
    async def probe(request: Request, user: User = pytest.importorskip("fastapi").Depends(get_current_user)):
        return {
            "user_sub": user.id,
            "fingerprint": getattr(request.state, "operator_fingerprint", None),
        }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        resp = await client.get("/probe", headers={"X-Operator-Key": "valid-operator-key"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["user_sub"] == "stoa-operator"
    expected_fp = hashlib.sha256(b"valid-operator-key").hexdigest()[:16]
    assert body["fingerprint"] == expected_fp
