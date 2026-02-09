"""
STOA Control-Plane API
FastAPI backend with RBAC, GitOps, and Kafka integration
"""
import asyncio
import os
from contextlib import asynccontextmanager, suppress

import httpx
import sqlalchemy.exc
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.responses import Response

from .config import settings
from .features.error_snapshots import add_error_snapshot_middleware, connect_error_snapshots
from .logging_config import configure_logging, get_logger
from .middleware.http_logging import HTTPLoggingMiddleware

# Note: These are now imported as instances, not modules
from .middleware.metrics import MetricsMiddleware, get_metrics
from .middleware.rate_limit import limiter, rate_limit_exceeded_handler
from .opensearch import search_router, setup_opensearch
from .routers import (
    admin_prospects,
    apis,
    applications,  # noqa: F401
    business,
    catalog_admin,
    certificates,
    consumers,
    contracts,
    deployments,
    events,
    gateway,
    gateway_deployments,
    gateway_instances,
    gateway_internal,
    gateway_observability,
    gateway_policies,
    git,
    health,
    mcp_gitops,
    mcp_policy_proxy,
    mcp_proxy,
    monitoring,
    operations,
    plans,
    platform,
    portal,
    portal_applications,
    quotas,
    self_service_logs,
    service_accounts,
    subscriptions,
    tenant_webhooks,
    tenants,
    traces,
    usage,
    users,
    webhooks,
)
from .routers.external_mcp_servers import (
    admin_router as external_mcp_servers_admin_router,
    internal_router as external_mcp_servers_internal_router,
)
from .routers.mcp import (
    servers_router as mcp_servers_router,
    subscriptions_router as mcp_subscriptions_router,
    validation_router as mcp_validation_router,
)
from .routers.mcp_admin import (
    admin_servers_router as mcp_admin_servers_router,
    admin_subscriptions_router as mcp_admin_subscriptions_router,
)
from .services import argocd_service, awx_service, git_service, kafka_service, keycloak_service, metrics_service
from .services.gateway_service import gateway_service
from .tracing_config import configure_tracing, shutdown_tracing
from .workers.deployment_worker import deployment_worker
from .workers.error_snapshot_consumer import error_snapshot_consumer
from .workers.gateway_health_worker import gateway_health_worker
from .workers.sync_engine import sync_engine

# Configure structured logging (CAB-281)
configure_logging()
logger = get_logger(__name__)

# Flag to control worker startup (can be disabled for dev/testing)
ENABLE_WORKER = os.getenv("ENABLE_DEPLOYMENT_WORKER", "true").lower() == "true"
ENABLE_SNAPSHOT_CONSUMER = os.getenv("ENABLE_SNAPSHOT_CONSUMER", "true").lower() == "true"
ENABLE_SYNC_ENGINE = os.getenv("ENABLE_SYNC_ENGINE", "true").lower() == "true"
ENABLE_GATEWAY_HEALTH_WORKER = os.getenv("ENABLE_GATEWAY_HEALTH_WORKER", "true").lower() == "true"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting STOA Control-Plane API", version=settings.VERSION, environment=settings.ENVIRONMENT)

    # Initialize services
    worker_task = None
    try:
        await kafka_service.connect()
        logger.info("Kafka connected")
    except Exception as e:
        logger.warning("Failed to connect Kafka", error=str(e))

    try:
        await git_service.connect()
        logger.info("GitLab connected")
    except Exception as e:
        logger.warning("Failed to connect GitLab", error=str(e))

    try:
        await awx_service.connect()
        logger.info("AWX connected")
    except Exception as e:
        logger.warning("Failed to connect AWX", error=str(e))

    try:
        await keycloak_service.connect()
        logger.info("Keycloak connected")
    except Exception as e:
        logger.warning("Failed to connect Keycloak", error=str(e))

    try:
        await gateway_service.connect()
        logger.info("Gateway connected", oidc_proxy=settings.GATEWAY_USE_OIDC_PROXY)
    except Exception as e:
        logger.warning("Failed to connect Gateway", error=str(e))

    try:
        await argocd_service.connect()
        logger.info("ArgoCD connected")
    except Exception as e:
        logger.warning("Failed to connect ArgoCD", error=str(e))

    # Initialize Metrics Service (CAB-840) - Prometheus + Loki clients
    try:
        await metrics_service.connect()
        logger.info("Metrics service connected (Prometheus + Loki)")
    except Exception as e:
        logger.warning("Failed to connect metrics service", error=str(e))

    # Initialize OpenSearch (CAB-307)
    try:
        await setup_opensearch(app)
        logger.info("OpenSearch connected")
    except Exception as e:
        logger.warning("Failed to connect OpenSearch", error=str(e))

    # Start deployment worker in background
    if ENABLE_WORKER:
        try:
            worker_task = asyncio.create_task(deployment_worker.start())
            logger.info("Deployment worker started")
        except Exception as e:
            logger.warning("Failed to start deployment worker", error=str(e))

    # Connect error snapshots storage (CAB-397)
    # Note: Middleware is added at module level after app creation
    try:
        snapshot_service = await connect_error_snapshots()
        if snapshot_service:
            logger.info("Error snapshots connected")
    except Exception as e:
        logger.warning("Failed to connect error snapshots", error=str(e))

    # Start error snapshot consumer for gateway snapshots (CAB-485)
    snapshot_consumer_task = None
    if ENABLE_SNAPSHOT_CONSUMER:
        try:
            snapshot_consumer_task = asyncio.create_task(error_snapshot_consumer.start())
            logger.info("Error snapshot consumer started")
        except Exception as e:
            logger.warning("Failed to start error snapshot consumer", error=str(e))

    # Start gateway sync engine (Control Plane Agnostique)
    sync_engine_task = None
    if ENABLE_SYNC_ENGINE and settings.SYNC_ENGINE_ENABLED:
        try:
            sync_engine_task = asyncio.create_task(sync_engine.start())
            logger.info("Gateway sync engine started")
        except Exception as e:
            logger.warning("Failed to start sync engine", error=str(e))

    # Start gateway health worker (ADR-028 auto-registration)
    gateway_health_task = None
    if ENABLE_GATEWAY_HEALTH_WORKER:
        try:
            gateway_health_task = asyncio.create_task(gateway_health_worker.start())
            logger.info("Gateway health worker started")
        except Exception as e:
            logger.warning("Failed to start gateway health worker", error=str(e))

    yield

    # Shutdown
    logger.info("Shutting down...")

    # Stop deployment worker
    if ENABLE_WORKER and worker_task:
        await deployment_worker.stop()
        worker_task.cancel()
        with suppress(asyncio.CancelledError):
            await worker_task

    # Stop error snapshot consumer
    if ENABLE_SNAPSHOT_CONSUMER and snapshot_consumer_task:
        await error_snapshot_consumer.stop()
        snapshot_consumer_task.cancel()
        with suppress(asyncio.CancelledError):
            await snapshot_consumer_task

    # Stop gateway sync engine
    if ENABLE_SYNC_ENGINE and sync_engine_task:
        await sync_engine.stop()
        sync_engine_task.cancel()
        with suppress(asyncio.CancelledError):
            await sync_engine_task

    # Stop gateway health worker
    if ENABLE_GATEWAY_HEALTH_WORKER and gateway_health_task:
        await gateway_health_worker.stop()
        gateway_health_task.cancel()
        with suppress(asyncio.CancelledError):
            await gateway_health_task

    await kafka_service.disconnect()
    await git_service.disconnect()
    await awx_service.disconnect()
    await keycloak_service.disconnect()
    await gateway_service.disconnect()
    await argocd_service.disconnect()
    await metrics_service.disconnect()

    # Flush remaining OTel spans before exit (CAB-1088)
    shutdown_tracing()

API_DESCRIPTION = """
## STOA Platform API

**The European Agent Gateway** — AI-Native API Gateway for modern enterprises.

### Key Features

- **MCP Server Subscriptions** — Subscribe to AI tools and manage API keys
- **Tools Catalog** — Browse and discover MCP tools with role-based visibility
- **Usage Tracking** — Monitor your API consumption in real-time
- **Multi-tenant Management** — Create and manage isolated API tenants
- **GitOps Integration** — Automatic sync with GitLab repositories
- **Event-Driven Architecture** — Kafka/Redpanda message bus for async operations
- **Pipeline Monitoring** — End-to-end tracing of deployments
- **RBAC** — Role-based access control via Keycloak

### Quick Start

1. **Get a token** from Keycloak (`POST /realms/stoa/protocol/openid-connect/token`)
2. **Browse MCP servers** (`GET /v1/mcp/servers`)
3. **Subscribe to a server** (`POST /v1/mcp/subscriptions`)
4. **Use your API key** with MCP Gateway (`https://mcp.gostoa.dev`)

### Authentication

All endpoints require a valid JWT token from Keycloak (realm: `stoa`).
Include the token in the `Authorization: Bearer <token>` header.

```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Environments

| Environment | Base URL |
|-------------|----------|
| Production | `https://api.gostoa.dev` |
| Via Gateway | `https://apis.gostoa.dev/gateway/Control-Plane-API/2.0` |

### Changelog

#### v2.1.0 (Current)
- Added MCP Server Subscriptions with admin approval workflow
- Added API key rotation with grace period support
- Added Dashboard home page stats (`/v1/dashboard`)
- Added Service Accounts for M2M authentication

#### v2.0.0
- Added Pipeline Tracing (`/v1/traces`) for end-to-end monitoring
- Added GitLab Webhook integration (`/webhooks/gitlab`)
- Added Kafka integration for event-driven deployments
- Added AWX integration for automated Gateway deployments

#### v1.0.0
- Initial release with tenant, API, and application management
"""

app = FastAPI(
    title="STOA Control-Plane API",
    description=API_DESCRIPTION,
    version=settings.VERSION,
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Tenants", "description": "Tenant management operations"},
        {"name": "APIs", "description": "API lifecycle management"},
        {"name": "Applications", "description": "Application and subscription management"},
        {"name": "Deployments", "description": "Deployment operations and status"},
        {"name": "Git", "description": "GitLab integration (commits, MRs, files)"},
        {"name": "Events", "description": "Real-time event streaming (SSE)"},
        {"name": "Webhooks", "description": "GitLab webhook handlers for GitOps"},
        {"name": "Traces", "description": "Pipeline monitoring and tracing"},
        {"name": "Gateway", "description": "webMethods Gateway administration via OIDC proxy"},
        {"name": "Subscriptions", "description": "API subscription and API key management"},
        {"name": "Tenant Webhooks", "description": "Webhook notifications for subscription events (CAB-315)"},
        {"name": "certificates", "description": "Certificate validation for mTLS subscriptions (CAB-313)"},
        {"name": "Search", "description": "Full-text search across tools and APIs (CAB-307)"},
        {"name": "Usage", "description": "Usage dashboard for API consumers (CAB-280)"},
        {"name": "Dashboard", "description": "Home dashboard stats and activity (CAB-299)"},
        {"name": "Service Accounts", "description": "OAuth2 Service Accounts for MCP access (CAB-296)"},
        {"name": "Contracts", "description": "Universal API Contracts with multi-protocol bindings (UAC)"},
        {"name": "MCP Servers", "description": "Browse and discover MCP servers"},
        {"name": "MCP Subscriptions", "description": "Subscribe to MCP servers and manage API keys"},
        {"name": "MCP Validation", "description": "API key validation for MCP Gateway (internal)"},
        {"name": "MCP Admin - Subscriptions", "description": "Admin approval workflow for MCP subscriptions"},
        {"name": "MCP Admin - Servers", "description": "MCP server management (admin)"},
        {"name": "Portal", "description": "Developer Portal API catalog and MCP server browsing"},
        {"name": "MCP GitOps", "description": "GitOps synchronization for MCP servers"},
        {"name": "MCP Tools", "description": "MCP tools discovery and invocation (proxy to MCP Gateway)"},
        {"name": "Platform", "description": "Platform status and GitOps observability (CAB-654)"},
        {"name": "Gateways", "description": "Gateway instance management (multi-gateway orchestration)"},
        {"name": "Gateway Deployments", "description": "API deployment to gateways (sync engine)"},
        {"name": "Gateway Policies", "description": "Gateway-agnostic policy management"},
        {"name": "Gateway Observability", "description": "Multi-gateway health and sync metrics"},
        {"name": "Gateway Internal", "description": "Internal gateway auto-registration (ADR-028)"},
        {"name": "Consumers", "description": "Consumer onboarding and lifecycle management (CAB-1121)"},
        {"name": "Plans", "description": "Subscription plan management with quotas (CAB-1121)"},
        {"name": "Quotas", "description": "Quota enforcement and usage monitoring (CAB-1121 Phase 4)"},
    ],
    contact={
        "name": "CAB Ingénierie",
        "url": "https://gostoa.dev",
        "email": "support@gostoa.dev",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
    docs_url="/docs",
    redoc_url="/redoc",
)

# OpenTelemetry distributed tracing (CAB-1088)
# Must be configured before middleware so FastAPI auto-instrumentation works
configure_tracing(app, settings)

# Rate limiting (CAB-298)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)


# === CAB-1122: Global exception handlers — structured error taxonomy ===
@app.exception_handler(sqlalchemy.exc.IntegrityError)
async def integrity_error_handler(request: Request, exc: sqlalchemy.exc.IntegrityError) -> JSONResponse:
    detail = str(exc.orig) if exc.orig else str(exc)
    logger.warning("Database integrity error", path=str(request.url.path), detail=detail)
    return JSONResponse(
        status_code=409, content={"detail": "Conflict: a resource with this identifier already exists."}
    )


@app.exception_handler(sqlalchemy.exc.OperationalError)
async def operational_error_handler(request: Request, exc: sqlalchemy.exc.OperationalError) -> JSONResponse:
    logger.error("Database operational error", path=str(request.url.path), error=str(exc))
    return JSONResponse(status_code=503, content={"detail": "Database service unavailable. Please retry later."})


@app.exception_handler(httpx.HTTPError)
async def httpx_error_handler(request: Request, exc: httpx.HTTPError) -> JSONResponse:
    logger.error("External service error", path=str(request.url.path), error=str(exc))
    return JSONResponse(status_code=502, content={"detail": "An upstream service is unavailable."})


@app.exception_handler(Exception)
async def catch_all_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled exception", path=str(request.url.path), error_type=type(exc).__name__, error=str(exc)
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


# GZip compression for responses > 1KB (reduces JSON payload size by ~70%)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics middleware
app.add_middleware(MetricsMiddleware)

# HTTP request/response logging middleware (CAB-330)
if settings.LOG_HTTP_MIDDLEWARE_ENABLED:
    app.add_middleware(HTTPLoggingMiddleware)

# Error Snapshots middleware (CAB-397) - captures request/response on errors
# Must be added before app startup, connects to storage in lifespan
add_error_snapshot_middleware(app)

# Audit middleware (CAB-307) - logs all API requests to OpenSearch
# Note: AuditMiddleware is added dynamically via setup_opensearch()

# Routers
app.include_router(tenants.router)
app.include_router(apis.router)
# CAB-1122: Applications router disabled — requires Keycloak service implementation
# app.include_router(applications.router)
app.include_router(deployments.router)
app.include_router(git.router)
app.include_router(events.router)
app.include_router(webhooks.router)
app.include_router(traces.router)
app.include_router(gateway.router)
app.include_router(subscriptions.router)
app.include_router(tenant_webhooks.router)
app.include_router(certificates.router)
app.include_router(search_router, prefix="/v1/search", tags=["Search"])
app.include_router(usage.router)
app.include_router(usage.dashboard_router)
app.include_router(service_accounts.router)
app.include_router(health.router)

# Contracts router (UAC Protocol Switcher)
app.include_router(contracts.router)

# MCP Server Subscription routers
app.include_router(mcp_servers_router)
app.include_router(mcp_subscriptions_router)
app.include_router(mcp_validation_router)
app.include_router(mcp_admin_subscriptions_router)
app.include_router(mcp_admin_servers_router)

# External MCP Servers (Linear, GitHub, etc.)
app.include_router(external_mcp_servers_admin_router)
app.include_router(external_mcp_servers_internal_router)

# Portal and GitOps routers
app.include_router(portal.router)
app.include_router(portal_applications.router)
app.include_router(mcp_gitops.router)

# MCP Tools proxy router (proxies to MCP Gateway)
app.include_router(mcp_proxy.router)

# MCP Policy proxy router (CAB-875 - proxies policy management to MCP Gateway)
app.include_router(mcp_policy_proxy.router)

# API Monitoring
app.include_router(monitoring.router)

# Platform Status (GitOps Observability - CAB-654)
app.include_router(platform.router)

# Catalog Admin (CAB-682 - Catalog Cache Sync)
app.include_router(catalog_admin.router)

# Admin Prospects Dashboard (CAB-911 - Conversion Cockpit)
app.include_router(admin_prospects.router)

# Operations and Business Analytics (CAB-Observability)
app.include_router(operations.router)
app.include_router(business.router)

# User profile and permissions (Single Source of Truth for RBAC)
app.include_router(users.router)

# Self-Service Logs (CAB-793 - Consumer log access with PII masking)
app.include_router(self_service_logs.router)

# Gateway Orchestration (Control Plane Agnostique)
# IMPORTANT: observability router BEFORE gateway_instances (path ordering for /metrics vs /{gateway_id})
app.include_router(gateway_observability.router)
app.include_router(gateway_instances.router)
app.include_router(gateway_deployments.router)
app.include_router(gateway_policies.router)
# Internal gateway registration API (ADR-028 auto-registration)
app.include_router(gateway_internal.router)

# Consumer Onboarding (CAB-1121)
app.include_router(consumers.router)
app.include_router(plans.router)

# Quota Enforcement (CAB-1121 Phase 4)
app.include_router(quotas.router)


# Legacy health endpoint - redirect to new /health/live
@app.get("/health", include_in_schema=False)
async def health_legacy():
    """Legacy health endpoint for backward compatibility."""
    return {"status": "healthy", "version": settings.VERSION}

@app.get("/")
async def root():
    return {
        "name": "STOA Control-Plane API",
        "version": settings.VERSION,
        "docs": "/docs",
    }


@app.get("/metrics", include_in_schema=False)
async def metrics():
    """Prometheus metrics endpoint."""
    return get_metrics()


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    """Serve STOA favicon."""
    static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
    favicon_path = os.path.join(static_dir, "favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/svg+xml")
    return Response(status_code=204)
