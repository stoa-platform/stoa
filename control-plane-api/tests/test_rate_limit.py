"""Tests for rate limiting middleware (CAB-1291, CAB-2146).

CAB-2146: `request.state.user` is a dict in prod (set by auth/dependencies.py),
not a MagicMock/object. Previous tests inadvertently validated MagicMock
attribute access semantics, which masked the prod bug where every JWT user
collapsed onto `tenant:default:user:unknown`. These tests now use real
Starlette Requests with dict users.
"""

from unittest.mock import MagicMock, patch

import pytest
from starlette.requests import Request

from src.middleware.rate_limit import (
    DEFAULT_LIMITS,
    get_rate_limit_key,
    get_strict_rate_limit_key,
    rate_limit_exceeded_handler,
)


def _make_request(
    *,
    user: dict | None = None,
    api_key: str | None = None,
    remote_addr: str = "1.2.3.4",
    path: str = "/v1/test",
) -> Request:
    """Build a real Starlette Request with the given auth context."""
    raw_headers: list[tuple[bytes, bytes]] = []
    if api_key:
        raw_headers.append((b"x-api-key", api_key.encode()))

    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": raw_headers,
        "client": (remote_addr, 12345),
    }
    req = Request(scope)
    if user is not None:
        req.state.user = user
    return req


class TestGetRateLimitKey:
    def test_authenticated_user_with_tenant(self):
        request = _make_request(user={"sub": "user-123", "tenant_id": "acme"})
        key = get_rate_limit_key(request)
        assert key == "tenant:acme:user:user-123"

    def test_authenticated_user_no_tenant_uses_azp(self):
        request = _make_request(user={"sub": "user-456", "tenant_id": None, "azp": "my-client"})
        key = get_rate_limit_key(request)
        assert key == "tenant:my-client:user:user-456"

    def test_api_key_auth(self):
        request = _make_request(api_key="sk_test_1234567890abcdef_extra")
        key = get_rate_limit_key(request)
        assert key == "apikey:sk_test_12345678"

    def test_anonymous_uses_ip(self):
        request = _make_request(remote_addr="10.0.0.1")
        with patch("src.middleware.rate_limit.get_remote_address", return_value="10.0.0.1"):
            key = get_rate_limit_key(request)
        assert key == "ip:10.0.0.1"


class TestGetStrictRateLimitKey:
    def test_includes_path(self):
        request = _make_request(api_key="sk_test_1234567890abcdef", path="/v1/tools/invoke")
        key = get_strict_rate_limit_key(request)
        assert key.endswith(":path:/v1/tools/invoke")
        assert key.startswith("apikey:")


class TestDefaultLimits:
    def test_all_tiers_present(self):
        assert "authenticated" in DEFAULT_LIMITS
        assert "api_key" in DEFAULT_LIMITS
        assert "anonymous" in DEFAULT_LIMITS
        assert "tool_invoke" in DEFAULT_LIMITS
        assert "subscription" in DEFAULT_LIMITS

    def test_format(self):
        for tier, limit in DEFAULT_LIMITS.items():
            assert "/minute" in limit, f"Tier {tier} missing /minute suffix"


class TestRateLimitExceededHandler:
    @pytest.mark.asyncio
    async def test_returns_429(self):
        request = _make_request(api_key="sk_test_0000000000000000")
        exc = MagicMock()
        exc.limit = "100/minute"
        with patch("src.middleware.rate_limit.get_rate_limit_key", return_value="apikey:test"):
            response = await rate_limit_exceeded_handler(request, exc)
        assert response.status_code == 429
        assert response.headers.get("Retry-After") == "60"

    @pytest.mark.asyncio
    async def test_response_body_structure(self):
        request = _make_request()
        exc = MagicMock()
        exc.limit = "30/minute"
        with patch("src.middleware.rate_limit.get_rate_limit_key", return_value="ip:1.2.3.4"):
            response = await rate_limit_exceeded_handler(request, exc)
        import json

        body = json.loads(response.body)
        assert body["error"] == "rate_limit_exceeded"
        assert "retry_after_seconds" in body
        assert body["retry_after_seconds"] == 60
        assert "documentation" in body
