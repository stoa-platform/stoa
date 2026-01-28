"""Fraud Detection API schemas.

CAB-1018: Mock APIs for Central Bank Demo
Pydantic models for transaction fraud scoring.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FraudDecision(str, Enum):
    """Fraud decision result."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REVIEW = "REVIEW"


class RiskFactor(str, Enum):
    """Risk factors that contribute to fraud score."""

    HIGH_AMOUNT = "HIGH_AMOUNT"
    VERY_HIGH_AMOUNT = "VERY_HIGH_AMOUNT"
    CROSS_BORDER = "CROSS_BORDER"
    HIGH_RISK_COUNTRY = "HIGH_RISK_COUNTRY"
    NEW_RECEIVER = "NEW_RECEIVER"
    UNUSUAL_TIME = "UNUSUAL_TIME"
    VELOCITY_SPIKE = "VELOCITY_SPIKE"
    ROUND_AMOUNT = "ROUND_AMOUNT"


class TransactionScoreRequest(BaseModel):
    """Request model for transaction fraud scoring."""

    transaction_id: str = Field(
        ...,
        description="Unique transaction identifier",
        examples=["TXN-001", "TXN-2026-02-26-ABC123"],
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Transaction amount",
        examples=[10000.00, 75000.00],
    )
    currency: str = Field(
        default="EUR",
        description="ISO 4217 currency code",
        examples=["EUR", "USD", "GBP"],
    )
    sender_iban: str = Field(
        ...,
        description="Sender IBAN",
        examples=["FR7630006000011234567890189"],
    )
    receiver_iban: str = Field(
        ...,
        description="Receiver IBAN",
        examples=["DE89370400440532013000"],
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Additional transaction metadata",
        examples=[{"channel": "mobile", "device_id": "ABC123"}],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "transaction_id": "TXN-001",
                "amount": 75000.00,
                "currency": "EUR",
                "sender_iban": "FR7630006000011234567890189",
                "receiver_iban": "DE89370400440532013000",
                "metadata": {"channel": "web"},
            }
        }
    }


class TransactionScoreResponse(BaseModel):
    """Response model for transaction fraud scoring."""

    transaction_id: str = Field(description="Transaction identifier")
    score: int = Field(
        ge=0,
        le=100,
        description="Fraud risk score (0=safe, 100=fraudulent)",
    )
    decision: FraudDecision = Field(description="Fraud decision")
    risk_factors: list[RiskFactor] = Field(
        default_factory=list,
        description="Contributing risk factors",
    )
    processing_time_ms: int = Field(
        description="Processing time in milliseconds"
    )
    circuit_state: str = Field(
        description="Circuit breaker state: CLOSED, OPEN, HALF_OPEN"
    )
    fallback_used: bool = Field(
        default=False,
        description="Whether fallback response was used (circuit open)"
    )
    timestamp: str = Field(description="ISO timestamp of scoring")

    model_config = {
        "json_schema_extra": {
            "example": {
                "transaction_id": "TXN-001",
                "score": 65,
                "decision": "REVIEW",
                "risk_factors": ["HIGH_AMOUNT", "CROSS_BORDER"],
                "processing_time_ms": 52,
                "circuit_state": "CLOSED",
                "fallback_used": False,
                "timestamp": "2026-02-26T10:00:00Z",
            }
        }
    }


class CircuitBreakerFallbackResponse(BaseModel):
    """Fallback response when circuit breaker is open."""

    transaction_id: str = Field(description="Transaction identifier")
    decision: FraudDecision = Field(
        default=FraudDecision.ALLOW,
        description="Fallback decision (always ALLOW with flag)"
    )
    fallback_used: bool = Field(default=True)
    fallback_reason: str = Field(
        default="circuit_breaker_open",
        description="Reason for fallback"
    )
    circuit_state: str = Field(default="OPEN")
    warning: str = Field(
        default="Transaction allowed due to circuit breaker - manual review recommended",
        description="Warning message for operators"
    )
    timestamp: str = Field(description="ISO timestamp")
