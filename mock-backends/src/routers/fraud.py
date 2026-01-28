"""Fraud Detection API router.

CAB-1018: Mock APIs for Central Bank Demo
Demonstrates circuit breaker pattern with simulated latency spikes.
"""

import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from prometheus_client import Counter, Histogram, Gauge

from src.config import settings
from src.logging_config import get_logger
from src.schemas.fraud import (
    TransactionScoreRequest,
    TransactionScoreResponse,
    CircuitBreakerFallbackResponse,
    FraudDecision,
)
from src.services.circuit_breaker import get_circuit_breaker, CircuitState
from src.services.data_generator import generate_fraud_score

logger = get_logger(__name__)

router = APIRouter(tags=["Fraud Detection"])

# Prometheus metrics
FRAUD_REQUESTS_TOTAL = Counter(
    f"{settings.metrics_prefix}_fraud_requests_total",
    "Total fraud scoring requests",
    ["decision", "circuit_state"],
)

FRAUD_SCORE_HISTOGRAM = Histogram(
    f"{settings.metrics_prefix}_fraud_score_distribution",
    "Distribution of fraud scores",
    buckets=(10, 20, 30, 40, 50, 60, 70, 80, 90, 100),
)

FRAUD_LATENCY_SECONDS = Histogram(
    f"{settings.metrics_prefix}_fraud_latency_seconds",
    "Fraud API latency in seconds",
    ["circuit_state"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)

FRAUD_CIRCUIT_STATE = Gauge(
    f"{settings.metrics_prefix}_fraud_circuit_state",
    "Circuit breaker state (0=CLOSED, 1=OPEN, 2=HALF_OPEN)",
)


def _decision_from_score(score: int) -> FraudDecision:
    """Determine fraud decision based on score.

    Rules:
    - score < 30 → ALLOW
    - score 30-70 → REVIEW
    - score > 70 → DENY
    """
    if score < 30:
        return FraudDecision.ALLOW
    elif score <= 70:
        return FraudDecision.REVIEW
    else:
        return FraudDecision.DENY


def _update_circuit_state_metric(state: CircuitState) -> None:
    """Update Prometheus gauge for circuit state."""
    state_map = {
        CircuitState.CLOSED: 0,
        CircuitState.OPEN: 1,
        CircuitState.HALF_OPEN: 2,
    }
    FRAUD_CIRCUIT_STATE.set(state_map.get(state, 0))


@router.post(
    "/transactions/score",
    response_model=TransactionScoreResponse,
    responses={
        200: {"description": "Transaction scored successfully"},
        503: {
            "description": "Circuit breaker open - fallback response",
            "model": CircuitBreakerFallbackResponse,
        },
    },
    summary="Score transaction for fraud risk",
    description="""
Score a transaction for fraud risk using rule-based analysis.

**Scoring Rules:**
- Amount > €50,000 → +30 points (HIGH_AMOUNT)
- Amount > €100,000 → +50 points (VERY_HIGH_AMOUNT)
- Cross-border transaction → +20 points (CROSS_BORDER)
- High-risk country → +25 points (HIGH_RISK_COUNTRY)
- Round amount → +5 points (ROUND_AMOUNT)

**Decision Logic:**
- Score < 30 → ALLOW
- Score 30-70 → REVIEW
- Score > 70 → DENY

**Circuit Breaker:**
When the circuit breaker is OPEN, returns a 503 with fallback response
(ALLOW with warning flag) to prevent blocking legitimate transactions.
    """,
)
async def score_transaction(
    request: TransactionScoreRequest,
) -> TransactionScoreResponse | CircuitBreakerFallbackResponse:
    """Score a transaction for fraud risk."""
    start_time = time.perf_counter()
    circuit_breaker = get_circuit_breaker()
    circuit_state = circuit_breaker.state

    # Update circuit state metric
    _update_circuit_state_metric(circuit_state)

    logger.info(
        "Fraud scoring request received",
        transaction_id=request.transaction_id,
        amount=request.amount,
        currency=request.currency,
        circuit_state=circuit_state.value,
    )

    # Check circuit breaker
    if not circuit_breaker.should_allow():
        # Circuit is OPEN - return fallback response
        logger.warning(
            "Circuit breaker OPEN - returning fallback",
            transaction_id=request.transaction_id,
        )

        FRAUD_REQUESTS_TOTAL.labels(
            decision="ALLOW_FALLBACK",
            circuit_state=circuit_state.value,
        ).inc()

        # Return 503 with fallback response
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "transaction_id": request.transaction_id,
                "decision": FraudDecision.ALLOW.value,
                "fallback_used": True,
                "fallback_reason": "circuit_breaker_open",
                "circuit_state": circuit_state.value,
                "warning": "Transaction allowed due to circuit breaker - manual review recommended",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
        )

    try:
        # Apply simulated latency (normal or spike)
        latency_ms = await circuit_breaker.apply_latency()

        # Generate fraud score
        score, risk_factors = generate_fraud_score(
            amount=request.amount,
            sender_iban=request.sender_iban,
            receiver_iban=request.receiver_iban,
            transaction_id=request.transaction_id,
        )

        decision = _decision_from_score(score)

        # Record metrics
        FRAUD_SCORE_HISTOGRAM.observe(score)
        FRAUD_REQUESTS_TOTAL.labels(
            decision=decision.value,
            circuit_state=circuit_state.value,
        ).inc()

        # Record success for circuit breaker
        circuit_breaker.record_success()

        # Calculate total processing time
        processing_time_ms = int((time.perf_counter() - start_time) * 1000)

        FRAUD_LATENCY_SECONDS.labels(
            circuit_state=circuit_state.value,
        ).observe(processing_time_ms / 1000.0)

        logger.info(
            "Fraud scoring completed",
            transaction_id=request.transaction_id,
            score=score,
            decision=decision.value,
            risk_factors=[rf.value for rf in risk_factors],
            processing_time_ms=processing_time_ms,
            simulated_latency_ms=latency_ms,
        )

        return TransactionScoreResponse(
            transaction_id=request.transaction_id,
            score=score,
            decision=decision,
            risk_factors=risk_factors,
            processing_time_ms=processing_time_ms,
            circuit_state=circuit_state.value,
            fallback_used=False,
            timestamp=datetime.utcnow().isoformat() + "Z",
        )

    except Exception as e:
        # Record failure for circuit breaker
        circuit_breaker.record_failure()

        logger.error(
            "Fraud scoring failed",
            transaction_id=request.transaction_id,
            error=str(e),
        )
        raise
