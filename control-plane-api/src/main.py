"""
APIM Control-Plane API
FastAPI backend with RBAC, GitOps, and Kafka integration
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .routers import tenants, apis, applications, deployments, git, events
from .services import kafka_service, git_service, awx_service, keycloak_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"Starting APIM Control-Plane API v{settings.VERSION}")

    # Initialize services
    try:
        await kafka_service.kafka_service.connect()
        await git_service.git_service.connect()
        await awx_service.awx_service.connect()
        await keycloak_service.keycloak_service.connect()
        print("All services connected")
    except Exception as e:
        print(f"Warning: Failed to connect some services: {e}")

    yield

    # Shutdown
    print("Shutting down...")
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
