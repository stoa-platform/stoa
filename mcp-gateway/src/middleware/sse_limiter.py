# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
CAB-939: SSE Connection Limiter

Protects against Slowloris and connection exhaustion attacks.
Team Coca Security Fix - 25/01/2026
"""

import asyncio
import ipaddress
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """Track individual SSE connection metadata."""

    ip: str
    tenant: str
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)

    def touch(self):
        """Update last activity timestamp."""
        self.last_activity = time.time()

    @property
    def age(self) -> float:
        """Connection age in seconds."""
        return time.time() - self.connected_at

    @property
    def idle(self) -> float:
        """Idle time in seconds."""
        return time.time() - self.last_activity


class SSEConnectionLimiter:
    """
    Rate limiter for SSE connections.

    Configurable limits (via environment or override):
    - MAX_PER_IP: Max concurrent connections from single IP (default: 10)
    - MAX_PER_TENANT: Max concurrent connections per tenant (default: 100)
    - MAX_TOTAL: Global connection limit (default: 5000)
    - IDLE_TIMEOUT: Kill idle connections after N seconds (default: 30)
    - MAX_DURATION: Max connection lifetime in seconds (default: 3600 = 1h)
    - RATE_LIMIT_PER_MIN: New connections per IP per minute (default: 5)
    """

    MAX_PER_IP: int = 10
    MAX_PER_TENANT: int = 100
    MAX_TOTAL: int = 5000
    IDLE_TIMEOUT: int = 30
    MAX_DURATION: int = 3600
    RATE_LIMIT_PER_MIN: int = 5

    def __init__(self):
        self._connections: dict[str, ConnectionInfo] = {}
        self._by_ip: dict[str, set[str]] = defaultdict(set)
        self._by_tenant: dict[str, set[str]] = defaultdict(set)
        self._recent_by_ip: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    @property
    def total(self) -> int:
        """Total active connections."""
        return len(self._connections)

    def count_by_ip(self, ip: str) -> int:
        """Count connections from specific IP."""
        return len(self._by_ip.get(ip, set()))

    def count_by_tenant(self, tenant: str) -> int:
        """Count connections for specific tenant."""
        return len(self._by_tenant.get(tenant, set()))

    async def check_allowed(
        self, ip: str, tenant: str, settings: "Settings"
    ) -> tuple[bool, str | None]:
        """
        Check if new connection is allowed.

        Args:
            ip: Client IP address
            tenant: Tenant identifier
            settings: Application settings (passed explicitly to avoid import-time issues)

        Returns:
            (allowed: bool, rejection_reason: str | None)
        """
        # CAB-939: Bypass if disabled (rollback support)
        if not settings.sse_limiter_enabled:
            return True, None

        async with self._lock:
            # Global limit
            if self.total >= self.MAX_TOTAL:
                logger.warning(
                    f"CAB-939: Global connection limit reached ({self.MAX_TOTAL})"
                )
                return False, "global_limit"

            # Per-IP limit
            if self.count_by_ip(ip) >= self.MAX_PER_IP:
                logger.warning(f"CAB-939: IP {ip} exceeded limit ({self.MAX_PER_IP})")
                return False, "ip_limit"

            # Per-tenant limit
            if self.count_by_tenant(tenant) >= self.MAX_PER_TENANT:
                logger.warning(
                    f"CAB-939: Tenant {tenant} exceeded limit ({self.MAX_PER_TENANT})"
                )
                return False, "tenant_limit"

            # Rate limit: new connections per minute per IP
            now = time.time()
            minute_ago = now - 60
            recent = [t for t in self._recent_by_ip[ip] if t > minute_ago]
            self._recent_by_ip[ip] = recent

            if len(recent) >= self.RATE_LIMIT_PER_MIN:
                logger.warning(
                    f"CAB-939: IP {ip} rate limited ({self.RATE_LIMIT_PER_MIN}/min)"
                )
                return False, "rate_limit"

            return True, None

    @asynccontextmanager
    async def track(self, conn_id: str, ip: str, tenant: str):
        """
        Context manager to track SSE connection lifecycle.

        Usage:
            async with sse_limiter.track(conn_id, ip, tenant) as info:
                # connection is tracked
                info.touch()  # update activity
            # connection automatically untracked on exit
        """
        info = ConnectionInfo(ip=ip, tenant=tenant)

        async with self._lock:
            self._connections[conn_id] = info
            self._by_ip[ip].add(conn_id)
            self._by_tenant[tenant].add(conn_id)
            self._recent_by_ip[ip].append(time.time())

        logger.info(f"CAB-939: SSE opened conn={conn_id} ip={ip} tenant={tenant}")

        try:
            yield info
        finally:
            async with self._lock:
                self._connections.pop(conn_id, None)
                self._by_ip[ip].discard(conn_id)
                self._by_tenant[tenant].discard(conn_id)

            logger.info(
                f"CAB-939: SSE closed conn={conn_id} age={info.age:.1f}s idle={info.idle:.1f}s"
            )

    async def get_expired(self) -> list[str]:
        """
        Get list of connection IDs that should be terminated.

        Connections are expired if:
        - Idle longer than IDLE_TIMEOUT
        - Total age exceeds MAX_DURATION
        """
        expired = []
        async with self._lock:
            for conn_id, info in self._connections.items():
                if info.idle > self.IDLE_TIMEOUT:
                    logger.info(
                        f"CAB-939: Expiring conn={conn_id} reason=idle ({info.idle:.0f}s)"
                    )
                    expired.append(conn_id)
                elif info.age > self.MAX_DURATION:
                    logger.info(
                        f"CAB-939: Expiring conn={conn_id} reason=max_duration ({info.age:.0f}s)"
                    )
                    expired.append(conn_id)
        return expired

    def get_stats(self) -> dict:
        """Get current limiter statistics."""
        return {
            "total_connections": self.total,
            "unique_ips": len(self._by_ip),
            "unique_tenants": len(self._by_tenant),
            "limits": {
                "max_per_ip": self.MAX_PER_IP,
                "max_per_tenant": self.MAX_PER_TENANT,
                "max_total": self.MAX_TOTAL,
                "idle_timeout": self.IDLE_TIMEOUT,
                "max_duration": self.MAX_DURATION,
            },
        }


def _ip_in_cidr(ip: str, cidr: str) -> bool:
    """Check if IP address is within CIDR range."""
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def get_client_ip(
    request: Request, x_forwarded_for: str | None, settings: "Settings"
) -> str:
    """
    Extract client IP with trusted proxy validation.

    OSS Killer fix: Settings passed explicitly to avoid cold start issues.

    Args:
        request: FastAPI request object
        x_forwarded_for: X-Forwarded-For header value
        settings: Application settings

    Returns:
        Client IP address
    """
    direct_ip = request.client.host if request.client else "unknown"

    if not x_forwarded_for:
        return direct_ip

    # Only trust X-Forwarded-For if request came from trusted proxy
    if not settings.sse_trusted_proxies:
        return direct_ip  # No trusted proxies configured = trust nothing

    trusted_cidrs = [ip.strip() for ip in settings.sse_trusted_proxies.split(",")]
    if any(_ip_in_cidr(direct_ip, cidr) for cidr in trusted_cidrs):
        return x_forwarded_for.split(",")[0].strip()

    return direct_ip


# Singleton instance
sse_limiter = SSEConnectionLimiter()
