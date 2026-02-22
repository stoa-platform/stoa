"""Tests for rate_limit middleware helpers (CAB-1388)."""

from unittest.mock import MagicMock

from src.middleware.rate_limit import (
    get_rate_limit_key,
    get_strict_rate_limit_key,
    limit_anonymous,
    limit_authenticated,
    limit_subscription,
    limit_tool_invoke,
)

# ── get_rate_limit_key ──


class TestGetRateLimitKey:
    def _req(self, user=None, api_key=None, remote_addr="1.2.3.4"):
        req = MagicMock()
        req.state = MagicMock()
        req.state.user = user
        req.headers = MagicMock()
        req.headers.get = MagicMock(return_value=api_key)
        req.url = MagicMock()
        req.url.path = "/api/test"
        req.client = MagicMock()
        req.client.host = remote_addr
        return req

    def test_authenticated_user_with_tenant(self):
        user = MagicMock(tenant_id="acme", sub="u-1")
        req = self._req(user=user)
        key = get_rate_limit_key(req)
        assert key == "tenant:acme:user:u-1"

    def test_authenticated_user_without_tenant_uses_azp(self):
        user = MagicMock(tenant_id=None, sub="u-2", azp="app-x")
        req = self._req(user=user)
        key = get_rate_limit_key(req)
        assert key == "tenant:app-x:user:u-2"

    def test_api_key_uses_prefix(self):
        req = self._req(user=None, api_key="ABCDEFGHIJKLMNOP-extra")
        key = get_rate_limit_key(req)
        assert key == "apikey:ABCDEFGHIJKLMNOP"

    def test_fallback_to_ip(self):
        req = self._req(user=None, api_key=None)
        from unittest.mock import patch

        # get_remote_address reads from request.client.host or headers
        with patch("src.middleware.rate_limit.get_remote_address", return_value="1.2.3.4"):
            key = get_rate_limit_key(req)
        assert key == "ip:1.2.3.4"


class TestGetStrictRateLimitKey:
    def test_includes_path(self):
        user = MagicMock(tenant_id="t1", sub="u1")
        req = MagicMock()
        req.state = MagicMock()
        req.state.user = user
        req.headers = MagicMock()
        req.headers.get = MagicMock(return_value=None)
        req.url = MagicMock()
        req.url.path = "/tools/invoke"
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
