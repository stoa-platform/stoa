"""Tests for rate limiting middleware (CAB-1291)"""
from unittest.mock import MagicMock, patch

import pytest

from src.middleware.rate_limit import (
    DEFAULT_LIMITS,
    get_rate_limit_key,
    get_strict_rate_limit_key,
    rate_limit_exceeded_handler,
)


def _make_request(user=None, api_key=None, remote_addr="1.2.3.4", path="/v1/test"):
    """Build a mock Request with given auth context."""
    request = MagicMock()
    request.state = MagicMock()
    if user:
        request.state.user = user
    else:
        request.state.user = None
        # getattr(request.state, "user", None) should return None
        del request.state.user

    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    request.headers = headers
    request.url.path = path
    request.method = "GET"

    # For get_remote_address fallback
    request.client = MagicMock()
    request.client.host = remote_addr

    return request


class TestGetRateLimitKey:
    def test_authenticated_user_with_tenant(self):
        user = MagicMock()
        user.tenant_id = "acme"
        user.sub = "user-123"
        request = _make_request(user=user)
        key = get_rate_limit_key(request)
        assert key == "tenant:acme:user:user-123"

    def test_authenticated_user_no_tenant_uses_azp(self):
        user = MagicMock(spec=[])
        user.tenant_id = None
        user.sub = "user-456"
        user.azp = "my-client"
        # Simulate getattr behavior
        request = MagicMock()
        request.state.user = user
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
