"""Internal billing API for gateway budget enforcement (CAB-1457).

Gateway calls GET /internal/budgets/{department_id}/check every ~60s
to determine if a department is over budget. Fail-open: 404 or error = allow.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.schemas.billing import BudgetCheckResponse
from src.services.billing_service import BillingService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/internal/budgets",
    tags=["Internal - Billing"],
)


@router.get("/{department_id}/check", response_model=BudgetCheckResponse)
async def check_department_budget(
    department_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Check if a department is over budget.

    Called by the STOA Gateway's BudgetCache every ~60s.
    Returns over_budget=false when no budget is configured (fail-open).
    """
    service = BillingService(db)
    result = await service.check_budget(department_id)
    return result
