"""Health Check Endpoints (CAB-308)

K8s-standard health endpoints for pod monitoring:
- /health/live   - Liveness probe (process alive)
- /health/ready  - Readiness probe (ready for traffic)
- /health/startup - Startup probe (boot complete)
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..services import kafka_service, git_service, awx_service, keycloak_service
from ..services.gateway_service import gateway_service

router = APIRouter(prefix="/health", tags=["Health"])


def _check_kafka_connected() -> bool:
    """Check if Kafka producer is connected."""
    return kafka_service.kafka_service._producer is not None


def _check_gitlab_connected() -> bool:
    """Check if GitLab client is connected."""
    return git_service.git_service._gl is not None


def _check_keycloak_connected() -> bool:
    """Check if Keycloak client is connected."""
    return keycloak_service.keycloak_service._keycloak_openid is not None


def _check_awx_connected() -> bool:
    """Check if AWX client is connected."""
    return awx_service.awx_service._client is not None


def _check_gateway_connected() -> bool:
    """Check if Gateway client is connected."""
    return gateway_service._session is not None


class HealthCheck(BaseModel):
    """Health check response model."""
    status: str
    version: str
    timestamp: str
    checks: Optional[dict] = None


class DependencyStatus(BaseModel):
    """Status of a dependency."""
    status: str
    latency_ms: Optional[float] = None
    error: Optional[str] = None


@router.get("/live", response_model=HealthCheck)
async def liveness():
    """Liveness probe - process is alive.

    K8s will restart the pod if this fails.
    Should be a simple check that the process is running.
    """
    return HealthCheck(
        status="healthy",
        version=settings.VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/ready", response_model=HealthCheck)
async def readiness():
    """Readiness probe - ready to accept traffic.

    K8s will remove pod from service if this fails.
    Checks critical dependencies (Kafka, Keycloak).
    Non-critical: GitLab, Gateway, AWX.
    """
    checks = {}
    all_healthy = True

    # Check Kafka connection (critical)
    try:
        kafka_healthy = _check_kafka_connected()
        checks["kafka"] = "ok" if kafka_healthy else "disconnected"
        if not kafka_healthy:
            all_healthy = False
    except Exception as e:
        checks["kafka"] = f"error: {str(e)}"
        all_healthy = False

    # Check Keycloak connection (critical)
    try:
        keycloak_healthy = _check_keycloak_connected()
        checks["keycloak"] = "ok" if keycloak_healthy else "disconnected"
        if not keycloak_healthy:
            all_healthy = False
    except Exception as e:
        checks["keycloak"] = f"error: {str(e)}"
        all_healthy = False

    # Check GitLab connection (non-critical)
    try:
        gitlab_healthy = _check_gitlab_connected()
        checks["gitlab"] = "ok" if gitlab_healthy else "disconnected"
    except Exception as e:
        checks["gitlab"] = f"error: {str(e)}"

    # Check Gateway connection (non-critical)
    try:
        gateway_healthy = _check_gateway_connected()
        checks["gateway"] = "ok" if gateway_healthy else "disconnected"
    except Exception as e:
        checks["gateway"] = f"error: {str(e)}"

    # Check AWX connection (non-critical)
    try:
        awx_healthy = _check_awx_connected()
        checks["awx"] = "ok" if awx_healthy else "disconnected"
    except Exception as e:
        checks["awx"] = f"error: {str(e)}"

    status = "healthy" if all_healthy else "degraded"

    response = HealthCheck(
        status=status,
        version=settings.VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
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
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
