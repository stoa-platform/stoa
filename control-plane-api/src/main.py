"""
APIM Control-Plane API
FastAPI backend with RBAC, GitOps, and Kafka integration
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .routers import tenants, apis, applications, deployments, git, events

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"Starting APIM Control-Plane API v{settings.VERSION}")
    yield
    # Shutdown
    print("Shutting down...")

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
