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
import time
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field
import httpx
import asyncpg
from aiokafka import AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError


class HealthStatus(str, Enum):
    """Tri-state health status matching v2.0 system prompt spec."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


class ComponentHealth(BaseModel):
    """Health status for a single component."""
    status: HealthStatus
    latency_ms: Optional[float] = Field(None, description="Response time in milliseconds")
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
        statuses = [c.status for c in self.components.values()]
        if all(s == HealthStatus.HEALTHY for s in statuses):
            return "All systems operational"
        elif HealthStatus.DOWN in statuses:
            down = [k for k, v in self.components.items() if v.status == HealthStatus.DOWN]
            return f"Service degraded: {', '.join(down)} down"
        else:
            degraded = [k for k, v in self.components.items() if v.status == HealthStatus.DEGRADED]
            return f"Performance issues: {', '.join(degraded)} degraded"


class HealthThresholds(BaseModel):
    """Latency thresholds for status determination (in ms)."""
    healthy_max: float  # Below this = healthy
    degraded_max: float  # Below this = degraded, above = effectively down due to latency


# Default thresholds per component (from CAB-658 spec)
DEFAULT_THRESHOLDS: dict[str, HealthThresholds] = {
    "gateway": HealthThresholds(healthy_max=100, degraded_max=500),
    "keycloak": HealthThresholds(healthy_max=200, degraded_max=1000),
    "database": HealthThresholds(healthy_max=50, degraded_max=200),
    "kafka": HealthThresholds(healthy_max=100, degraded_max=500),
    "opensearch": HealthThresholds(healthy_max=100, degraded_max=500),
}


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
        health = await checker.check_components(["gateway", "database"])
    """

    def __init__(
        self,
        gateway_url: str = "http://localhost:8080",
        keycloak_url: str = "http://localhost:8180",
        database_url: str = "postgresql://localhost:5432/stoa",
        kafka_bootstrap: str = "localhost:9092",
        opensearch_url: str = "http://localhost:9200",
        timeout_seconds: float = 5.0,
        thresholds: Optional[dict[str, HealthThresholds]] = None,
    ):
        self.gateway_url = gateway_url
        self.keycloak_url = keycloak_url
        self.database_url = database_url
        self.kafka_bootstrap = kafka_bootstrap
        self.opensearch_url = opensearch_url
        self.timeout = timeout_seconds
        self.thresholds = thresholds or DEFAULT_THRESHOLDS

    async def check_all(self) -> PlatformHealth:
        """Check all components in parallel."""
        return await self.check_components(list(DEFAULT_THRESHOLDS.keys()))

    async def check_components(self, components: list[str]) -> PlatformHealth:
        """Check specified components in parallel."""
        from datetime import datetime, timezone

        # Map component names to check functions
        check_funcs = {
            "gateway": self._check_gateway,
            "keycloak": self._check_keycloak,
            "database": self._check_database,
            "kafka": self._check_kafka,
            "opensearch": self._check_opensearch,
        }

        # Run checks in parallel
        tasks = []
        valid_components = []
        for comp in components:
            if comp in check_funcs:
                tasks.append(check_funcs[comp]())
                valid_components.append(comp)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build response
        component_health: dict[str, ComponentHealth] = {}
        for comp, result in zip(valid_components, results):
            if isinstance(result, Exception):
                component_health[comp] = ComponentHealth(
                    status=HealthStatus.UNKNOWN,
                    error=f"Check failed: {str(result)}"
                )
            else:
                component_health[comp] = result

        # Determine overall status
        statuses = [h.status for h in component_health.values()]
        if HealthStatus.DOWN in statuses:
            overall = HealthStatus.DOWN
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        elif HealthStatus.UNKNOWN in statuses:
            overall = HealthStatus.UNKNOWN
        else:
            overall = HealthStatus.HEALTHY

        return PlatformHealth(
            overall=overall,
            components=component_health,
            checked_at=datetime.now(timezone.utc).isoformat()
        )

    async def _check_gateway(self) -> ComponentHealth:
        """Check webMethods Gateway health endpoint."""
        return await self._check_http_endpoint(
            url=f"{self.gateway_url}/health",
            component="gateway"
        )

    async def _check_keycloak(self) -> ComponentHealth:
        """Check Keycloak health endpoint."""
        return await self._check_http_endpoint(
            url=f"{self.keycloak_url}/health/ready",
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
