# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Demo trigger endpoints for scenario control.

CAB-1018: Mock APIs for Central Bank Demo
Council feedback (OSS Killer): Use /demo/trigger/* instead of query params.

These endpoints are only available when DEMO_SCENARIOS_ENABLED=true.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, status, Query
from pydantic import BaseModel, Field

from src.config import settings
from src.logging_config import get_logger
from src.services.circuit_breaker import get_circuit_breaker
from src.services.idempotency import get_idempotency_store
from src.services.saga import get_saga_orchestrator
from src.services.semantic_cache import get_semantic_cache

logger = get_logger(__name__)

router = APIRouter(tags=["Demo"])


class DemoActionResponse(BaseModel):
    """Response for demo trigger actions."""

    success: bool = Field(default=True)
    action: str = Field(description="Action performed")
    details: dict = Field(default_factory=dict, description="Action details")
    timestamp: str = Field(description="ISO timestamp")


class DemoStateResponse(BaseModel):
    """Response for demo state endpoint."""

    demo_mode: bool = Field(description="Whether demo mode is enabled")
    demo_scenarios_enabled: bool = Field(description="Whether demo triggers are enabled")
    circuit_breaker: dict = Field(description="Circuit breaker state")
    idempotency_store: dict = Field(
        default_factory=dict,
        description="Idempotency store state",
    )
    saga: dict = Field(
        default_factory=dict,
        description="Saga orchestrator state",
    )
    semantic_cache: dict = Field(
        default_factory=dict,
        description="Semantic cache state",
    )
    timestamp: str = Field(description="ISO timestamp")


def _check_demo_enabled() -> None:
    """Check if demo scenarios are enabled, raise 404 if not."""
    if not settings.demo_scenarios_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Demo scenarios are disabled. Set DEMO_SCENARIOS_ENABLED=true to enable.",
        )


@router.post(
    "/trigger/spike",
    response_model=DemoActionResponse,
    summary="Trigger circuit breaker latency spike",
    description="""
Activate a latency spike for the Fraud Detection API.

The next N requests will experience 2000ms latency instead of 50ms.
Use this to demonstrate circuit breaker behavior during a live demo.
    """,
)
async def trigger_spike(
    num_requests: int = Query(
        default=5,
        ge=1,
        le=100,
        description="Number of requests to affect",
    ),
) -> DemoActionResponse:
    """Trigger latency spike for next N requests."""
    _check_demo_enabled()

    circuit_breaker = get_circuit_breaker()
    result = circuit_breaker.trigger_spike(num_requests)

    logger.info(
        "Demo: Spike triggered",
        num_requests=num_requests,
    )

    return DemoActionResponse(
        success=True,
        action="spike_triggered",
        details=result,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@router.post(
    "/trigger/circuit-open",
    response_model=DemoActionResponse,
    summary="Force circuit breaker to OPEN state",
    description="""
Force the circuit breaker to OPEN state.

All subsequent Fraud Detection requests will receive a 503 with fallback response.
Use this to demonstrate graceful degradation during a live demo.
    """,
)
async def trigger_circuit_open() -> DemoActionResponse:
    """Force circuit breaker to OPEN state."""
    _check_demo_enabled()

    circuit_breaker = get_circuit_breaker()
    result = circuit_breaker.force_open()

    logger.info("Demo: Circuit breaker forced OPEN")

    return DemoActionResponse(
        success=True,
        action="circuit_forced_open",
        details=result,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@router.post(
    "/trigger/rollback",
    response_model=DemoActionResponse,
    summary="Force next settlement to rollback",
    description="""
Force the next settlement to fail and trigger saga rollback.

The settlement will fail at the `execute_transfer` step, triggering:
- `reverse_transfer` compensation
- `release_funds` compensation
- Final status: `ROLLED_BACK`

Use this to demonstrate saga compensation during a live demo.
    """,
)
async def trigger_rollback() -> DemoActionResponse:
    """Force next settlement to fail and rollback."""
    _check_demo_enabled()

    saga = get_saga_orchestrator()
    result = saga.trigger_rollback_next()

    logger.info("Demo: Rollback armed for next settlement")

    return DemoActionResponse(
        success=True,
        action="rollback_armed",
        details=result,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@router.post(
    "/trigger/cache-clear",
    response_model=DemoActionResponse,
    summary="Clear sanctions semantic cache",
    description="""
Clear the sanctions screening semantic cache.

All subsequent screening requests will be cache misses until cached again.
Use this to demonstrate cache behavior during a live demo.
    """,
)
async def trigger_cache_clear() -> DemoActionResponse:
    """Clear the semantic cache."""
    _check_demo_enabled()

    semantic_cache = get_semantic_cache()
    cleared_count = semantic_cache.clear()

    logger.info("Demo: Semantic cache cleared", cleared_count=cleared_count)

    return DemoActionResponse(
        success=True,
        action="cache_cleared",
        details={"cleared_entries": cleared_count},
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@router.post(
    "/trigger/reset",
    response_model=DemoActionResponse,
    summary="Reset all demo states",
    description="""
Reset all demo states to their initial values:
- Circuit breaker → CLOSED
- Latency spike → disabled
- Saga rollback → disabled
- Idempotency store → cleared
- Semantic cache → cleared
    """,
)
async def trigger_reset() -> DemoActionResponse:
    """Reset all demo states."""
    _check_demo_enabled()

    circuit_breaker = get_circuit_breaker()
    cb_result = circuit_breaker.reset()

    saga = get_saga_orchestrator()
    saga_result = saga.reset()

    idempotency_store = get_idempotency_store()
    idempotency_cleared = idempotency_store.clear()

    semantic_cache = get_semantic_cache()
    cache_cleared = semantic_cache.clear()

    logger.info("Demo: All states reset")

    return DemoActionResponse(
        success=True,
        action="all_states_reset",
        details={
            "circuit_breaker": cb_result,
            "saga": saga_result,
            "idempotency_store": {"cleared_entries": idempotency_cleared},
            "semantic_cache": {"cleared_entries": cache_cleared},
        },
        timestamp=datetime.utcnow().isoformat() + "Z",
    )


@router.get(
    "/state",
    response_model=DemoStateResponse,
    summary="Get current demo state",
    description="""
Get the current state of all demo components.

Useful for debugging and monitoring during a live demo.
    """,
)
async def get_demo_state() -> DemoStateResponse:
    """Get current demo state."""
    _check_demo_enabled()

    circuit_breaker = get_circuit_breaker()
    cb_state = circuit_breaker.get_state()

    saga = get_saga_orchestrator()
    saga_state = saga.get_state()

    idempotency_store = get_idempotency_store()
    idempotency_state = idempotency_store.get_stats()

    semantic_cache = get_semantic_cache()
    cache_state = semantic_cache.get_stats()

    return DemoStateResponse(
        demo_mode=settings.demo_mode,
        demo_scenarios_enabled=settings.demo_scenarios_enabled,
        circuit_breaker=cb_state["circuit_breaker"],
        idempotency_store=idempotency_state,
        saga=saga_state,
        semantic_cache=cache_state,
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
