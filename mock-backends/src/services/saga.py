# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""Saga orchestrator for Settlement API.

CAB-1018: Mock APIs for Central Bank Demo
Implements saga pattern with compensation (rollback) for settlement processing.
"""

import asyncio
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.config import settings
from src.logging_config import get_logger
from src.schemas.settlement import (
    SettlementRequest,
    SettlementStatus,
    SagaStep,
    StepStatus,
    AuditEntry,
)

logger = get_logger(__name__)

# Seed random for reproducibility in demo
random.seed(settings.faker_seed)


@dataclass
class SagaState:
    """Mutable state for saga orchestrator."""

    # Demo controls
    force_rollback_next: bool = False
    force_fail_step: Optional[str] = None


@dataclass
class SettlementRecord:
    """Internal record of a settlement."""

    settlement_id: str
    request: SettlementRequest
    status: SettlementStatus
    steps: list[SagaStep] = field(default_factory=list)
    audit_trail: list[AuditEntry] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    idempotency_key: str = ""


# Saga step definitions
SAGA_STEPS = [
    "validate_funds",
    "reserve_funds",
    "execute_transfer",
    "confirm_settlement",
]

# Compensation (rollback) steps - reverse order
COMPENSATION_STEPS = {
    "confirm_settlement": "cancel_confirmation",
    "execute_transfer": "reverse_transfer",
    "reserve_funds": "release_funds",
    "validate_funds": None,  # No compensation needed
}


class SagaOrchestrator:
    """Saga orchestrator for settlement processing.

    Implements the saga pattern with:
    - Sequential step execution
    - Automatic compensation on failure
    - Demo controls for forcing failures

    Steps:
    1. validate_funds - Verify sufficient funds
    2. reserve_funds - Place hold on funds
    3. execute_transfer - Execute the transfer
    4. confirm_settlement - Final confirmation

    Each step has 95% success rate (5% random failure) unless forced.
    """

    def __init__(self):
        self._state = SagaState()
        self._settlements: dict[str, SettlementRecord] = {}
        self._step_success_rate = 0.95  # 95% success

    async def execute(
        self, request: SettlementRequest, idempotency_key: str
    ) -> SettlementRecord:
        """Execute saga for settlement.

        Args:
            request: Settlement request
            idempotency_key: Idempotency key for the request

        Returns:
            SettlementRecord with final status
        """
        now = datetime.utcnow()

        # Create settlement record
        record = SettlementRecord(
            settlement_id=request.settlement_id,
            request=request,
            status=SettlementStatus.PENDING,
            created_at=now,
            updated_at=now,
            idempotency_key=idempotency_key,
        )

        # Initialize steps
        for step_name in SAGA_STEPS:
            record.steps.append(
                SagaStep(name=step_name, status=StepStatus.PENDING)
            )

        # Add initial audit entry
        record.audit_trail.append(
            AuditEntry(
                timestamp=now.isoformat() + "Z",
                action="SETTLEMENT_INITIATED",
                status="SUCCESS",
                actor="saga-orchestrator",
                details={
                    "settlement_id": request.settlement_id,
                    "amount": request.amount,
                    "currency": request.currency,
                },
            )
        )

        # Store record
        self._settlements[request.settlement_id] = record

        # Check if rollback is forced for this settlement
        force_fail = self._state.force_rollback_next
        if force_fail:
            self._state.force_rollback_next = False  # Reset after use
            logger.info("Demo: Forcing rollback for this settlement")

        # Execute saga steps
        failed_step_index = None

        for i, step_name in enumerate(SAGA_STEPS):
            step = record.steps[i]
            step.status = StepStatus.IN_PROGRESS
            step.started_at = datetime.utcnow().isoformat() + "Z"
            record.status = self._status_for_step(step_name)
            record.updated_at = datetime.utcnow()

            # Simulate step execution
            await asyncio.sleep(0.05)  # 50ms per step

            # Determine if step succeeds
            step_succeeds = True

            if force_fail and step_name == "execute_transfer":
                # Force fail at execute_transfer step for visible rollback
                step_succeeds = False
                logger.info(f"Demo: Forcing failure at step {step_name}")
            elif random.random() > self._step_success_rate:
                # Random failure (5% chance)
                step_succeeds = False
                logger.info(f"Random failure at step {step_name}")

            if step_succeeds:
                step.status = StepStatus.COMPLETED
                step.completed_at = datetime.utcnow().isoformat() + "Z"

                record.audit_trail.append(
                    AuditEntry(
                        timestamp=datetime.utcnow().isoformat() + "Z",
                        action=step_name.upper(),
                        status="SUCCESS",
                        actor="saga-orchestrator",
                        details={
                            "amount": request.amount,
                            "currency": request.currency,
                        },
                    )
                )
            else:
                step.status = StepStatus.FAILED
                step.completed_at = datetime.utcnow().isoformat() + "Z"
                step.error = f"Step {step_name} failed"
                failed_step_index = i

                record.audit_trail.append(
                    AuditEntry(
                        timestamp=datetime.utcnow().isoformat() + "Z",
                        action=step_name.upper(),
                        status="FAILED",
                        actor="saga-orchestrator",
                        details={"error": step.error},
                    )
                )
                break

        # If any step failed, trigger rollback
        if failed_step_index is not None:
            await self._rollback(record, failed_step_index)
        else:
            record.status = SettlementStatus.COMPLETED
            record.updated_at = datetime.utcnow()

            record.audit_trail.append(
                AuditEntry(
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    action="SETTLEMENT_COMPLETED",
                    status="SUCCESS",
                    actor="saga-orchestrator",
                    details={
                        "settlement_id": request.settlement_id,
                        "final_status": record.status.value,
                    },
                )
            )

        logger.info(
            "Saga completed",
            settlement_id=request.settlement_id,
            status=record.status.value,
            steps_completed=sum(
                1 for s in record.steps if s.status == StepStatus.COMPLETED
            ),
        )

        return record

    async def _rollback(self, record: SettlementRecord, failed_step_index: int) -> None:
        """Execute compensation steps for rollback.

        Args:
            record: Settlement record to rollback
            failed_step_index: Index of the step that failed
        """
        logger.info(
            "Starting saga rollback",
            settlement_id=record.settlement_id,
            failed_at_step=SAGA_STEPS[failed_step_index],
        )

        record.audit_trail.append(
            AuditEntry(
                timestamp=datetime.utcnow().isoformat() + "Z",
                action="ROLLBACK_INITIATED",
                status="IN_PROGRESS",
                actor="saga-orchestrator",
                details={"failed_step": SAGA_STEPS[failed_step_index]},
            )
        )

        # Mark remaining steps as skipped
        for i in range(failed_step_index + 1, len(SAGA_STEPS)):
            record.steps[i].status = StepStatus.SKIPPED

        # Execute compensation in reverse order
        for i in range(failed_step_index - 1, -1, -1):
            step_name = SAGA_STEPS[i]
            compensation_name = COMPENSATION_STEPS.get(step_name)

            if compensation_name is None:
                continue

            # Create compensation step
            compensation_step = SagaStep(
                name=compensation_name,
                status=StepStatus.IN_PROGRESS,
                started_at=datetime.utcnow().isoformat() + "Z",
                compensation_of=step_name,
            )

            await asyncio.sleep(0.03)  # 30ms for compensation

            compensation_step.status = StepStatus.COMPLETED
            compensation_step.completed_at = datetime.utcnow().isoformat() + "Z"

            # Mark original step as compensated
            record.steps[i].status = StepStatus.COMPENSATED

            record.steps.append(compensation_step)

            record.audit_trail.append(
                AuditEntry(
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    action=compensation_name.upper(),
                    status="COMPENSATED",
                    actor="saga-orchestrator",
                    details={"compensates": step_name},
                )
            )

        record.status = SettlementStatus.ROLLED_BACK
        record.updated_at = datetime.utcnow()

        record.audit_trail.append(
            AuditEntry(
                timestamp=datetime.utcnow().isoformat() + "Z",
                action="ROLLBACK_COMPLETED",
                status="SUCCESS",
                actor="saga-orchestrator",
                details={"final_status": record.status.value},
            )
        )

        logger.info(
            "Saga rollback completed",
            settlement_id=record.settlement_id,
        )

    def _status_for_step(self, step_name: str) -> SettlementStatus:
        """Map step name to settlement status."""
        status_map = {
            "validate_funds": SettlementStatus.VALIDATING,
            "reserve_funds": SettlementStatus.RESERVING,
            "execute_transfer": SettlementStatus.EXECUTING,
            "confirm_settlement": SettlementStatus.COMPLETED,
        }
        return status_map.get(step_name, SettlementStatus.PENDING)

    def get_settlement(self, settlement_id: str) -> Optional[SettlementRecord]:
        """Get settlement by ID.

        Args:
            settlement_id: Settlement identifier

        Returns:
            SettlementRecord if found, None otherwise
        """
        return self._settlements.get(settlement_id)

    # ========== Demo Controls ==========

    def trigger_rollback_next(self) -> dict:
        """Force next settlement to fail and rollback.

        Returns:
            Status dict
        """
        self._state.force_rollback_next = True
        logger.info("Demo: Next settlement will be forced to rollback")
        return {
            "action": "rollback_armed",
            "message": "Next settlement will fail at execute_transfer and rollback",
        }

    def reset(self) -> dict:
        """Reset saga state.

        Returns:
            Status dict
        """
        self._state.force_rollback_next = False
        self._state.force_fail_step = None
        logger.info("Demo: Saga state reset")
        return {
            "action": "saga_reset",
            "force_rollback_next": False,
        }

    def get_state(self) -> dict:
        """Get saga state for /demo/state.

        Returns:
            State dict
        """
        return {
            "force_rollback_next": self._state.force_rollback_next,
            "settlements_count": len(self._settlements),
            "step_success_rate": self._step_success_rate,
        }


# Singleton instance
_saga_orchestrator: Optional[SagaOrchestrator] = None


def get_saga_orchestrator() -> SagaOrchestrator:
    """Get the singleton saga orchestrator instance."""
    global _saga_orchestrator
    if _saga_orchestrator is None:
        _saga_orchestrator = SagaOrchestrator()
    return _saga_orchestrator
