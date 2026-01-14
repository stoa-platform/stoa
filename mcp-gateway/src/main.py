"""STOA MCP Gateway - Main Application Entry Point.

Model Context Protocol Gateway for AI-Native API Management.
Exposes APIs as MCP Tools for LLM consumption.
"""

import asyncio
import ipaddress
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response

from .config import get_settings
from .handlers import mcp_router, subscriptions_router, mcp_sse_router
from .middleware import MetricsMiddleware
from .services import get_tool_registry, shutdown_tool_registry, init_database, shutdown_database
from .k8s import get_tool_watcher, shutdown_tool_watcher

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

    # Initialize database
    try:
        await init_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning("Database initialization failed, using in-memory storage", error=str(e))

    # Initialize tool registry
    registry = await get_tool_registry()

    # Initialize K8s watcher and connect to registry
    if settings.k8s_watcher_enabled:
        # Get watcher without starting (to set callbacks first)
        watcher = await get_tool_watcher(start=False)

        # Define callbacks to connect watcher to registry
        async def on_tool_added(tool):
            registry.register(tool)
            logger.info("K8s tool registered", tool_name=tool.name)

        async def on_tool_removed(tool_name):
            registry.unregister(tool_name)
            logger.info("K8s tool unregistered", tool_name=tool_name)

        async def on_tool_modified(tool):
            registry.register(tool)  # Register overwrites existing
            logger.info("K8s tool updated", tool_name=tool.name)

        # Set callbacks BEFORE starting to catch initial events
        watcher.set_callbacks(
            on_added=on_tool_added,
            on_removed=on_tool_removed,
            on_modified=on_tool_modified,
        )

        # Now start the watcher
        await watcher.startup()

        logger.info("K8s watcher connected to tool registry")

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

    # Cleanup K8s watcher
    await shutdown_tool_watcher()

    # Cleanup tool registry
    await shutdown_tool_registry()

    # Cleanup database
    await shutdown_database()


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

    # Metrics middleware (must be added first to capture all requests)
    if settings.enable_metrics:
        app.add_middleware(MetricsMiddleware)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    register_routes(app)

    # Register MCP router
    app.include_router(mcp_router)

    # Register subscriptions router
    app.include_router(subscriptions_router)

    # Register MCP SSE router for native Claude Desktop support
    app.include_router(mcp_sse_router)

    return app


def _is_internal_request(request: Request) -> bool:
    """Check if request comes from internal network (K8s cluster).

    Detection strategy:
    Kubernetes probes access the pod directly via the service,
    while external requests go through the ingress (ALB -> nginx -> pod).

    We detect external requests by checking if the request went through
    the ingress, which sets the X-Request-ID header (nginx adds this).

    Internal networks (for direct connections):
    - 10.0.0.0/8 (K8s pod network)
    - 172.16.0.0/12 (K8s service network)
    - 192.168.0.0/16 (Private networks)
    - 127.0.0.0/8 (Localhost)
    """
    # Check direct client IP
    client_ip = request.client.host if request.client else "0.0.0.0"

    # Check if request came through ingress by looking for typical ingress headers
    # X-Request-ID is added by nginx-ingress for all requests
    has_request_id = bool(request.headers.get("X-Request-ID", "").strip())
    # X-Forwarded headers are added by ALB/nginx for external requests
    has_forwarded = bool(request.headers.get("X-Forwarded-For", "").strip())
    has_forwarded_proto = bool(request.headers.get("X-Forwarded-Proto", "").strip())

    # If request has typical ingress headers, it's likely external
    # unless the original IP is also internal (rare case)
    if has_request_id or has_forwarded or has_forwarded_proto:
        # Request likely came through ingress - assume external
        return False

    # No ingress headers - direct connection from within cluster
    try:
        ip = ipaddress.ip_address(client_ip)
        internal_networks = [
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("127.0.0.0/8"),
        ]
        return any(ip in network for network in internal_networks)
    except ValueError:
        return False


def register_routes(app: FastAPI) -> None:
    """Register all application routes."""

    @app.get("/health", tags=["Health"])
    async def health_check(request: Request) -> dict[str, Any]:
        """Health check endpoint for Kubernetes probes.

        Only accessible from internal cluster network.
        Returns basic health status. Always returns 200 if the service is running.
        """
        if not _is_internal_request(request):
            # Only log blocked requests (K8s probes happen frequently)
            client = request.client.host if request.client else "unknown"
            logger.warning("Blocked external health check request", client_ip=client)
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        settings = get_settings()
        return {
            "status": "healthy",
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/ready", tags=["Health"])
    async def readiness_check(request: Request) -> JSONResponse:
        """Readiness check endpoint for Kubernetes.

        Only accessible from internal cluster network.
        Returns 200 if the service is ready to accept traffic.
        Returns 503 if dependencies are not available.
        """
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        settings = get_settings()

        checks: dict[str, Any] = {
            "service": "stoa-mcp-gateway",
            "version": settings.app_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {
                "app_ready": app_state["ready"],
            },
        }

        is_ready = all(checks["checks"].values())
        checks["status"] = "ready" if is_ready else "not_ready"

        return JSONResponse(
            content=checks,
            status_code=200 if is_ready else 503,
        )

    @app.get("/live", tags=["Health"])
    async def liveness_check(request: Request) -> dict[str, str]:
        """Liveness check endpoint for Kubernetes.

        Only accessible from internal cluster network.
        Simple check that the process is running.
        """
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        return {"status": "alive"}

    @app.get("/metrics", tags=["Observability"])
    async def metrics(request: Request) -> Response:
        """Prometheus metrics endpoint.

        Only accessible from internal cluster network.
        """
        if not _is_internal_request(request):
            raise HTTPException(status_code=403, detail="Forbidden - internal only")

        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.get("/", tags=["Info"])
    async def root() -> dict[str, Any]:
        """Root endpoint with service information."""
        settings = get_settings()
        return {
            "service": "stoa-mcp-gateway",
            "description": "Model Context Protocol Gateway for AI-Native API Management",
            "version": settings.app_version,
            "mcp": {
                "tools": "/mcp/v1/tools",
                "sse": "/mcp/sse",
                "docs": "https://modelcontextprotocol.io",
            },
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
