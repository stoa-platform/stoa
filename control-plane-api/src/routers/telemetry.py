"""Telemetry Ingest Router — webhook endpoint for push-based gateway telemetry.

POST /internal/telemetry/ingest accepts JSON arrays of log entries
from gateways configured with push subscriptions (Kong http-log,
webMethods subscriptions, etc.).

Internal endpoint — authenticated via API key, not user JWT.

See CAB-1682 for architectural context.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ..config import settings
from ..services.telemetry_collector import telemetry_collector

logger = logging.getLogger("stoa.telemetry.router")

router = APIRouter(prefix="/internal/telemetry", tags=["Telemetry Internal"])


class TelemetryEntry(BaseModel):
    """A single gateway telemetry log entry."""

    timestamp: str | None = None
    gateway_type: str
    gateway_id: str | None = None
    tenant_id: str | None = "platform"
    method: str = "UNKNOWN"
    path: str = "/"
    status: int = 0
    latency_ms: float = 0.0
    request_id: str | None = None
    trace_id: str | None = None
    user_agent: str | None = None
    source_ip: str | None = None


class IngestRequest(BaseModel):
    """Batch ingest request body."""

    entries: list[TelemetryEntry] = Field(..., min_length=1, max_length=5000)


class IngestResponse(BaseModel):
    """Ingest response."""

    accepted: int
    status: str


def _verify_internal_api_key(
    x_internal_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """Verify the internal API key for telemetry ingestion."""
    expected = getattr(settings, "TELEMETRY_INTERNAL_API_KEY", None)
    if not expected:
        # If no key configured, allow all (dev mode)
        return "dev"
    if x_internal_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal API key",
        )
    return x_internal_api_key


@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest gateway telemetry entries",
    description="Accepts a batch of log entries from push-based gateways.",
)
async def ingest_telemetry(
    body: IngestRequest,
    _api_key: str = Depends(_verify_internal_api_key),
) -> IngestResponse:
    entries = [entry.model_dump() for entry in body.entries]
    accepted = await telemetry_collector.ingest(entries, source="push")

    if not accepted:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Backpressure limit reached. Retry later.",
        )

    return IngestResponse(accepted=len(entries), status="ok")


@router.get(
    "/status",
    summary="Telemetry subsystem status",
    description="Returns circuit breaker state and buffer size.",
)
async def telemetry_status() -> dict:
    from ..opensearch.log_writer import log_writer

    return {
        "buffer_size": log_writer.buffer_count(),
        "circuit_breaker_open": log_writer._circuit_open,
        "consecutive_failures": log_writer._consecutive_failures,
    }
