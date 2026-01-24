"""Error Snapshot feature for time-travel debugging.

CAB-397: Captures complete request/response context when errors occur,
enabling developers to debug issues by replaying the exact state
at the time of the error.

Usage:
    # 1. Add middleware at app creation (before startup)
    from src.features.error_snapshots import add_error_snapshot_middleware
    add_error_snapshot_middleware(app)

    # 2. Connect storage in lifespan
    from src.features.error_snapshots import connect_error_snapshots
    async def lifespan(app: FastAPI):
        await connect_error_snapshots()
        yield

Features:
- Automatic capture on 4xx/5xx errors (configurable)
- PII masking for sensitive data
- MinIO/S3 storage with compression
- Date-based partitioning for efficient queries
- Tenant isolation
- cURL replay generation
"""

import logging

from fastapi import FastAPI

from .config import SnapshotSettings, get_snapshot_settings
from .masking import MaskingConfig, PIIMasker, mask_request
from .middleware import ErrorSnapshotMiddleware, SimpleErrorSnapshotMiddleware
from .models import (
    BackendState,
    EnvironmentInfo,
    ErrorSnapshot,
    LogEntry,
    PolicyResult,
    ReplayResponse,
    RequestSnapshot,
    ResponseSnapshot,
    RoutingInfo,
    SnapshotFilters,
    SnapshotListResponse,
    SnapshotSummary,
    SnapshotTrigger,
)
from .router import router as snapshot_router, set_snapshot_service
from .service import SnapshotService
from .storage import SnapshotStorage

logger = logging.getLogger(__name__)

# Module-level singleton for the service
_snapshot_service: SnapshotService | None = None
_snapshot_storage: SnapshotStorage | None = None
_settings: SnapshotSettings | None = None

__all__ = [
    # Models
    "ErrorSnapshot",
    "SnapshotTrigger",
    "SnapshotListResponse",
    "SnapshotSummary",
    "SnapshotFilters",
    "RequestSnapshot",
    "ResponseSnapshot",
    "RoutingInfo",
    "PolicyResult",
    "BackendState",
    "LogEntry",
    "EnvironmentInfo",
    "ReplayResponse",
    # Masking
    "PIIMasker",
    "MaskingConfig",
    "mask_request",
    # Config
    "SnapshotSettings",
    "get_snapshot_settings",
    # Storage
    "SnapshotStorage",
    # Service
    "SnapshotService",
    # Middleware
    "ErrorSnapshotMiddleware",
    "SimpleErrorSnapshotMiddleware",
    # Router
    "snapshot_router",
    # Setup functions
    "add_error_snapshot_middleware",
    "connect_error_snapshots",
    "get_snapshot_service",
    # Legacy
    "setup_error_snapshots",
]


def add_error_snapshot_middleware(app: FastAPI) -> bool:
    """Add error snapshot middleware to the FastAPI app.

    MUST be called after app creation but before startup.
    This sets up the middleware and router, but does not connect to storage.

    Args:
        app: FastAPI application instance

    Returns:
        True if middleware was added, False if feature is disabled
    """
    global _settings, _snapshot_storage, _snapshot_service

    _settings = get_snapshot_settings()

    if not _settings.enabled:
        logger.info("error_snapshots_disabled")
        return False

    try:
        # Initialize storage and service (not connected yet)
        _snapshot_storage = SnapshotStorage(_settings)
        _snapshot_service = SnapshotService(_snapshot_storage, _settings)

        # Set service for router dependency injection
        set_snapshot_service(_snapshot_service)

        # Add middleware (must be done before app startup)
        app.add_middleware(ErrorSnapshotMiddleware, service=_snapshot_service)

        # Add router
        app.include_router(snapshot_router)

        logger.info(
            f"error_snapshots_middleware_added capture_4xx={_settings.capture_on_4xx} "
            f"capture_5xx={_settings.capture_on_5xx}"
        )

        return True

    except Exception as e:
        logger.error(f"error_snapshots_middleware_failed: {e}", exc_info=True)
        return False


async def connect_error_snapshots() -> SnapshotService | None:
    """Connect to storage backend.

    Call this in your FastAPI lifespan after the app has started.

    Returns:
        SnapshotService instance or None if not enabled/failed
    """
    global _snapshot_storage, _snapshot_service, _settings

    if _snapshot_storage is None or _settings is None:
        return None

    try:
        await _snapshot_storage.connect()

        logger.info(
            f"error_snapshots_connected bucket={_settings.storage_bucket} "
            f"retention_days={_settings.retention_days}"
        )

        return _snapshot_service

    except Exception as e:
        logger.error(f"error_snapshots_connection_failed: {e}", exc_info=True)
        return None


def get_snapshot_service() -> SnapshotService | None:
    """Get the current snapshot service instance."""
    return _snapshot_service


async def setup_error_snapshots(app: FastAPI) -> SnapshotService | None:
    """Legacy function - Initialize error snapshot feature.

    DEPRECATED: Use add_error_snapshot_middleware() + connect_error_snapshots()
    instead for proper FastAPI lifecycle handling.

    This function tries to add middleware which will fail if called from lifespan.
    """
    logger.warning("setup_error_snapshots is deprecated, use add_error_snapshot_middleware + connect_error_snapshots")

    settings = get_snapshot_settings()

    if not settings.enabled:
        logger.info("error_snapshots_disabled")
        return None

    try:
        # Initialize storage
        storage = SnapshotStorage(settings)
        await storage.connect()

        # Initialize service
        service = SnapshotService(storage, settings)

        # Set service for router dependency injection
        set_snapshot_service(service)

        # This will fail if called from lifespan
        app.add_middleware(ErrorSnapshotMiddleware, service=service)

        # Add router
        app.include_router(snapshot_router)

        logger.info(
            f"error_snapshots_enabled bucket={settings.storage_bucket} "
            f"capture_4xx={settings.capture_on_4xx} capture_5xx={settings.capture_on_5xx} "
            f"capture_timeout={settings.capture_on_timeout} retention_days={settings.retention_days}"
        )

        return service

    except Exception as e:
        logger.error(f"error_snapshots_setup_failed: {e}", exc_info=True)
        # Don't crash the app if snapshots fail to initialize
        return None
