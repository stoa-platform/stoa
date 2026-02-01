"""Portal Executions router — consumer execution view endpoints.

CAB-432: Provides "My Executions" endpoints for the Developer Portal.
Consumer sees WHAT happened, never HOW.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ...auth.dependencies import User, get_current_user
from .models import ExecutionError, ExecutionSummary
from .service import PortalExecutionsService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/portal/apps",
    tags=["Portal Executions"],
)

_service: PortalExecutionsService | None = None


def set_executions_service(service: PortalExecutionsService) -> None:
    """Set the service instance (called during app startup)."""
    global _service
    _service = service


def _get_service() -> PortalExecutionsService:
    """Get the executions service or raise 503."""
    if _service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Portal executions service not initialized",
        )
    return _service


@router.get(
    "/{app_id}/executions",
    response_model=ExecutionSummary,
    summary="Get execution summary for an application",
    description=(
        "Returns aggregated stats and recent errors for a consumer application. "
        "Includes degraded mode when backend services are unavailable."
    ),
)
async def get_executions(
    app_id: str,
    user: User = Depends(get_current_user),
    service: PortalExecutionsService = Depends(_get_service),
) -> ExecutionSummary:
    """Get execution summary with stats and recent errors."""
    try:
        return await service.get_execution_summary(app_id, user)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Application {app_id} not found",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        ) from exc
    except Exception as e:
        logger.error(f"get_executions_failed app={app_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Execution data temporarily unavailable",
        ) from e


@router.get(
    "/{app_id}/executions/{error_id}",
    response_model=ExecutionError,
    summary="Get error detail for support escalation",
    description=(
        "Returns classified error information with help text and suggested actions. "
        "Use the trace_id to escalate to support."
    ),
)
async def get_error_detail(
    app_id: str,
    error_id: str,
    user: User = Depends(get_current_user),
    service: PortalExecutionsService = Depends(_get_service),
) -> ExecutionError:
    """Get detailed error info for escalation."""
    try:
        error = await service.get_error_detail(app_id, error_id, user)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        ) from exc
    except Exception as e:
        logger.error(f"get_error_detail_failed app={app_id} error={error_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Error detail temporarily unavailable",
        ) from e

    if error is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Error {error_id} not found",
        )

    return error
