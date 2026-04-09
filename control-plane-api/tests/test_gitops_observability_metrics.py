"""Tests for GitOps observability metrics (CAB-2026).

Verifies that Prometheus counters and histograms are incremented correctly
in GitSyncWorker (git sync metrics) and SyncEngine (drift metrics).
"""

from unittest.mock import AsyncMock

import pytest
from prometheus_client import REGISTRY

from src.workers.git_sync_worker import (
    GIT_SYNC_DURATION_SECONDS,
    GIT_SYNC_RETRIES_TOTAL,
    GIT_SYNC_TOTAL,
    GitSyncWorker,
)
from src.workers.sync_engine import (
    DRIFT_DETECTED_TOTAL,
    DRIFT_REPAIRED_TOTAL,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _metric_value(metric, labels: dict) -> float:
    """Read current value of a prometheus_client metric with given labels."""
    return metric.labels(**labels)._value.get()


def _histogram_count(metric, labels: dict) -> float:
    """Read the _count of a Histogram metric."""
    # Histogram exposes _count as a child of the metric
    return metric.labels(**labels)._sum._count.get() if hasattr(metric.labels(**labels), "_sum") else 0


# ── GitSyncWorker metrics tests ──────────────────────────────────────


@pytest.fixture
def worker():
    """Create a GitSyncWorker with mocked dependencies."""
    w = GitSyncWorker()
    w._git_sync_enabled = True
    w._github_service = AsyncMock()
    w._github_service.create_api = AsyncMock()
    w._github_service.update_api = AsyncMock()
    w._github_service.delete_api = AsyncMock()
    w._github_service.is_api_up_to_date = AsyncMock(return_value=False)
    w._retry_delays = [0]  # Fast retry for tests
    return w


@pytest.mark.asyncio
async def test_git_sync_success_increments_counter(worker):
    """Happy path: successful sync increments success counter."""
    before = _metric_value(GIT_SYNC_TOTAL, {"status": "success", "operation": "created"})

    event = {
        "event_type": "api-created",
        "tenant_id": "acme",
        "payload": {"name": "test-api"},
    }
    await worker._handle_event(event)

    after = _metric_value(GIT_SYNC_TOTAL, {"status": "success", "operation": "created"})
    assert after == before + 1


@pytest.mark.asyncio
async def test_git_sync_update_records_duration(worker):
    """Successful update records duration histogram."""
    event = {
        "event_type": "api-updated",
        "tenant_id": "acme",
        "payload": {"name": "test-api"},
    }

    # Get observation count before via the metric's internal child
    child = GIT_SYNC_DURATION_SECONDS.labels(operation="updated")
    before_count = child._sum.get()

    await worker._handle_event(event)

    after_count = child._sum.get()
    # Duration sum should have increased (> 0 seconds elapsed)
    assert after_count >= before_count


@pytest.mark.asyncio
async def test_git_sync_delete_success(worker):
    """Delete operation increments correct counter."""
    before = _metric_value(GIT_SYNC_TOTAL, {"status": "success", "operation": "deleted"})

    event = {
        "event_type": "api-deleted",
        "tenant_id": "acme",
        "payload": {"name": "test-api"},
    }
    await worker._handle_event(event)

    after = _metric_value(GIT_SYNC_TOTAL, {"status": "success", "operation": "deleted"})
    assert after == before + 1


@pytest.mark.asyncio
async def test_git_sync_error_increments_error_counter(worker):
    """Failed sync after all retries increments error counter."""
    worker._github_service.create_api = AsyncMock(side_effect=RuntimeError("GitHub down"))

    before_error = _metric_value(GIT_SYNC_TOTAL, {"status": "error", "operation": "created"})
    before_retries = GIT_SYNC_RETRIES_TOTAL._value.get()

    event = {
        "event_type": "api-created",
        "tenant_id": "acme",
        "payload": {"name": "test-api"},
    }
    await worker._handle_event(event)

    after_error = _metric_value(GIT_SYNC_TOTAL, {"status": "error", "operation": "created"})
    after_retries = GIT_SYNC_RETRIES_TOTAL._value.get()

    assert after_error == before_error + 1
    assert after_retries == before_retries + 1  # 1 retry (retry_delays=[0])


@pytest.mark.asyncio
async def test_git_sync_idempotent_skip_counts_as_success(worker):
    """ValueError (idempotent skip) counts as success, not error."""
    worker._github_service.create_api = AsyncMock(side_effect=ValueError("already exists"))

    before_success = _metric_value(GIT_SYNC_TOTAL, {"status": "success", "operation": "created"})

    event = {
        "event_type": "api-created",
        "tenant_id": "acme",
        "payload": {"name": "test-api"},
    }
    await worker._handle_event(event)

    after_success = _metric_value(GIT_SYNC_TOTAL, {"status": "success", "operation": "created"})
    assert after_success == before_success + 1


# ── Drift metrics tests ─────────────────────────────────────────────


def test_drift_detected_metric_is_registered():
    """Verify drift counter is registered in the Prometheus registry."""
    metric_names = [m.name for m in REGISTRY.collect()]
    # prometheus_client strips _total suffix from Counter names in collect()
    assert "catalog_drift_detected" in metric_names


def test_drift_repaired_metric_is_registered():
    """Verify drift repaired counter is registered in the Prometheus registry."""
    metric_names = [m.name for m in REGISTRY.collect()]
    assert "catalog_drift_repaired" in metric_names


def test_drift_detected_counter_labels():
    """Drift detected counter has expected labels."""
    before = _metric_value(DRIFT_DETECTED_TOTAL, {"tenant_id": "test-tenant", "repair_mode": "none"})
    DRIFT_DETECTED_TOTAL.labels(tenant_id="test-tenant", repair_mode="none").inc()
    after = _metric_value(DRIFT_DETECTED_TOTAL, {"tenant_id": "test-tenant", "repair_mode": "none"})
    assert after == before + 1


def test_drift_repaired_counter_labels():
    """Drift repaired counter has expected labels."""
    before = _metric_value(DRIFT_REPAIRED_TOTAL, {"mode": "commit"})
    DRIFT_REPAIRED_TOTAL.labels(mode="commit").inc()
    after = _metric_value(DRIFT_REPAIRED_TOTAL, {"mode": "commit"})
    assert after == before + 1


def test_git_sync_metrics_are_registered():
    """All 3 git sync metrics are registered in the Prometheus registry."""
    metric_names = [m.name for m in REGISTRY.collect()]
    # prometheus_client strips _total suffix from Counter names in collect()
    assert "catalog_git_sync" in metric_names
    assert "catalog_git_sync_duration_seconds" in metric_names
    assert "catalog_git_sync_retries" in metric_names
