"""
STOA Control-Plane API
FastAPI backend with RBAC, GitOps, and Kafka integration
"""
import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .routers import tenants, apis, applications, deployments, git, events, webhooks, traces, gateway
from .services import kafka_service, git_service, awx_service, keycloak_service
from .middleware.metrics import MetricsMiddleware, get_metrics
from .services.gateway_service import gateway_service
from .workers.deployment_worker import deployment_worker

# Flag to control worker startup (can be disabled for dev/testing)
ENABLE_WORKER = os.getenv("ENABLE_DEPLOYMENT_WORKER", "true").lower() == "true"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"Starting STOA Control-Plane API v{settings.VERSION}")

    # Initialize services
    worker_task = None
    try:
        await kafka_service.kafka_service.connect()
        print("Kafka connected")
    except Exception as e:
        print(f"Warning: Failed to connect Kafka: {e}")

    try:
        await git_service.git_service.connect()
        print("GitLab connected")
    except Exception as e:
        print(f"Warning: Failed to connect GitLab: {e}")

    try:
        await awx_service.awx_service.connect()
        print("AWX connected")
    except Exception as e:
        print(f"Warning: Failed to connect AWX: {e}")

    try:
        await keycloak_service.keycloak_service.connect()
        print("Keycloak connected")
    except Exception as e:
        print(f"Warning: Failed to connect Keycloak: {e}")

    try:
        await gateway_service.connect()
        print(f"Gateway connected (OIDC proxy: {settings.GATEWAY_USE_OIDC_PROXY})")
    except Exception as e:
        print(f"Warning: Failed to connect Gateway: {e}")

    # Start deployment worker in background
    if ENABLE_WORKER:
        try:
            worker_task = asyncio.create_task(deployment_worker.start())
            print("Deployment worker started")
        except Exception as e:
            print(f"Warning: Failed to start deployment worker: {e}")

    yield

    # Shutdown
    print("Shutting down...")

    # Stop deployment worker
    if ENABLE_WORKER and worker_task:
        await deployment_worker.stop()
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass

    await kafka_service.kafka_service.disconnect()
    await git_service.git_service.disconnect()
    await awx_service.awx_service.disconnect()
    await keycloak_service.keycloak_service.disconnect()
    await gateway_service.disconnect()

API_DESCRIPTION = """
## STOA Control-Plane API

Multi-tenant API Management Control Plane with GitOps integration.

### Features

- **Multi-tenant Management**: Create and manage isolated API tenants
- **API Lifecycle**: Full CRUD operations for APIs with versioning
- **GitOps Integration**: Automatic sync with GitLab repositories
- **Event-Driven Architecture**: Kafka/Redpanda message bus for async operations
- **Pipeline Monitoring**: End-to-end tracing of deployments
- **RBAC**: Role-based access control via Keycloak

### Changelog

#### v2.0.0 (Current)
- Added Pipeline Tracing (`/v1/traces`) for end-to-end monitoring
- Added GitLab Webhook integration (`/webhooks/gitlab`)
- Added Kafka integration for event-driven deployments
- Added AWX integration for automated Gateway deployments

#### v1.0.0
- Initial release with tenant, API, and application management
- Basic deployment endpoints
- Git operations (commits, merge requests)

### Authentication

All endpoints require a valid JWT token from Keycloak (realm: `stoa`).
Include the token in the `Authorization: Bearer <token>` header.
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
    ],
    contact={
        "name": "CAB Ingenierie",
        "email": "admin@cab-i.com",
    },
    license_info={
        "name": "Proprietary",
    },
)

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

@app.get("/health")
async def health():
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
