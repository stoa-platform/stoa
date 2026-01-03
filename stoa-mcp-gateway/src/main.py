"""STOA MCP Gateway - Main Application Entry Point.

Model Context Protocol Gateway for AI-Native API Management.
Exposes APIs as MCP Tools for LLM consumption.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from .config import get_settings

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger(__name__)

# Prometheus metrics
REQUEST_COUNT = Counter(
    "mcp_gateway_requests_total",
    "Total number of requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "mcp_gateway_request_latency_seconds",
    "Request latency in seconds",
    ["method", "endpoint"],
)

# Application state
app_state: dict[str, Any] = {
    "ready": False,
    "started_at": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    settings = get_settings()
    logger.info(
        "Starting STOA MCP Gateway",
        version=settings.app_version,
        environment=settings.environment,
    )

    # Startup
    app_state["started_at"] = datetime.now(timezone.utc)
    app_state["ready"] = True

    logger.info(
        "STOA MCP Gateway ready",
        base_domain=settings.base_domain,
        keycloak_url=settings.keycloak_url,
    )

    yield

    # Shutdown
    logger.info("Shutting down STOA MCP Gateway")
    app_state["ready"] = False


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Model Context Protocol Gateway for AI-Native API Management",
        version=settings.app_version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Configure per environment
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    register_routes(app)

    return app


def register_routes(app: FastAPI) -> None:
    """Register all application routes."""

    @app.get("/health", tags=["Health"])
    async def health_check() -> dict[str, Any]:
        """Health check endpoint for load balancers.

        Returns basic health status. Always returns 200 if the service is running.
        """
        settings = get_settings()
        return {
            "status": "healthy",
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/ready", tags=["Health"])
    async def readiness_check() -> JSONResponse:
        """Readiness check endpoint for Kubernetes.

        Returns 200 if the service is ready to accept traffic.
        Returns 503 if dependencies are not available.
        """
        settings = get_settings()

        checks: dict[str, Any] = {
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "app_ready": app_state["ready"],
            },
        }

        # TODO: Add dependency checks (Keycloak, Control Plane API, etc.)

        is_ready = all(checks["checks"].values())
        checks["status"] = "ready" if is_ready else "not_ready"

        return JSONResponse(
            content=checks,
            status_code=200 if is_ready else 503,
        )

    @app.get("/live", tags=["Health"])
    async def liveness_check() -> dict[str, str]:
        """Liveness check endpoint for Kubernetes.

        Simple check that the process is running.
        """
        return {"status": "alive"}

    @app.get("/metrics", tags=["Observability"])
    async def metrics() -> bytes:
        """Prometheus metrics endpoint."""
        return generate_latest()

    @app.get("/", tags=["Info"])
    async def root() -> dict[str, Any]:
        """Root endpoint with service information."""
        settings = get_settings()
        return {
            "service": "stoa-mcp-gateway",
            "description": "Model Context Protocol Gateway for AI-Native API Management",
            "version": settings.app_version,
            "environment": settings.environment,
            "docs": "/docs" if settings.debug else "Disabled in production",
            "links": {
                "health": "/health",
                "ready": "/ready",
                "metrics": "/metrics",
            },
        }

    # MCP Protocol endpoints placeholder
    @app.get("/mcp/v1/tools", tags=["MCP"])
    async def list_tools() -> dict[str, Any]:
        """List available MCP tools.

        This endpoint will expose registered APIs as MCP tools.
        """
        return {
            "tools": [],
            "message": "MCP Tool Registry - Coming soon",
        }

    @app.get("/mcp/v1/resources", tags=["MCP"])
    async def list_resources() -> dict[str, Any]:
        """List available MCP resources.

        This endpoint will expose data sources as MCP resources.
        """
        return {
            "resources": [],
            "message": "MCP Resource Registry - Coming soon",
        }


# Create the application instance
app = create_app()


def main() -> None:
    """Run the application with uvicorn."""
    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
