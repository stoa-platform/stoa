"""Health Check Endpoints (CAB-308)

K8s-standard health endpoints for pod monitoring:
- /health/live   - Liveness probe (process alive)
- /health/ready  - Readiness probe (ready for traffic)
- /health/startup - Startup probe (boot complete)
"""

import asyncio
import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..services import kafka_service, keycloak_service
from ..services.gateway_service import gateway_service
from ..services.git_provider import git_provider_factory
from ..services.vault_client import get_vault_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


def _check_kafka_connected() -> bool:
    """Check if Kafka producer is connected."""
    return kafka_service._producer is not None


def _check_git_connected() -> bool:
    """Check if git provider is connected."""
    try:
        provider = git_provider_factory()
        return getattr(provider, "_gl", None) is not None or getattr(provider, "_client", None) is not None
    except Exception:
        return False


def _check_keycloak_connected() -> bool:
    """Check if Keycloak admin client is connected."""
    return keycloak_service._admin is not None


def _check_gateway_connected() -> bool:
    """Check if Gateway is configured (proxy mode or client)."""
    # In OIDC proxy mode, no persistent client is created
    # Gateway is "connected" if using proxy mode or has a client
    from ..config import settings

    if settings.GATEWAY_USE_OIDC_PROXY:
        return True  # Proxy mode is always available
    return gateway_service._client is not None


# The secrets store is not a readiness dependency, but checking it is a
# blocking network call. It runs in a worker thread, bounded by this timeout,
# and its result is reused for the TTL so probes never queue behind it.
VAULT_READINESS_TIMEOUT_SECONDS = 2.0
VAULT_READINESS_CACHE_TTL_SECONDS = 30.0
_vault_readiness_cache: tuple[float, str] | None = None
_vault_readiness_task: asyncio.Future[bool] | None = None


def _reset_vault_readiness_cache() -> None:
    """Forget the cached secrets-store status (tests, client reset)."""
    global _vault_readiness_cache, _vault_readiness_task
    _vault_readiness_cache = None
    _vault_readiness_task = None


async def _vault_readiness_status() -> str:
    """Secrets-store status for /health/ready, never blocking the event loop.

    At most one check runs at a time; a check still running after the timeout
    reports "timeout" and that result is cached like any other.
    """
    global _vault_readiness_cache, _vault_readiness_task

    now = time.monotonic()
    if _vault_readiness_cache is not None and now - _vault_readiness_cache[0] < VAULT_READINESS_CACHE_TTL_SECONDS:
        return _vault_readiness_cache[1]

    vault = get_vault_client()
    if not vault.enabled:
        return "disabled"

    if _vault_readiness_task is None or _vault_readiness_task.done():
        _vault_readiness_task = asyncio.ensure_future(asyncio.to_thread(vault.health_check))

    try:
        healthy = await asyncio.wait_for(asyncio.shield(_vault_readiness_task), VAULT_READINESS_TIMEOUT_SECONDS)
        status = "ok" if healthy else "disconnected"
    except TimeoutError:
        status = "timeout"
    except Exception:
        status = "error"

    _vault_readiness_cache = (time.monotonic(), status)
    return status


class HealthCheck(BaseModel):
    """Health check response model."""

    status: str
    version: str
    timestamp: str
    checks: dict | None = None


class DependencyStatus(BaseModel):
    """Status of a dependency."""

    status: str
    latency_ms: float | None = None
    error: str | None = None


@router.get("/live", response_model=HealthCheck)
async def liveness():
    """Liveness probe - process is alive.

    K8s will restart the pod if this fails.
    Should be a simple check that the process is running.
    """
    return HealthCheck(
        status="healthy",
        version=settings.VERSION,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/ready", response_model=HealthCheck)
async def readiness():
    """Readiness probe - ready to accept traffic.

    K8s will remove pod from service if this fails.
    Checks critical dependencies (Kafka, Keycloak).
    Non-critical: GitLab, Gateway.
    """
    checks = {}
    all_healthy = True

    # Check Kafka connection (critical — only if enabled)
    if settings.KAFKA_ENABLED:
        try:
            kafka_healthy = _check_kafka_connected()
            checks["kafka"] = "ok" if kafka_healthy else "disconnected"
            if not kafka_healthy:
                all_healthy = False
        except Exception as e:
            checks["kafka"] = f"error: {e!s}"
            all_healthy = False
    else:
        checks["kafka"] = "disabled"

    # Check Keycloak connection (critical)
    try:
        keycloak_healthy = _check_keycloak_connected()
        checks["keycloak"] = "ok" if keycloak_healthy else "disconnected"
        if not keycloak_healthy:
            all_healthy = False
    except Exception as e:
        checks["keycloak"] = f"error: {e!s}"
        all_healthy = False

    # Check git provider connection (non-critical)
    try:
        git_healthy = _check_git_connected()
        checks["git"] = "ok" if git_healthy else "disconnected"
    except Exception as e:
        checks["git"] = f"error: {e!s}"

    # Check Gateway connection (non-critical)
    try:
        gateway_healthy = _check_gateway_connected()
        checks["gateway"] = "ok" if gateway_healthy else "disconnected"
    except Exception as e:
        checks["gateway"] = f"error: {e!s}"

    # Check Vault connection (non-critical — MCP credentials feature).
    # Bounded and cached: a slow secrets store must not hold the probe.
    try:
        checks["vault"] = await _vault_readiness_status()
    except Exception as e:
        # Probe output stays generic: report a fixed status, keep details in logs.
        logger.warning("Secret store readiness check failed: %s", type(e).__name__)
        checks["vault"] = "error"

    status = "healthy" if all_healthy else "degraded"

    response = HealthCheck(
        status=status,
        version=settings.VERSION,
        timestamp=datetime.now(UTC).isoformat(),
        checks=checks,
    )

    if not all_healthy:
        # Return 503 if critical dependencies are down
        raise HTTPException(status_code=503, detail=response.model_dump())

    return response


@router.get("/startup", response_model=HealthCheck)
async def startup():
    """Startup probe - initial boot complete.

    K8s uses this during pod startup to know when
    to start running liveness/readiness probes.
    """
    return HealthCheck(
        status="healthy",
        version=settings.VERSION,
        timestamp=datetime.now(UTC).isoformat(),
    )


@router.get("/workers")
async def workers_status():
    """Background workers health status."""
    from ..workers.gateway_health_worker import gateway_health_worker
    from ..workers.gateway_reconciler import gateway_reconciler

    return {
        "gateway_health_worker": {
            "active": gateway_health_worker._running,
        },
        "gateway_reconciler": gateway_reconciler.status,
    }
