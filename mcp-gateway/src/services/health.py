# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
STOA Platform Health Check Module
CAB-658: Add latency tracking & status badges

Provides health checking with:
- Per-component latency measurement (ms)
- Tri-state status: healthy / degraded / down
- Configurable thresholds
- Async parallel checks for performance
"""

import asyncio
import os
import time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import httpx
import asyncpg
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError


class HealthStatus(str, Enum):
    """Health status matching v2.0 system prompt spec."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"
    NOT_CONFIGURED = "not_configured"  # Component not yet deployed/configured


class ComponentHealth(BaseModel):
    """Health status for a single component."""
    status: HealthStatus
    latency_ms: Optional[float] = Field(None, description="Response time in milliseconds")
    description: Optional[str] = Field(None, description="Component description")
    message: Optional[str] = Field(None, description="Human-readable status message")
    error: Optional[str] = Field(None, description="Error message if status is down")
    details: Optional[dict] = Field(None, description="Additional component-specific details")


class PlatformHealth(BaseModel):
    """Aggregated platform health response."""
    overall: HealthStatus
    components: dict[str, ComponentHealth]
    checked_at: str

    @property
    def summary(self) -> str:
        """Human-readable summary for LLM responses."""
        statuses = {name: c.status for name, c in self.components.items()}

        down = [k for k, v in statuses.items() if v == HealthStatus.DOWN]
        not_configured = [k for k, v in statuses.items() if v == HealthStatus.NOT_CONFIGURED]
        degraded = [k for k, v in statuses.items() if v == HealthStatus.DEGRADED]

        if down:
            return f"Service down: {', '.join(down)}"
        if not_configured:
            return f"{len(not_configured)} components not configured: {', '.join(not_configured)}"
        if degraded:
            return f"Performance issues: {', '.join(degraded)}"
        return "All systems operational"


class HealthThresholds(BaseModel):
    """Latency thresholds for status determination (in ms)."""
    healthy_max: float  # Below this = healthy
    degraded_max: float  # Below this = degraded, above = effectively down due to latency


# Default thresholds per component (from CAB-658 spec)
# Note: External services (mcp/webmethods/keycloak) have higher thresholds for ALB round-trip
# Internal services (database/kafka/opensearch) have moderate thresholds for K8s network
DEFAULT_THRESHOLDS: dict[str, HealthThresholds] = {
    "mcp": HealthThresholds(healthy_max=500, degraded_max=2000),
    "webmethods": HealthThresholds(healthy_max=500, degraded_max=2000),
    "keycloak": HealthThresholds(healthy_max=500, degraded_max=2000),
    "database": HealthThresholds(healthy_max=200, degraded_max=1000),
    "kafka": HealthThresholds(healthy_max=200, degraded_max=1000),
    "opensearch": HealthThresholds(healthy_max=200, degraded_max=1000),
}


def get_component_config() -> dict[str, dict]:
    """Build component configuration with auto-detection via environment variables.

    Core components (mcp, webmethods, keycloak) are always enabled.
    Optional components (database, kafka, opensearch) are enabled if their
    corresponding environment variable is set.

    Environment Variables:
    - STOA_DATABASE_URL: Enable PostgreSQL health check
    - STOA_KAFKA_BOOTSTRAP: Enable Kafka health check
    - STOA_OPENSEARCH_URL: Enable OpenSearch health check
    """
    return {
        "mcp": {
            "enabled": True,  # Always enabled (it's us)
            "url_attr": "mcp_url",
            "description": "STOA MCP Server",
        },
        "webmethods": {
            "enabled": True,  # Always enabled (core dependency)
            "url_attr": "webmethods_url",
            "description": "webMethods API Gateway",
        },
        "keycloak": {
            "enabled": True,  # Always enabled (auth)
            "url_attr": "keycloak_url",
            "description": "Keycloak Auth Server",
        },
        "database": {
            "enabled": bool(os.getenv("STOA_DATABASE_URL")),
            "url_attr": "database_url",
            "description": "PostgreSQL Database",
            "message": "Set STOA_DATABASE_URL to enable",
        },
        "kafka": {
            "enabled": bool(os.getenv("STOA_KAFKA_BOOTSTRAP")),
            "url_attr": "kafka_bootstrap",
            "description": "Kafka Event Bus",
            "message": "Set STOA_KAFKA_BOOTSTRAP to enable",
        },
        "opensearch": {
            "enabled": bool(os.getenv("STOA_OPENSEARCH_URL")),
            "url_attr": "opensearch_url",
            "description": "OpenSearch Analytics",
            "message": "Set STOA_OPENSEARCH_URL to enable",
        },
    }


# Component configuration - evaluated at module load time
# Re-call get_component_config() for runtime re-evaluation if needed
COMPONENT_CONFIG: dict[str, dict] = get_component_config()


def determine_status(latency_ms: float, thresholds: HealthThresholds) -> HealthStatus:
    """Determine health status based on latency and thresholds."""
    if latency_ms <= thresholds.healthy_max:
        return HealthStatus.HEALTHY
    elif latency_ms <= thresholds.degraded_max:
        return HealthStatus.DEGRADED
    else:
        return HealthStatus.DEGRADED  # Very slow but responding


class HealthChecker:
    """
    Async health checker for STOA platform components.

    Usage:
        checker = HealthChecker(config)
        health = await checker.check_all()
        # or
        health = await checker.check_components(["webmethods", "database"])
    """

    def __init__(
        self,
        mcp_url: str = "",
        webmethods_url: str = "",
        keycloak_url: str = "",
        keycloak_realm: str = "stoa",
        database_url: str = "",
        kafka_bootstrap: str = "",
        opensearch_url: str = "",
        timeout_seconds: float = 5.0,
        thresholds: Optional[dict[str, HealthThresholds]] = None,
    ):
        self.mcp_url = mcp_url
        self.webmethods_url = webmethods_url
        self.keycloak_url = keycloak_url
        self.keycloak_realm = keycloak_realm
        self.database_url = database_url
        self.kafka_bootstrap = kafka_bootstrap
        self.opensearch_url = opensearch_url
        self.timeout = timeout_seconds
        self.thresholds = thresholds or DEFAULT_THRESHOLDS

    async def check_all(self) -> PlatformHealth:
        """Check all components in parallel, including not_configured ones."""
        # Use dynamic config to pick up env var changes at runtime
        component_config = get_component_config()
        return await self.check_components(list(component_config.keys()))

    async def check_components(self, components: list[str]) -> PlatformHealth:
        """Check specified components in parallel, including not_configured ones."""
        from datetime import datetime, timezone

        # Get dynamic config to pick up env var changes at runtime
        component_config = get_component_config()

        # Map component names to check functions
        check_funcs = {
            "mcp": self._check_mcp,
            "webmethods": self._check_webmethods,
            "keycloak": self._check_keycloak,
            "database": self._check_database,
            "kafka": self._check_kafka,
            "opensearch": self._check_opensearch,
        }

        # Check which components have URLs configured
        url_configured = {
            "mcp": bool(self.mcp_url),
            "webmethods": bool(self.webmethods_url),
            "keycloak": bool(self.keycloak_url),
            "database": bool(self.database_url),
            "kafka": bool(self.kafka_bootstrap),
            "opensearch": bool(self.opensearch_url),
        }

        # Separate enabled (will check) vs disabled (not_configured) components
        tasks = []
        enabled_components = []
        not_configured_components = []

        for comp in components:
            if comp not in component_config:
                continue

            config = component_config[comp]

            # Check if component is enabled AND has URL configured
            if config.get("enabled", False) and url_configured.get(comp, False):
                if comp in check_funcs:
                    tasks.append(check_funcs[comp]())
                    enabled_components.append(comp)
            else:
                # Component disabled or no URL - mark as not_configured
                not_configured_components.append(comp)

        # Run checks in parallel for enabled components
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build response with all components
        component_health: dict[str, ComponentHealth] = {}

        # Add enabled components with their check results
        for comp, result in zip(enabled_components, results):
            config = component_config.get(comp, {})
            if isinstance(result, Exception):
                component_health[comp] = ComponentHealth(
                    status=HealthStatus.UNKNOWN,
                    description=config.get("description"),
                    error=f"Check failed: {str(result)}"
                )
            else:
                # Add description from config to the result
                result.description = config.get("description")
                component_health[comp] = result

        # Add not_configured components
        for comp in not_configured_components:
            config = component_config.get(comp, {})
            component_health[comp] = ComponentHealth(
                status=HealthStatus.NOT_CONFIGURED,
                description=config.get("description"),
                message=config.get("message", f"{comp} not configured")
            )

        # Determine overall status (priority: DOWN > DEGRADED > NOT_CONFIGURED > UNKNOWN > HEALTHY)
        overall = self._compute_overall(component_health)

        return PlatformHealth(
            overall=overall,
            components=component_health,
            checked_at=datetime.now(timezone.utc).isoformat()
        )

    def _compute_overall(self, components: dict[str, ComponentHealth]) -> HealthStatus:
        """Compute overall health status from components.

        Priority: DOWN > DEGRADED > NOT_CONFIGURED > UNKNOWN > HEALTHY
        """
        statuses = [c.status for c in components.values()]

        if HealthStatus.DOWN in statuses:
            return HealthStatus.DOWN
        if HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        if HealthStatus.NOT_CONFIGURED in statuses:
            # Overall degraded if some components not configured
            return HealthStatus.DEGRADED
        if HealthStatus.UNKNOWN in statuses:
            return HealthStatus.UNKNOWN
        return HealthStatus.HEALTHY

    async def _check_mcp(self) -> ComponentHealth:
        """Check STOA MCP Server via /healthz (public endpoint).

        Note: /health/live is internal-only (403 for external).
        /healthz is the public health endpoint.
        """
        return await self._check_http_endpoint(
            url=f"{self.mcp_url}/healthz",
            component="mcp"
        )

    async def _check_webmethods(self) -> ComponentHealth:
        """Check webMethods Gateway via root endpoint (/).

        The gateway returns 302 redirect to /apigatewayui when healthy.
        The /health endpoint is only accessible from internal network.
        """
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                response = await client.get(f"{self.webmethods_url}/")
                latency_ms = (time.perf_counter() - start) * 1000

                # Gateway returns 302 redirect when healthy, or 200 for some configs
                if response.status_code in [200, 302]:
                    return ComponentHealth(
                        status=self._latency_status(latency_ms, "webmethods"),
                        latency_ms=round(latency_ms, 2),
                        details={"redirect": response.status_code == 302}
                    )
                else:
                    return ComponentHealth(
                        status=HealthStatus.DEGRADED if response.status_code < 500 else HealthStatus.DOWN,
                        latency_ms=round(latency_ms, 2),
                        error=f"HTTP {response.status_code}"
                    )
        except httpx.TimeoutException:
            return ComponentHealth(
                status=HealthStatus.DOWN,
                error=f"Connection timeout ({self.timeout}s)"
            )
        except httpx.ConnectError as e:
            return ComponentHealth(
                status=HealthStatus.DOWN,
                error=f"Connection refused: {str(e)}"
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                status=HealthStatus.DOWN,
                latency_ms=round(latency_ms, 2) if latency_ms < self.timeout * 1000 else None,
                error=str(e)
            )

    async def _check_keycloak(self) -> ComponentHealth:
        """Check Keycloak via OIDC discovery endpoint.

        Uses the .well-known/openid-configuration endpoint which is always
        publicly accessible and doesn't require authentication.
        """
        url = f"{self.keycloak_url}/realms/{self.keycloak_realm}/.well-known/openid-configuration"
        return await self._check_http_endpoint(
            url=url,
            component="keycloak"
        )

    async def _check_opensearch(self) -> ComponentHealth:
        """Check OpenSearch cluster health."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.opensearch_url}/_cluster/health")
                latency_ms = (time.perf_counter() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    cluster_status = data.get("status", "unknown")

                    # Map OpenSearch status to our status
                    if cluster_status == "green":
                        status = self._latency_status(latency_ms, "opensearch")
                    elif cluster_status == "yellow":
                        status = HealthStatus.DEGRADED
                    else:
                        status = HealthStatus.DOWN

                    return ComponentHealth(
                        status=status,
                        latency_ms=round(latency_ms, 2),
                        details={
                            "cluster_status": cluster_status,
                            "number_of_nodes": data.get("number_of_nodes"),
                            "active_shards": data.get("active_shards")
                        }
                    )
                else:
                    return ComponentHealth(
                        status=HealthStatus.DOWN,
                        latency_ms=round(latency_ms, 2),
                        error=f"HTTP {response.status_code}"
                    )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                status=HealthStatus.DOWN,
                latency_ms=round(latency_ms, 2) if latency_ms < self.timeout * 1000 else None,
                error=str(e)
            )

    async def _check_database(self) -> ComponentHealth:
        """Check PostgreSQL connectivity."""
        start = time.perf_counter()
        try:
            conn = await asyncio.wait_for(
                asyncpg.connect(self.database_url),
                timeout=self.timeout
            )
            try:
                # Simple query to verify connection
                result = await conn.fetchval("SELECT 1")
                latency_ms = (time.perf_counter() - start) * 1000

                if result == 1:
                    return ComponentHealth(
                        status=self._latency_status(latency_ms, "database"),
                        latency_ms=round(latency_ms, 2)
                    )
                else:
                    return ComponentHealth(
                        status=HealthStatus.DEGRADED,
                        latency_ms=round(latency_ms, 2),
                        error="Unexpected query result"
                    )
            finally:
                await conn.close()
        except asyncio.TimeoutError:
            return ComponentHealth(
                status=HealthStatus.DOWN,
                error=f"Connection timeout ({self.timeout}s)"
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                status=HealthStatus.DOWN,
                latency_ms=round(latency_ms, 2) if latency_ms < self.timeout * 1000 else None,
                error=str(e)
            )

    async def _check_kafka(self) -> ComponentHealth:
        """Check Kafka broker connectivity."""
        start = time.perf_counter()
        producer = None
        try:
            producer = AIOKafkaProducer(
                bootstrap_servers=self.kafka_bootstrap,
                request_timeout_ms=int(self.timeout * 1000),
                metadata_max_age_ms=int(self.timeout * 1000),
            )
            await asyncio.wait_for(producer.start(), timeout=self.timeout)
            latency_ms = (time.perf_counter() - start) * 1000

            # Get cluster metadata for details
            cluster = producer.client.cluster
            brokers = len(cluster.brokers())

            return ComponentHealth(
                status=self._latency_status(latency_ms, "kafka"),
                latency_ms=round(latency_ms, 2),
                details={"broker_count": brokers}
            )
        except asyncio.TimeoutError:
            return ComponentHealth(
                status=HealthStatus.DOWN,
                error=f"Connection timeout ({self.timeout}s)"
            )
        except KafkaConnectionError as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                status=HealthStatus.DOWN,
                latency_ms=round(latency_ms, 2) if latency_ms < self.timeout * 1000 else None,
                error=f"Connection refused: {str(e)}"
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                status=HealthStatus.DOWN,
                latency_ms=round(latency_ms, 2) if latency_ms < self.timeout * 1000 else None,
                error=str(e)
            )
        finally:
            if producer:
                await producer.stop()

    async def _check_http_endpoint(
        self,
        url: str,
        component: str,
        expected_status: int = 200
    ) -> ComponentHealth:
        """Generic HTTP health check with latency measurement."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                latency_ms = (time.perf_counter() - start) * 1000

                if response.status_code == expected_status:
                    return ComponentHealth(
                        status=self._latency_status(latency_ms, component),
                        latency_ms=round(latency_ms, 2)
                    )
                else:
                    # Got response but not expected status
                    status = HealthStatus.DEGRADED if response.status_code < 500 else HealthStatus.DOWN
                    return ComponentHealth(
                        status=status,
                        latency_ms=round(latency_ms, 2),
                        error=f"HTTP {response.status_code}"
                    )
        except httpx.TimeoutException:
            return ComponentHealth(
                status=HealthStatus.DOWN,
                error=f"Connection timeout ({self.timeout}s)"
            )
        except httpx.ConnectError as e:
            return ComponentHealth(
                status=HealthStatus.DOWN,
                error=f"Connection refused: {str(e)}"
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return ComponentHealth(
                status=HealthStatus.DOWN,
                latency_ms=round(latency_ms, 2) if latency_ms < self.timeout * 1000 else None,
                error=str(e)
            )

    def _latency_status(self, latency_ms: float, component: str) -> HealthStatus:
        """Determine status based on latency thresholds."""
        thresholds = self.thresholds.get(component)
        if thresholds:
            return determine_status(latency_ms, thresholds)
        return HealthStatus.HEALTHY  # No thresholds = assume healthy if responding


# Convenience function for simple usage
async def check_platform_health(
    components: Optional[list[str]] = None,
    **config
) -> PlatformHealth:
    """
    Quick health check function.

    Args:
        components: List of components to check, or None for all
        **config: Configuration options for HealthChecker

    Returns:
        PlatformHealth with status of all checked components
    """
    checker = HealthChecker(**config)
    if components:
        return await checker.check_components(components)
    return await checker.check_all()
