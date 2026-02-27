"""Usage metering router — aggregated API usage endpoints (CAB-1334 Phase 1)."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.dependencies import User
from src.auth.rbac import require_role
from src.config import settings
from src.database import get_db
from src.schemas.usage_metering import (
    UsageDetailResponse,
    UsageRecordRequest,
    UsageSummaryListResponse,
)
from src.services.usage_metering import UsageMeteringService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/usage", tags=["Usage Metering"])


@router.get("/summary", response_model=UsageSummaryListResponse)
async def get_usage_summary(
    api_id: uuid.UUID | None = Query(None, description="Filter by API ID"),
    period: str = Query("daily", description="Period type: daily or monthly"),
    limit: int = Query(50, ge=1, le=200, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryListResponse:
    """Get paginated usage summaries for the current tenant.

    - **cpi-admin**: can view all tenants (uses default tenant or requires tenant_id param)
    - **tenant-admin**: scoped to own tenant
    """
    tenant_id = current_user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="User has no associated tenant")

    service = UsageMeteringService(db)
    return await service.get_summary(
        tenant_id=tenant_id,
        api_id=api_id,
        period=period,
        limit=limit,
        offset=offset,
    )


@router.get("/details", response_model=UsageDetailResponse)
async def get_usage_details(
    api_id: uuid.UUID = Query(..., description="API ID to get details for"),
    period: str = Query("daily", description="Period type: daily or monthly"),
    current_user: User = Depends(require_role(["cpi-admin", "tenant-admin"])),
    db: AsyncSession = Depends(get_db),
) -> UsageDetailResponse:
    """Get aggregated usage details for a specific API.

    Returns total requests, errors, error rate, average latency, and token usage.
    """
    tenant_id = current_user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="User has no associated tenant")

    service = UsageMeteringService(db)
    result = await service.get_details(
        tenant_id=tenant_id,
        api_id=api_id,
        period=period,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="No usage data found for this API")
    return result


@router.post("/record", status_code=201)
async def record_usage(
    payload: UsageRecordRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Record usage from a STOA gateway (CAB-1568: LLM proxy metering).

    Authenticated via X-API-Key header (control plane API key).
    Called by gateways after proxying LLM API requests.
    """
    valid_keys = settings.gateway_api_keys_list
    if not valid_keys or x_api_key not in valid_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")

    service = UsageMeteringService(db)
    now = datetime.now(UTC)

    # Use subscription_id as a deterministic api_id (UUID5 from namespace + subscription)
    api_id = uuid.uuid5(uuid.NAMESPACE_URL, f"llm-proxy:{payload.subscription_id}")

    await service.record_usage(
        tenant_id=payload.tenant_id,
        api_id=api_id,
        period="daily",
        period_start=now.replace(hour=0, minute=0, second=0, microsecond=0),
        request_count=payload.request_count,
        total_latency_ms=payload.total_latency_ms,
        total_tokens=payload.total_tokens,
    )
    await db.commit()

    logger.info(
        "Usage recorded: tenant=%s, subscription=%s, tokens=%d",
        payload.tenant_id,
        payload.subscription_id,
        payload.total_tokens,
    )

    return {"status": "recorded", "tenant_id": payload.tenant_id, "total_tokens": payload.total_tokens}
