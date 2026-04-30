"""Prometheus metrics for the GitOps catalog sync surface (CAB-2208).

Single Counter exposed by both the writer (``services/gitops_writer``) and the
reconciler (``services/catalog_reconciler``) to mirror every
``catalog_sync_status`` log emission. Logs lose their structlog ``extra=``
fields when the emitting module is wired on stdlib ``logging`` (root cause
fixed by CAB-2208); the counter is the durable observability surface that
§7bis and Phase 7-9 smoke/regression tests assert against.

Cardinality is the cross product of ``status`` (5 values), ``tenant_id`` and
``api_id``. With ~10 tenants and ~50 APIs in scope through Phase 10 this stays
well below 100k series — comfortably inside Prometheus' single-instance budget.
Re-evaluate the labels if the platform ever crosses ~100 tenants AND ~1000 APIs.

Legacy counters in ``src/workers/git_sync_worker.py`` (``GIT_SYNC_TOTAL``,
``GIT_SYNC_DURATION_SECONDS``, ``GIT_SYNC_RETRIES_TOTAL``) and
``src/workers/sync_engine.py`` (``DRIFT_DETECTED_TOTAL``,
``DRIFT_REPAIRED_TOTAL``) instrument the pre-rewrite DB-first + Kafka path.
They stay incrementing for tenants still on the legacy flow and are out of
scope here; their removal is conditioned on Phase 10 (all eligible tenants
migrated to the GitOps flow), not on a calendar trigger.
"""

from __future__ import annotations

from prometheus_client import Counter

VALID_SYNC_STATUSES: frozenset[str] = frozenset(
    {
        "synced",
        "failed",
        "drift_detected",
        "drift_pre_gitops",
        "drift_orphan",
    }
)
"""Status values emitted by ``_log_sync_status`` in writer.py + worker.py.

Kept as a frozenset constant so unit tests and the invariant suite can assert
against the exact emission surface without re-discovering it from the source.
"""


CATALOG_SYNC_STATUS_TOTAL: Counter = Counter(
    "catalog_sync_status_total",
    "GitOps catalog sync status transitions per (tenant, api, status).",
    ["tenant_id", "api_id", "status"],
)
"""Increment paired with every ``catalog_sync_status`` log line.

Status values are the 5 listed in :data:`VALID_SYNC_STATUSES`. The counter is
incremented inside the two ``_log_sync_status`` helpers (writer + reconciler);
it intentionally duplicates the structured log so observers can choose either
surface (logs for narrative, metric for time-series and alerts).
"""
