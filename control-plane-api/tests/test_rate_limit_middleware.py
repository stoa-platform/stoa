"""Tests for rate_limit middleware helpers (CAB-1388, CAB-2146).

CAB-2146: switched from MagicMock users to dict users to match prod behavior.
"""

from starlette.requests import Request

from src.middleware.rate_limit import (
    get_rate_limit_key,
    get_strict_rate_limit_key,
    limit_anonymous,
    limit_authenticated,
    limit_subscription,
    limit_tool_invoke,
)

# ── get_rate_limit_key ──


def _req(
    *,
    user: dict | None = None,
    api_key: str | None = None,
    remote_addr: str = "1.2.3.4",
    path: str = "/api/test",
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if api_key:
        headers.append((b"x-api-key", api_key.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": b"",
        "headers": headers,
        "client": (remote_addr, 12345),
    }
    r = Request(scope)
    if user is not None:
        r.state.user = user
    return r


class TestGetRateLimitKey:
    def test_authenticated_user_with_tenant(self):
        req = _req(user={"sub": "u-1", "tenant_id": "acme"})
        assert get_rate_limit_key(req) == "tenant:acme:user:u-1"

    def test_authenticated_user_without_tenant_uses_azp(self):
        req = _req(user={"sub": "u-2", "tenant_id": None, "azp": "app-x"})
        assert get_rate_limit_key(req) == "tenant:app-x:user:u-2"

    def test_api_key_uses_prefix(self):
        req = _req(api_key="ABCDEFGHIJKLMNOP-extra")
        assert get_rate_limit_key(req) == "apikey:ABCDEFGHIJKLMNOP"

    def test_fallback_to_ip(self):
        from unittest.mock import patch

        req = _req()
        with patch("src.middleware.rate_limit.get_remote_address", return_value="1.2.3.4"):
            assert get_rate_limit_key(req) == "ip:1.2.3.4"


class TestGetStrictRateLimitKey:
    def test_includes_path(self):
        req = _req(user={"sub": "u1", "tenant_id": "t1"}, path="/tools/invoke")
        key = get_strict_rate_limit_key(req)
        assert "path:" in key
        assert "/tools/invoke" in key


# ── Decorator factory functions ──


class TestLimitDecorators:
    def test_limit_authenticated_returns_decorator(self):
        decorator = limit_authenticated()
        assert decorator is not None

    def test_limit_tool_invoke_returns_decorator(self):
        decorator = limit_tool_invoke()
        assert decorator is not None

    def test_limit_subscription_returns_decorator(self):
        decorator = limit_subscription()
        assert decorator is not None

    def test_limit_anonymous_returns_decorator(self):
        decorator = limit_anonymous()
        assert decorator is not None

    def test_limit_authenticated_custom_limit(self):
        decorator = limit_authenticated("50/minute")
        assert decorator is not None

    def test_limit_tool_invoke_custom_limit(self):
        decorator = limit_tool_invoke("30/minute")
        assert decorator is not None
