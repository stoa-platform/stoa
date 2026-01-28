# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Settlement API schemas.

CAB-1018: Mock APIs for Central Bank Demo
Pydantic models for settlement processing with saga pattern.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SettlementStatus(str, Enum):
    """Settlement processing status."""

    PENDING = "PENDING"
    VALIDATING = "VALIDATING"
    RESERVING = "RESERVING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class StepStatus(str, Enum):
    """Individual saga step status."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"
    SKIPPED = "SKIPPED"


class SagaStep(BaseModel):
    """Individual step in the saga."""

    name: str = Field(description="Step name")
    status: StepStatus = Field(description="Step status")
    started_at: Optional[str] = Field(default=None, description="ISO timestamp when started")
    completed_at: Optional[str] = Field(default=None, description="ISO timestamp when completed")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    compensation_of: Optional[str] = Field(
        default=None, description="Name of step this compensates (for rollback)"
    )


class AuditEntry(BaseModel):
    """Audit trail entry for settlement processing."""

    timestamp: str = Field(description="ISO timestamp")
    action: str = Field(description="Action performed")
    status: str = Field(description="Action status: SUCCESS, FAILED, COMPENSATED")
    actor: str = Field(default="saga-orchestrator", description="Actor performing action")
    details: dict = Field(default_factory=dict, description="Additional details")


class SettlementRequest(BaseModel):
    """Request model for creating a settlement."""

    settlement_id: str = Field(
        ...,
        description="Unique settlement identifier",
        examples=["SETL-001", "SETL-2026-02-26-ABC123"],
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Settlement amount",
        examples=[10000.00, 50000.00],
    )
    currency: str = Field(
        default="EUR",
        description="ISO 4217 currency code",
        examples=["EUR", "USD", "GBP"],
    )
    debtor_iban: str = Field(
        ...,
        description="Debtor (payer) IBAN",
        examples=["FR7630006000011234567890189"],
    )
    creditor_iban: str = Field(
        ...,
        description="Creditor (payee) IBAN",
        examples=["DE89370400440532013000"],
    )
    reference: Optional[str] = Field(
        default=None,
        description="Payment reference",
        examples=["INV-2026-001"],
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Additional settlement metadata",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "settlement_id": "SETL-001",
                "amount": 10000.00,
                "currency": "EUR",
                "debtor_iban": "FR7630006000011234567890189",
                "creditor_iban": "DE89370400440532013000",
                "reference": "INV-2026-001",
            }
        }
    }


class SettlementResponse(BaseModel):
    """Response model for settlement creation."""

    settlement_id: str = Field(description="Settlement identifier")
    status: SettlementStatus = Field(description="Current settlement status")
    steps: list[SagaStep] = Field(description="Saga execution steps")
    amount: float = Field(description="Settlement amount")
    currency: str = Field(description="Currency code")
    debtor_iban: str = Field(description="Debtor IBAN")
    creditor_iban: str = Field(description="Creditor IBAN")
    created_at: str = Field(description="ISO timestamp of creation")
    updated_at: str = Field(description="ISO timestamp of last update")
    idempotency_key: str = Field(description="Idempotency key used")
    idempotency_hit: bool = Field(
        default=False, description="Whether this was a cached response"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "settlement_id": "SETL-001",
                "status": "COMPLETED",
                "steps": [
                    {"name": "validate_funds", "status": "COMPLETED"},
                    {"name": "reserve_funds", "status": "COMPLETED"},
                    {"name": "execute_transfer", "status": "COMPLETED"},
                    {"name": "confirm_settlement", "status": "COMPLETED"},
                ],
                "amount": 10000.00,
                "currency": "EUR",
                "debtor_iban": "FR7630006000011234567890189",
                "creditor_iban": "DE89370400440532013000",
                "created_at": "2026-02-26T10:00:00Z",
                "updated_at": "2026-02-26T10:00:05Z",
                "idempotency_key": "setl-001-unique",
                "idempotency_hit": False,
            }
        }
    }


class SettlementStatusResponse(BaseModel):
    """Response model for settlement status query."""

    settlement_id: str = Field(description="Settlement identifier")
    status: SettlementStatus = Field(description="Current settlement status")
    steps: list[SagaStep] = Field(description="Saga execution steps")
    audit_trail: list[AuditEntry] = Field(description="Audit trail entries")
    amount: float = Field(description="Settlement amount")
    currency: str = Field(description="Currency code")
    created_at: str = Field(description="ISO timestamp of creation")
    updated_at: str = Field(description="ISO timestamp of last update")

    model_config = {
        "json_schema_extra": {
            "example": {
                "settlement_id": "SETL-001",
                "status": "COMPLETED",
                "steps": [
                    {
                        "name": "validate_funds",
                        "status": "COMPLETED",
                        "started_at": "2026-02-26T10:00:00Z",
                        "completed_at": "2026-02-26T10:00:01Z",
                    }
                ],
                "audit_trail": [
                    {
                        "timestamp": "2026-02-26T10:00:00Z",
                        "action": "VALIDATE_FUNDS",
                        "status": "SUCCESS",
                        "actor": "saga-orchestrator",
                        "details": {"amount": 10000, "currency": "EUR"},
                    }
                ],
                "amount": 10000.00,
                "currency": "EUR",
                "created_at": "2026-02-26T10:00:00Z",
                "updated_at": "2026-02-26T10:00:05Z",
            }
        }
    }
