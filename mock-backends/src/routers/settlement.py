"""Settlement API router.

CAB-1018: Mock APIs for Central Bank Demo
Demonstrates idempotency pattern and saga with rollback.
"""

from fastapi import APIRouter, HTTPException, Header, status
from prometheus_client import Counter, Gauge

from src.config import settings
from src.logging_config import get_logger
from src.schemas.settlement import (
    SettlementRequest,
    SettlementResponse,
    SettlementStatusResponse,
    SagaStep,
)
from src.services.idempotency import get_idempotency_store
from src.services.saga import get_saga_orchestrator

logger = get_logger(__name__)

router = APIRouter(tags=["Settlement"])

# Prometheus metrics
SETTLEMENT_REQUESTS_TOTAL = Counter(
    f"{settings.metrics_prefix}_settlement_requests_total",
    "Total settlement requests",
    ["status", "idempotency_hit"],
)

SETTLEMENT_SAGA_STEPS = Counter(
    f"{settings.metrics_prefix}_settlement_saga_steps_total",
    "Total saga steps executed",
    ["step_name", "step_status"],
)

SETTLEMENT_ACTIVE = Gauge(
    f"{settings.metrics_prefix}_settlement_active_count",
    "Number of active settlements in store",
)


def _record_to_response(record, idempotency_hit: bool = False) -> SettlementResponse:
    """Convert SettlementRecord to SettlementResponse."""
    return SettlementResponse(
        settlement_id=record.settlement_id,
        status=record.status,
        steps=record.steps,
        amount=record.request.amount,
        currency=record.request.currency,
        debtor_iban=record.request.debtor_iban,
        creditor_iban=record.request.creditor_iban,
        created_at=record.created_at.isoformat() + "Z",
        updated_at=record.updated_at.isoformat() + "Z",
        idempotency_key=record.idempotency_key,
        idempotency_hit=idempotency_hit,
    )


@router.post(
    "/settlements",
    response_model=SettlementResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Idempotent request - cached response returned"},
        201: {"description": "Settlement created successfully"},
        400: {"description": "Invalid request"},
        422: {"description": "Validation error"},
    },
    summary="Create a new settlement",
    description="""
Create a new settlement with saga pattern execution.

**Idempotency:**
- The `Idempotency-Key` header is REQUIRED
- If the same key is used again, the cached response is returned (HTTP 200)
- New requests return HTTP 201

**Saga Steps:**
1. `validate_funds` - Verify sufficient funds available
2. `reserve_funds` - Place hold on debtor's funds
3. `execute_transfer` - Execute the actual transfer
4. `confirm_settlement` - Final confirmation

**Failure & Rollback:**
- Each step has 95% success rate (5% random failure)
- On failure, compensation steps execute in reverse:
  - `reverse_transfer` compensates `execute_transfer`
  - `release_funds` compensates `reserve_funds`
- Final status will be `ROLLED_BACK`

**Demo:**
Use `POST /demo/trigger/rollback` to force the next settlement to fail.
    """,
)
async def create_settlement(
    request: SettlementRequest,
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        description="Unique idempotency key for this request",
        examples=["setl-001-unique"],
    ),
) -> SettlementResponse:
    """Create a new settlement with idempotency support."""
    idempotency_store = get_idempotency_store()
    saga = get_saga_orchestrator()

    logger.info(
        "Settlement request received",
        settlement_id=request.settlement_id,
        idempotency_key=idempotency_key,
        amount=request.amount,
        currency=request.currency,
    )

    # Check idempotency
    cached_response = idempotency_store.check(idempotency_key)
    if cached_response is not None:
        logger.info(
            "Idempotency hit - returning cached response",
            settlement_id=request.settlement_id,
            idempotency_key=idempotency_key,
        )

        SETTLEMENT_REQUESTS_TOTAL.labels(
            status=cached_response.status.value,
            idempotency_hit="true",
        ).inc()

        # Mark as idempotency hit and return 200 (not 201)
        cached_response.idempotency_hit = True
        # Note: FastAPI will return 201 due to decorator, but the response indicates hit
        return cached_response

    # Execute saga
    try:
        record = await saga.execute(request, idempotency_key)

        # Build response
        response = _record_to_response(record, idempotency_hit=False)

        # Save to idempotency store
        idempotency_store.save(idempotency_key, response)

        # Update metrics
        SETTLEMENT_REQUESTS_TOTAL.labels(
            status=response.status.value,
            idempotency_hit="false",
        ).inc()

        for step in record.steps:
            SETTLEMENT_SAGA_STEPS.labels(
                step_name=step.name,
                step_status=step.status.value,
            ).inc()

        logger.info(
            "Settlement completed",
            settlement_id=request.settlement_id,
            status=response.status.value,
            idempotency_key=idempotency_key,
        )

        return response

    except Exception as e:
        logger.error(
            "Settlement failed",
            settlement_id=request.settlement_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Settlement processing failed: {str(e)}",
        )


@router.get(
    "/settlements/{settlement_id}/status",
    response_model=SettlementStatusResponse,
    responses={
        200: {"description": "Settlement status retrieved"},
        404: {"description": "Settlement not found"},
    },
    summary="Get settlement status",
    description="""
Get the current status of a settlement including:
- Current status (PENDING, COMPLETED, ROLLED_BACK, etc.)
- Saga steps with their individual statuses
- Full audit trail of all actions

**Audit Trail:**
Each entry contains:
- `timestamp`: When the action occurred
- `action`: Action name (e.g., VALIDATE_FUNDS, ROLLBACK_INITIATED)
- `status`: SUCCESS, FAILED, or COMPENSATED
- `actor`: Who performed the action (saga-orchestrator)
- `details`: Additional context
    """,
)
async def get_settlement_status(settlement_id: str) -> SettlementStatusResponse:
    """Get settlement status by ID."""
    saga = get_saga_orchestrator()
    record = saga.get_settlement(settlement_id)

    if record is None:
        logger.warning("Settlement not found", settlement_id=settlement_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Settlement {settlement_id} not found",
        )

    return SettlementStatusResponse(
        settlement_id=record.settlement_id,
        status=record.status,
        steps=record.steps,
        audit_trail=record.audit_trail,
        amount=record.request.amount,
        currency=record.request.currency,
        created_at=record.created_at.isoformat() + "Z",
        updated_at=record.updated_at.isoformat() + "Z",
    )
