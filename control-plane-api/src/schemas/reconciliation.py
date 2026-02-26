"""Pydantic schemas for SCIM↔Gateway reconciliation API (CAB-1484)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DriftType(StrEnum):
    """Type of drift between SCIM and gateway."""

    MISSING_IN_GATEWAY = "missing_in_gateway"
    ORPHANED_IN_GATEWAY = "orphaned_in_gateway"
    ROLE_MISMATCH = "role_mismatch"


class DriftItem(BaseModel):
    """A single drift entry between SCIM and gateway state."""

    drift_type: DriftType
    client_id: str | None = None
    client_name: str
    detail: str
    scim_roles: list[str] = Field(default_factory=list)
    gateway_roles: list[str] = Field(default_factory=list)


class DriftReport(BaseModel):
    """Full drift report comparing SCIM state with gateway consumers."""

    tenant_id: str
    checked_at: datetime
    in_sync: bool
    total_scim_clients: int
    total_gateway_consumers: int
    drift_items: list[DriftItem] = Field(default_factory=list)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "tenant-acme",
                "checked_at": "2026-02-26T12:00:00Z",
                "in_sync": False,
                "total_scim_clients": 5,
                "total_gateway_consumers": 4,
                "drift_items": [
                    {
                        "drift_type": "missing_in_gateway",
                        "client_name": "acme-billing-service",
                        "detail": "Client exists in SCIM but not provisioned in gateway",
                        "scim_roles": ["api:read", "billing:admin"],
                        "gateway_roles": [],
                    }
                ],
            }
        }
    )


class ReconciliationAction(StrEnum):
    """Action taken during reconciliation."""

    PROVISIONED = "provisioned"
    DEPROVISIONED = "deprovisioned"
    UPDATED_ROLES = "updated_roles"
    SKIPPED = "skipped"
    FAILED = "failed"


class ReconciliationActionResult(BaseModel):
    """Result of a single reconciliation action."""

    client_name: str
    action: ReconciliationAction
    detail: str


class ReconciliationResult(BaseModel):
    """Result of a full reconciliation run."""

    tenant_id: str
    started_at: datetime
    completed_at: datetime
    success: bool
    actions_taken: int
    actions_failed: int
    results: list[ReconciliationActionResult] = Field(default_factory=list)


class ReconciliationStatus(BaseModel):
    """Current reconciliation status for a tenant."""

    tenant_id: str
    last_check: datetime | None = None
    last_sync: datetime | None = None
    in_sync: bool = True
    drift_count: int = 0
    last_error: str | None = None
