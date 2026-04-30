"""Unit tests for ``CATALOG_SYNC_STATUS_TOTAL`` (CAB-2208).

The Prometheus counter is the durable observability surface paired with the
``catalog_sync_status`` log line. These tests pin the wiring contract:

* both ``_log_sync_status`` helpers (writer + reconciler) increment exactly
  one sample per call,
* every status value declared in ``VALID_SYNC_STATUSES`` is accepted by the
  counter labels,
* the literal status values emitted in the source remain a subset of
  ``VALID_SYNC_STATUSES`` — protects against silent drift if a new status
  is introduced at an emission site without being registered.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.services.catalog_reconciler.metrics import (
    CATALOG_SYNC_STATUS_TOTAL,
    VALID_SYNC_STATUSES,
)
from src.services.catalog_reconciler.worker import CatalogReconcilerWorker
from src.services.gitops_writer.writer import GitOpsWriter

SERVICES_ROOT = Path(__file__).parent.parent.parent.parent / "src/services"
WRITER_FILE = SERVICES_ROOT / "gitops_writer/writer.py"
WORKER_FILE = SERVICES_ROOT / "catalog_reconciler/worker.py"


def _read_counter(*, tenant_id: str, api_id: str, status: str) -> float:
    sample = CATALOG_SYNC_STATUS_TOTAL.labels(
        tenant_id=tenant_id,
        api_id=api_id,
        status=status,
    )
    return sample._value.get()


@pytest.mark.parametrize("status", sorted(VALID_SYNC_STATUSES))
def test_writer_log_sync_status_increments_counter(status: str) -> None:
    tenant_id, api_id = "tenant-writer", f"api-{status}"
    before = _read_counter(tenant_id=tenant_id, api_id=api_id, status=status)

    GitOpsWriter._log_sync_status(
        tenant_id=tenant_id,
        api_id=api_id,
        status=status,
        git_commit_sha=None,
        catalog_content_hash=None,
        git_path=None,
    )

    after = _read_counter(tenant_id=tenant_id, api_id=api_id, status=status)
    assert after - before == pytest.approx(1.0)


@pytest.mark.parametrize("status", sorted(VALID_SYNC_STATUSES))
def test_reconciler_log_sync_status_increments_counter(status: str) -> None:
    tenant_id, api_id = "tenant-reconciler", f"api-{status}"
    before = _read_counter(tenant_id=tenant_id, api_id=api_id, status=status)

    CatalogReconcilerWorker._log_sync_status(
        tenant_id=tenant_id,
        api_id=api_id,
        status=status,
        git_commit_sha="deadbeef",
        catalog_content_hash="cafebabe",
        git_path=f"tenants/tenant-reconciler/apis/api-{status}/api.yaml",
        last_error=None,
    )

    after = _read_counter(tenant_id=tenant_id, api_id=api_id, status=status)
    assert after - before == pytest.approx(1.0)


def test_emitted_status_literals_are_a_subset_of_valid_statuses() -> None:
    """Static check: every ``status="<literal>"`` adjacent to a
    ``_log_sync_status`` call must be enumerated in ``VALID_SYNC_STATUSES``.

    If a new status literal lands at an emission site without being added
    to ``VALID_SYNC_STATUSES``, this test fails loudly. The reconciler also
    has a dynamic branch (``status=status``) where ``status`` is bound to a
    literal a few lines above; those literals are picked up by the same
    regex because they appear as ``status = "<literal>"`` assignments.
    """
    literal = re.compile(r'status\s*=\s*"([^"]+)"')
    found: set[str] = set()
    for src in (WRITER_FILE, WORKER_FILE):
        for match in literal.finditer(src.read_text()):
            found.add(match.group(1))

    extras = found - VALID_SYNC_STATUSES
    assert not extras, (
        f"Source emits status literals not declared in VALID_SYNC_STATUSES: {sorted(extras)}. "
        "Update src/services/catalog_reconciler/metrics.py::VALID_SYNC_STATUSES."
    )
