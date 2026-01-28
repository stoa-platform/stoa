# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""STOA Mock Backends - FastAPI Application.

CAB-1018: Mock APIs for Central Bank Demo
Provides mock implementations of:
- Fraud Detection API (circuit breaker pattern)
- Settlement API (idempotency + saga pattern)
- Sanctions Screening API (semantic cache pattern)
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.logging_config import configure_logging, get_logger
from src.middleware import DemoHeadersMiddleware, TraceIdMiddleware, MetricsMiddleware
from src.routers import health_router, fraud_router, settlement_router, sanctions_router, demo_router

# Configure logging first
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    logger.info(
        "Starting Mock Backends service",
        version=settings.app_version,
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        demo_scenarios_enabled=settings.demo_scenarios_enabled,
    )

    yield

    # Shutdown
    logger.info("Shutting down Mock Backends service")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="""
## STOA Mock Backends - Central Bank Demo (CAB-1018)

Mock implementations of enterprise banking APIs for demonstrating STOA Platform patterns.

### APIs
- **Fraud Detection**: Circuit breaker pattern demonstration
- **Settlement**: Idempotency + saga rollback pattern
- **Sanctions Screening**: Semantic cache pattern

### Demo Features
- `X-Demo-Mode: true` header on all responses
- `X-Data-Classification: SYNTHETIC` header
- `/demo/trigger/*` endpoints for scenario control

### Note
All data is 100% synthetic. Auth is bypassed for demo purposes.
    """,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    openapi_tags=[
        {"name": "Health", "description": "Health check and metrics endpoints"},
        {"name": "Fraud Detection", "description": "Transaction fraud scoring API"},
        {"name": "Settlement", "description": "Settlement processing API"},
        {"name": "Sanctions Screening", "description": "Entity sanctions screening API"},
        {"name": "Demo", "description": "Demo scenario trigger endpoints"},
    ],
)

# Add middleware (order matters - executed in reverse order)
# 1. CORS (outermost) - CAB-1018: Whitelist origins
DEMO_ALLOWED_ORIGINS = [
    "https://gostoa.dev",
    "https://demo.gostoa.dev",
    "https://console.gostoa.dev",
    "https://portal.gostoa.dev",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://localhost:8090",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=DEMO_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID", "Idempotency-Key"],
)

# 2. Metrics middleware
if settings.metrics_enabled:
    app.add_middleware(MetricsMiddleware)

# 3. Trace ID middleware
app.add_middleware(TraceIdMiddleware)

# 4. Demo headers middleware (innermost)
app.add_middleware(DemoHeadersMiddleware)

# Register routers
app.include_router(health_router)
app.include_router(fraud_router, prefix="/v1", tags=["Fraud Detection"])
app.include_router(settlement_router, prefix="/v1", tags=["Settlement"])
app.include_router(sanctions_router, prefix="/v1", tags=["Sanctions Screening"])

# Demo router (only when enabled)
if settings.demo_scenarios_enabled:
    app.include_router(demo_router, prefix="/demo", tags=["Demo"])


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint - redirect to docs."""
    return {
        "service": "STOA Mock Backends",
        "version": settings.app_version,
        "demo_mode": settings.demo_mode,
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
