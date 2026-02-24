"""Data governance schemas for runtime source-of-truth classification and drift detection (CAB-1324)."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class DataSourceOfTruth(StrEnum):
    """Where the canonical version of an entity lives."""

    GIT = "git"
    DATABASE = "database"
    RUNTIME = "runtime"
    HYBRID = "hybrid"


class SyncDirection(StrEnum):
    """Direction of data flow between source and replicas."""

    GIT_TO_DB = "git→db"
    DB_TO_GATEWAY = "db→gateway"
    BIDIRECTIONAL = "bidirectional"


class DriftStatus(StrEnum):
    """Drift status of an entity class."""

    CLEAN = "clean"
    DRIFTED = "drifted"
    UNKNOWN = "unknown"
    ERROR = "error"


class ReconcileAction(StrEnum):
    """How drift is resolved."""

    AUTO = "auto"
    MANUAL = "manual"
    ON_SYNC = "on-sync"


# ---------------------------------------------------------------------------
# Governance Matrix
# ---------------------------------------------------------------------------


class GovernanceEntity(BaseModel):
    """Classification of a single entity type in the governance matrix."""

    entity_type: str = Field(description="Logical entity name (e.g. api_catalog)")
    source_of_truth: DataSourceOfTruth
    sync_direction: SyncDirection
    drift_detection: bool = Field(description="Whether drift is actively monitored")
    reconciliation_method: ReconcileAction
    last_sync_at: datetime | None = None
    drift_status: DriftStatus = DriftStatus.UNKNOWN
    total_count: int = 0
    drifted_count: int = 0
    error_count: int = 0


class GovernanceMatrixSummary(BaseModel):
    total_entity_types: int
    total_items: int
    total_drifted: int
    total_errors: int
    health_pct: float = Field(description="Percentage of items with clean status")


class GovernanceMatrixResponse(BaseModel):
    timestamp: datetime
    entities: list[GovernanceEntity]
    summary: GovernanceMatrixSummary


# ---------------------------------------------------------------------------
# Drift Report
# ---------------------------------------------------------------------------


class DriftItem(BaseModel):
    """A single drifted item within an entity type."""

    entity_id: str
    entity_name: str
    drift_type: str = Field(description="orphan | stale | desync | error")
    detail: str
    last_sync_at: datetime | None = None


class EntityDriftDetail(BaseModel):
    """Drift report for a single entity type."""

    entity_type: str
    source_of_truth: DataSourceOfTruth
    total: int
    drifted: int
    items: list[DriftItem]


class DriftReportResponse(BaseModel):
    timestamp: datetime
    total_entities: int
    total_drifted: int
    entities: list[EntityDriftDetail]


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


class ReconcileRequest(BaseModel):
    dry_run: bool = Field(default=True, description="Preview changes without applying")


class ReconcileResult(BaseModel):
    entity_type: str
    action: str
    items_reconciled: int
    items_skipped: int = 0
    dry_run: bool
    errors: list[str] = Field(default_factory=list)


class ReconcileResponse(BaseModel):
    timestamp: datetime
    results: list[ReconcileResult]
