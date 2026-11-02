"""GitOps logs retain context without copying untrusted exception content."""

from typing import NoReturn
from unittest.mock import AsyncMock

import pytest
from structlog.testing import capture_logs

from src.services.catalog_reconciler.metrics import CATALOG_SYNC_STATUS_TOTAL
from src.services.catalog_reconciler.worker import CatalogReconcilerWorker
from src.services.gitops_writer.writer import GitOpsWriter
from tests.services._fakes import InMemoryCatalogGitClient

# Deliberately fictitious credentials; never use real credentials in fixtures.
SENSITIVE_URL = "https://fixture-user:synthetic-password@example.invalid?token=synthetic-token"
GIT_PATH = "tenants/log-safety/apis/petstore/api.yaml"


def _unused_session_factory() -> NoReturn:
    raise AssertionError("Invalid Git content must not reach the database")


def _assert_safe(record: dict) -> None:
    rendered = repr(record)
    for sensitive in (SENSITIVE_URL, "synthetic-password", "synthetic-token"):
        assert sensitive not in rendered
    assert "exc_info" not in record
    assert "exception" not in record


def test_yaml_error_logs_status_without_source_content() -> None:
    worker = CatalogReconcilerWorker(
        catalog_git_client=InMemoryCatalogGitClient(), db_session_factory=_unused_session_factory
    )
    sample = CATALOG_SYNC_STATUS_TOTAL.labels(tenant_id="log-safety", api_id="petstore", status="failed")
    before = sample._value.get()
    with capture_logs() as records:
        result = worker._parse_and_validate_yaml(
            content_bytes=f"backend_url: [{SENSITIVE_URL}\n".encode(),
            tenant_id="log-safety",
            api_name="petstore",
            commit_sha="fixture-commit",
            content_hash="fixture-hash",
            git_path=GIT_PATH,
        )
    assert result is None
    record = records[0]
    _assert_safe(record)
    assert record["event"] == "catalog_sync_status"
    assert (record["tenant_id"], record["api_id"], record["status"]) == ("log-safety", "petstore", "failed")
    assert record["git_path"] == GIT_PATH
    assert record["last_error"] == "api.yaml parse error"
    assert sample._value.get() - before == 1


@pytest.mark.parametrize("field", ["name", "id"])
async def test_validation_error_does_not_log_untrusted_field(field: str) -> None:
    client = InMemoryCatalogGitClient()
    content = {"name": "petstore", "id": "petstore", "version": "1.0.0", "backend_url": SENSITIVE_URL}
    content[field] = SENSITIVE_URL
    client.seed(GIT_PATH, "\n".join(f"{key}: {value}" for key, value in content.items()).encode())
    worker = CatalogReconcilerWorker(catalog_git_client=client, db_session_factory=_unused_session_factory)
    with capture_logs() as records:
        key = await worker._reconcile_one_path(GIT_PATH)
    assert key == ("log-safety", "petstore")
    record = records[0]
    _assert_safe(record)
    assert record["status"] == "failed"
    assert record["last_error"] == "api.yaml or OpenAPI validation failed"
    assert record["git_commit_sha"]
    assert record["catalog_content_hash"]


async def test_unlock_error_logs_type_without_connection_details() -> None:
    session = AsyncMock()
    session.execute.side_effect = RuntimeError(f"connection failed: {SENSITIVE_URL}")
    writer = GitOpsWriter(catalog_git_client=InMemoryCatalogGitClient(), db_session=session)
    with capture_logs() as records:
        await writer._release_advisory_lock(42)
    record = records[0]
    _assert_safe(record)
    assert record["event"] == "gitops_writer.advisory_unlock_failed"
    assert record["lock_key"] == 42
    assert record["error_type"] == "RuntimeError"


async def test_iteration_error_logs_type_without_exception_traceback() -> None:
    class FailingWorker(CatalogReconcilerWorker):
        async def _reconcile_iteration(self) -> None:
            await self.stop()
            raise RuntimeError(SENSITIVE_URL)

    worker = FailingWorker(catalog_git_client=InMemoryCatalogGitClient(), db_session_factory=_unused_session_factory)
    with capture_logs() as records:
        await worker.start()
    record = next(record for record in records if record["event"] == "catalog_reconciler.iteration_failed")
    _assert_safe(record)
    assert record["error_type"] == "RuntimeError"
    assert record["log_level"] == "error"
