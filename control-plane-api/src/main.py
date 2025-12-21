"""
APIM Control-Plane API
FastAPI backend with RBAC, GitOps, and Kafka integration
"""
import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .routers import tenants, apis, applications, deployments, git, events, webhooks
from .services import kafka_service, git_service, awx_service, keycloak_service
from .workers.deployment_worker import deployment_worker

# Flag to control worker startup (can be disabled for dev/testing)
ENABLE_WORKER = os.getenv("ENABLE_DEPLOYMENT_WORKER", "true").lower() == "true"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"Starting APIM Control-Plane API v{settings.VERSION}")

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

app = FastAPI(
    title="APIM Control-Plane API",
    description="Multi-tenant API Management Control Plane",
    version=settings.VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(tenants.router)
app.include_router(apis.router)
app.include_router(applications.router)
app.include_router(deployments.router)
app.include_router(git.router)
app.include_router(events.router)
app.include_router(webhooks.router)

@app.get("/health")
async def health():
    return {"status": "healthy", "version": settings.VERSION}

@app.get("/")
async def root():
    return {
        "name": "APIM Control-Plane API",
        "version": settings.VERSION,
        "docs": "/docs",
    }
