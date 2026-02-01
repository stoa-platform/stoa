"""Portal Executions feature — Consumer Execution View.

CAB-432: Provides "My Executions" view for API Consumers in the
Developer Portal with simplified error taxonomy.

Usage:
    from src.features.portal_executions import setup_portal_executions
    setup_portal_executions(app)
"""

import logging

from fastapi import FastAPI

from .classifier import classify_error
from .config import PortalExecutionsSettings, get_portal_executions_settings
from .models import (
    ErrorCategory,
    ErrorSource,
    ExecutionError,
    ExecutionStats,
    ExecutionSummary,
)
from .router import router as portal_executions_router, set_executions_service
from .service import PortalExecutionsService

logger = logging.getLogger(__name__)

_service: PortalExecutionsService | None = None

__all__ = [
    "ErrorCategory",
    "ErrorSource",
    "ExecutionError",
    "ExecutionStats",
    "ExecutionSummary",
    "PortalExecutionsService",
    "PortalExecutionsSettings",
    "classify_error",
    "get_portal_executions_settings",
    "portal_executions_router",
    "setup_portal_executions",
]


def setup_portal_executions(app: FastAPI) -> bool:
    """Register portal executions feature on the FastAPI app.

    Args:
        app: FastAPI application instance.

    Returns:
        True if feature was registered, False if disabled.
    """
    global _service

    settings = get_portal_executions_settings()

    if not settings.enabled:
        logger.info("portal_executions_disabled")
        return False

    try:
        _service = PortalExecutionsService(settings)
        set_executions_service(_service)
        app.include_router(portal_executions_router)
        logger.info(
            f"portal_executions_enabled "
            f"error_window_hours={settings.error_window_hours} "
            f"max_errors={settings.max_errors}"
        )
        return True

    except Exception as e:
        logger.error(f"portal_executions_setup_failed: {e}", exc_info=True)
        return False


def get_executions_service() -> PortalExecutionsService | None:
    """Get the current portal executions service instance."""
    return _service
