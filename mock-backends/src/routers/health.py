"""Health check endpoints for Kubernetes probes.

CAB-1018: Mock APIs for Central Bank Demo
Provides /health, /health/live, /health/ready endpoints.
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from src.config import settings
from src.middleware.metrics import get_metrics, get_metrics_content_type

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Health check response model."""

    status: Literal["healthy", "unhealthy"] = Field(
        description="Health status"
    )
    service: str = Field(description="Service name")
    version: str = Field(description="Service version")
    environment: str = Field(description="Environment")
    timestamp: str = Field(description="ISO timestamp")
    demo_mode: bool = Field(description="Whether demo mode is enabled")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "healthy",
                "service": "mock-backends",
                "version": "1.0.0",
                "environment": "demo",
                "timestamp": "2026-02-26T10:00:00Z",
                "demo_mode": True,
            }
        }
    }


class ReadinessResponse(BaseModel):
    """Readiness check response model."""

    ready: bool = Field(description="Whether service is ready to accept traffic")
    checks: dict = Field(description="Individual check results")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Basic health check endpoint.

    Returns service health status and metadata.
    """
    return HealthResponse(
        status="healthy",
        service="mock-backends",
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.utcnow().isoformat() + "Z",
        demo_mode=settings.demo_mode,
    )


@router.get("/health/live", response_model=HealthResponse)
async def liveness_probe() -> HealthResponse:
    """Kubernetes liveness probe.

    Returns 200 if the process is alive.
    Used by Kubernetes to determine if the container should be restarted.
    """
    return HealthResponse(
        status="healthy",
        service="mock-backends",
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.utcnow().isoformat() + "Z",
        demo_mode=settings.demo_mode,
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_probe() -> ReadinessResponse:
    """Kubernetes readiness probe.

    Returns 200 if the service is ready to accept traffic.
    Used by Kubernetes to determine if traffic should be routed to this pod.

    For mock-backends, always ready (no external dependencies).
    """
    return ReadinessResponse(
        ready=True,
        checks={
            "config_loaded": True,
            "demo_mode": settings.demo_mode,
            "metrics_enabled": settings.metrics_enabled,
        },
    )


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """Prometheus metrics endpoint.

    Returns metrics in Prometheus text format.
    """
    return Response(
        content=get_metrics(),
        media_type=get_metrics_content_type(),
    )
