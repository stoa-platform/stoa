"""
STOA Control-Plane API
FastAPI backend with RBAC, GitOps, and Kafka integration
"""
import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from starlette.responses import Response
from contextlib import asynccontextmanager

from slowapi.errors import RateLimitExceeded

from .config import settings
from .logging_config import configure_logging, get_logger
from .routers import tenants, apis, applications, deployments, git, events, webhooks, traces, gateway, subscriptions, tenant_webhooks, certificates, usage, service_accounts, health, contracts, monitoring, users
from .routers.mcp import servers_router as mcp_servers_router, subscriptions_router as mcp_subscriptions_router, validation_router as mcp_validation_router
from .routers.mcp_admin import admin_subscriptions_router as mcp_admin_subscriptions_router, admin_servers_router as mcp_admin_servers_router
from .routers import portal, mcp_gitops, mcp_proxy, platform, portal_applications, catalog_admin
from .opensearch import search_router, AuditMiddleware, setup_opensearch
from .services import kafka_service, git_service, awx_service, keycloak_service, argocd_service, metrics_service
# Note: These are now imported as instances, not modules
from .middleware.metrics import MetricsMiddleware, get_metrics
from .middleware.rate_limit import limiter, rate_limit_exceeded_handler
from .middleware.http_logging import HTTPLoggingMiddleware
from .services.gateway_service import gateway_service
from .workers.deployment_worker import deployment_worker
from .workers.error_snapshot_consumer import error_snapshot_consumer
from .features.error_snapshots import add_error_snapshot_middleware, connect_error_snapshots

# Configure structured logging (CAB-281)
configure_logging()
logger = get_logger(__name__)

# Flag to control worker startup (can be disabled for dev/testing)
ENABLE_WORKER = os.getenv("ENABLE_DEPLOYMENT_WORKER", "true").lower() == "true"
ENABLE_SNAPSHOT_CONSUMER = os.getenv("ENABLE_SNAPSHOT_CONSUMER", "true").lower() == "true"

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

    yield

    # Shutdown
    logger.info("Shutting down...")

    # Stop deployment worker
    if ENABLE_WORKER and worker_task:
        await deployment_worker.stop()
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    # Stop error snapshot consumer
    if ENABLE_SNAPSHOT_CONSUMER and snapshot_consumer_task:
        await error_snapshot_consumer.stop()
        snapshot_consumer_task.cancel()
        try:
            await snapshot_consumer_task
        except asyncio.CancelledError:
            pass

    await kafka_service.disconnect()
    await git_service.disconnect()
    await awx_service.disconnect()
    await keycloak_service.disconnect()
    await gateway_service.disconnect()
    await argocd_service.disconnect()
    await metrics_service.disconnect()

API_DESCRIPTION = """
## STOA Platform API

**The Cilium of API Management** — AI-Native API Gateway for modern enterprises.

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
4. **Use your API key** with MCP Gateway (`https://mcp.stoa.cab-i.com`)

### Authentication

All endpoints require a valid JWT token from Keycloak (realm: `stoa`).
Include the token in the `Authorization: Bearer <token>` header.

```
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### Environments

| Environment | Base URL |
|-------------|----------|
| Production | `https://api.stoa.cab-i.com` |
| Via Gateway | `https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0` |

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
    ],
    contact={
        "name": "CAB Ingénierie",
        "url": "https://stoa.cab-i.com",
        "email": "support@cab-i.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0",
    },
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting (CAB-298)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

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
app.include_router(applications.router)
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

# Portal and GitOps routers
app.include_router(portal.router)
app.include_router(portal_applications.router)
app.include_router(mcp_gitops.router)

# MCP Tools proxy router (proxies to MCP Gateway)
app.include_router(mcp_proxy.router)

# API Monitoring
app.include_router(monitoring.router)

# Platform Status (GitOps Observability - CAB-654)
app.include_router(platform.router)

# Catalog Admin (CAB-682 - Catalog Cache Sync)
app.include_router(catalog_admin.router)

# User profile and permissions (Single Source of Truth for RBAC)
app.include_router(users.router)


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
