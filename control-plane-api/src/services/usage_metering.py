"""Service layer for usage metering (CAB-1334 Phase 1)."""

import logging
import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.chat_token_usage_repository import ChatTokenUsageRepository
from src.repositories.usage_metering import UsageMeteringRepository
from src.schemas.usage_metering import (
    UsageDetailResponse,
    UsageRecordCreate,
    UsageRecordResponse,
    UsageSummaryListResponse,
    UsageSummaryResponse,
)

logger = logging.getLogger(__name__)


class UsageMeteringService:
    """Business logic for usage metering — aggregation, retrieval, and upsert."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UsageMeteringRepository(session)

    async def get_summary(
        self,
        tenant_id: str,
        api_id: uuid.UUID | None = None,
        period: str = "daily",
        limit: int = 50,
        offset: int = 0,
    ) -> UsageSummaryListResponse:
        """Retrieve paginated usage summaries for a tenant."""
        items, total = await self.repo.get_usage_summary(
            tenant_id=tenant_id,
            api_id=api_id,
            period=period,
            limit=limit,
            offset=offset,
        )
        return UsageSummaryListResponse(
            items=[UsageSummaryResponse.model_validate(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_details(
        self,
        tenant_id: str,
        api_id: uuid.UUID,
        period: str = "daily",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> UsageDetailResponse | None:
        """Get aggregated usage details for a specific API."""
        result = await self.repo.get_usage_details(
            tenant_id=tenant_id,
            api_id=api_id,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
        if result is None:
            return None
        return UsageDetailResponse(**result)

    async def record_llm_usage(self, request: UsageRecordCreate) -> UsageRecordResponse:
        """Record LLM proxy usage from the gateway (CAB-1568).

        Uses ChatTokenUsage table for daily per-consumer aggregation.
        The consumer_id (from stoa_sk_* key) is used as user_id, and
        'llm-proxy' is the default tenant for dogfood mode.
        """
        token_repo = ChatTokenUsageRepository(self.session)
        await token_repo.increment(
            tenant_id="llm-proxy",
            user_id=request.consumer_id,
            model=request.model,
            input_tokens=request.input_tokens,
            output_tokens=request.output_tokens,
        )
        total = request.input_tokens + request.output_tokens
        logger.info(
            "LLM proxy usage recorded: consumer=%s model=%s tokens=%d",
            request.consumer_id,
            request.model,
            total,
        )
        return UsageRecordResponse(
            input_tokens=request.input_tokens,
            output_tokens=request.output_tokens,
            total_tokens=total,
        )

    async def record_usage(
        self,
        tenant_id: str,
        api_id: uuid.UUID,
        period: str,
        period_start: datetime,
        request_count: int = 0,
        error_count: int = 0,
        total_latency_ms: int = 0,
        p99_latency_ms: int | None = None,
        total_tokens: int = 0,
        consumer_id: uuid.UUID | None = None,
    ) -> UsageSummaryResponse:
        """Record (upsert) a usage event into the summaries table."""
        record = await self.repo.upsert_usage(
            tenant_id=tenant_id,
            api_id=api_id,
            period=period,
            period_start=period_start,
            request_count=request_count,
            error_count=error_count,
            total_latency_ms=total_latency_ms,
            p99_latency_ms=p99_latency_ms,
            total_tokens=total_tokens,
            consumer_id=consumer_id,
        )
        return UsageSummaryResponse.model_validate(record)
