# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""STOA Control Plane - FastAPI Application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from control_plane import __version__
from control_plane.api.v1.invites import limiter
from control_plane.api.v1.router import router as api_router
from control_plane.api.v1.router import welcome_router
from control_plane.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    yield
    # Shutdown


app = FastAPI(
    title="STOA Control Plane",
    description="API for managing invites, events, and prospect tracking",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Configure CORS - CAB-1018: Restrict origins for security
ALLOWED_ORIGINS = [
    "https://gostoa.dev",
    "https://demo.gostoa.dev",
    "https://console.gostoa.dev",
    "https://portal.gostoa.dev",
    "https://api.gostoa.dev",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
)

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get(
    "/health",
    tags=["health"],
    summary="Health check",
    description="Returns health status of the API.",
)
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": __version__,
        "service": settings.app_name,
    }


@app.get(
    "/",
    tags=["root"],
    summary="API root",
    description="Returns API information.",
)
async def root():
    """Root endpoint with API info."""
    return {
        "service": "STOA Control Plane",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


# Include routers
app.include_router(api_router)
app.include_router(welcome_router)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": {
                "code": "internal_error",
                "message": "An internal error occurred",
            }
        },
    )
