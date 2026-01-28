# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Tests for CAB-939 SSE Connection Limiter."""

import pytest
from unittest.mock import MagicMock

from src.config import Settings, clear_settings_cache
from src.middleware.sse_limiter import (
    SSEConnectionLimiter,
    ConnectionInfo,
    get_client_ip,
    _ip_in_cidr,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def limiter() -> SSEConnectionLimiter:
    """Create a fresh SSEConnectionLimiter instance."""
    return SSEConnectionLimiter()


@pytest.fixture
def settings_enabled() -> Settings:
    """Settings with SSE limiter enabled."""
    clear_settings_cache()
    return Settings(
        base_domain="test.local",
        sse_limiter_enabled=True,
        sse_trusted_proxies="",
    )


@pytest.fixture
def settings_disabled() -> Settings:
    """Settings with SSE limiter disabled."""
    clear_settings_cache()
    return Settings(
        base_domain="test.local",
        sse_limiter_enabled=False,
        sse_trusted_proxies="",
    )


@pytest.fixture
def settings_with_trusted_proxy() -> Settings:
    """Settings with trusted proxy configured."""
    clear_settings_cache()
    return Settings(
        base_domain="test.local",
        sse_limiter_enabled=True,
        sse_trusted_proxies="10.0.0.0/8,172.16.0.0/12",
    )


# =============================================================================
# ConnectionInfo Tests
# =============================================================================


class TestConnectionInfo:
    """Tests for ConnectionInfo dataclass."""

    def test_touch_updates_last_activity(self):
        """Test touch() updates last_activity timestamp."""
        info = ConnectionInfo(ip="1.2.3.4", tenant="test-tenant")
        initial_activity = info.last_activity

        import time
        time.sleep(0.01)  # Small delay
        info.touch()

        assert info.last_activity > initial_activity

    def test_age_property(self):
        """Test age property returns time since connection."""
        info = ConnectionInfo(ip="1.2.3.4", tenant="test-tenant")

        import time
        time.sleep(0.01)

        assert info.age > 0

    def test_idle_property(self):
        """Test idle property returns time since last activity."""
        info = ConnectionInfo(ip="1.2.3.4", tenant="test-tenant")

        import time
        time.sleep(0.01)

        assert info.idle > 0


# =============================================================================
# SSEConnectionLimiter Tests
# =============================================================================


class TestSSEConnectionLimiter:
    """Tests for SSEConnectionLimiter class."""

    @pytest.mark.asyncio
    async def test_check_allowed_when_disabled(
        self, limiter: SSEConnectionLimiter, settings_disabled: Settings
    ):
        """Test check_allowed returns True when limiter is disabled."""
        allowed, reason = await limiter.check_allowed("1.2.3.4", "tenant", settings_disabled)

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_check_allowed_initial_request(
        self, limiter: SSEConnectionLimiter, settings_enabled: Settings
    ):
        """Test first connection is allowed."""
        allowed, reason = await limiter.check_allowed("1.2.3.4", "tenant", settings_enabled)

        assert allowed is True
        assert reason is None

    @pytest.mark.asyncio
    async def test_ip_limit_enforced(
        self, limiter: SSEConnectionLimiter, settings_enabled: Settings
    ):
        """Test 11th connection from same IP is rejected (limit is 10)."""
        ip = "1.2.3.4"
        tenant = "test-tenant"

        # Create 10 connections from same IP
        for i in range(10):
            async with limiter.track(f"conn-{i}", ip, tenant):
                pass  # Connection tracked
            # Manually add back to simulate active connections
            limiter._connections[f"conn-{i}"] = ConnectionInfo(ip=ip, tenant=tenant)
            limiter._by_ip[ip].add(f"conn-{i}")
            limiter._by_tenant[tenant].add(f"conn-{i}")

        # 11th should be rejected
        allowed, reason = await limiter.check_allowed(ip, tenant, settings_enabled)

        assert allowed is False
        assert reason == "ip_limit"

    @pytest.mark.asyncio
    async def test_tenant_limit_enforced(
        self, limiter: SSEConnectionLimiter, settings_enabled: Settings
    ):
        """Test 101st connection for same tenant is rejected (limit is 100)."""
        tenant = "test-tenant"

        # Create 100 connections from different IPs
        for i in range(100):
            ip = f"1.2.3.{i % 256}"
            limiter._connections[f"conn-{i}"] = ConnectionInfo(ip=ip, tenant=tenant)
            limiter._by_ip[ip].add(f"conn-{i}")
            limiter._by_tenant[tenant].add(f"conn-{i}")

        # 101st should be rejected
        allowed, reason = await limiter.check_allowed("9.9.9.9", tenant, settings_enabled)

        assert allowed is False
        assert reason == "tenant_limit"

    @pytest.mark.asyncio
    async def test_rate_limit_enforced(
        self, limiter: SSEConnectionLimiter, settings_enabled: Settings
    ):
        """Test 6th connection in 1 minute from same IP is rejected."""
        ip = "1.2.3.4"
        tenant = "test-tenant"

        # Simulate 5 recent connections
        import time
        now = time.time()
        limiter._recent_by_ip[ip] = [now - 10, now - 20, now - 30, now - 40, now - 50]

        # 6th should be rejected
        allowed, reason = await limiter.check_allowed(ip, tenant, settings_enabled)

        assert allowed is False
        assert reason == "rate_limit"

    @pytest.mark.asyncio
    async def test_track_context_manager(
        self, limiter: SSEConnectionLimiter
    ):
        """Test track() context manager adds and removes connections."""
        assert limiter.total == 0

        async with limiter.track("conn-1", "1.2.3.4", "tenant"):
            assert limiter.total == 1
            assert limiter.count_by_ip("1.2.3.4") == 1
            assert limiter.count_by_tenant("tenant") == 1

        assert limiter.total == 0
        assert limiter.count_by_ip("1.2.3.4") == 0
        assert limiter.count_by_tenant("tenant") == 0

    def test_get_stats(self, limiter: SSEConnectionLimiter):
        """Test get_stats returns correct structure."""
        stats = limiter.get_stats()

        assert "total_connections" in stats
        assert "unique_ips" in stats
        assert "unique_tenants" in stats
        assert "limits" in stats
        assert stats["limits"]["max_per_ip"] == 10
        assert stats["limits"]["max_per_tenant"] == 100


# =============================================================================
# IP Helper Tests
# =============================================================================


class TestIPHelpers:
    """Tests for IP helper functions."""

    def test_ip_in_cidr_valid(self):
        """Test _ip_in_cidr with valid IP in range."""
        assert _ip_in_cidr("10.0.0.1", "10.0.0.0/8") is True
        assert _ip_in_cidr("10.255.255.255", "10.0.0.0/8") is True
        assert _ip_in_cidr("172.16.0.1", "172.16.0.0/12") is True

    def test_ip_in_cidr_outside_range(self):
        """Test _ip_in_cidr with IP outside range."""
        assert _ip_in_cidr("192.168.1.1", "10.0.0.0/8") is False
        assert _ip_in_cidr("11.0.0.1", "10.0.0.0/8") is False

    def test_ip_in_cidr_invalid_ip(self):
        """Test _ip_in_cidr with invalid IP returns False."""
        assert _ip_in_cidr("invalid", "10.0.0.0/8") is False

    def test_get_client_ip_no_header(self, settings_enabled: Settings):
        """Test get_client_ip uses direct IP when no X-Forwarded-For."""
        request = MagicMock()
        request.client.host = "192.168.1.100"

        ip = get_client_ip(request, None, settings_enabled)

        assert ip == "192.168.1.100"

    def test_get_client_ip_untrusted_proxy(self, settings_enabled: Settings):
        """Test get_client_ip ignores X-Forwarded-For from untrusted proxy."""
        request = MagicMock()
        request.client.host = "192.168.1.100"  # Not in trusted proxies

        ip = get_client_ip(request, "1.2.3.4", settings_enabled)

        # Should use direct IP since proxy is not trusted
        assert ip == "192.168.1.100"

    def test_get_client_ip_trusted_proxy(self, settings_with_trusted_proxy: Settings):
        """Test get_client_ip uses X-Forwarded-For from trusted proxy."""
        request = MagicMock()
        request.client.host = "10.0.0.1"  # In trusted range 10.0.0.0/8

        ip = get_client_ip(request, "203.0.113.50, 10.0.0.1", settings_with_trusted_proxy)

        # Should use first IP from X-Forwarded-For
        assert ip == "203.0.113.50"

    def test_get_client_ip_no_trusted_proxies_configured(self, settings_enabled: Settings):
        """Test get_client_ip uses direct IP when no trusted proxies configured."""
        request = MagicMock()
        request.client.host = "10.0.0.1"

        ip = get_client_ip(request, "203.0.113.50", settings_enabled)

        # No trusted proxies = don't trust X-Forwarded-For
        assert ip == "10.0.0.1"
