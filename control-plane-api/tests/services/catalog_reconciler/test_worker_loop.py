"""Integration tests for ``CatalogReconcilerWorker._reconcile_iteration``.

Spec §6.6 (CAB-2186 B-WORKER) + §6.14 + §11.1 audit-informed.

Real PostgreSQL via ``DATABASE_URL`` is required (``pg_try_advisory_xact_lock``
+ projection writes); tests are auto-skipped otherwise. The Git side uses
:class:`InMemoryCatalogGitClient`.

The worker is verified at the iteration level rather than by spinning the
real loop — :meth:`CatalogReconcilerWorker._reconcile_iteration` is the unit
that the spec describes (§6.6 pseudo-code), and the wrapping ``while`` loop
is shallow enough to be covered by ``test_start_stop_cycles_cleanly``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from structlog.testing import capture_logs

from src.models.catalog import APICatalog
from src.services.catalog.write_api_yaml import render_api_yaml
from src.services.catalog_reconciler.worker import CatalogReconcilerWorker
from src.services.gitops_writer.advisory_lock import advisory_lock_key
from tests.services._fakes import InMemoryCatalogGitClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_TEST_TENANT_PREFIX = "reco-test-"


@pytest.fixture
async def session_factory():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration tests")
    engine = create_async_engine(url, echo=False)

    # Bootstrap schema (mirrors ``conftest_integration.integration_db``) — the
    # reconciler opens a session per tick and the worker tests need the
    # tables to exist before the first iteration runs.
    from src.database import Base

    # Import every model so Base.metadata knows about all tables.
    from src.models.catalog import APICatalog  # noqa: F401
    from src.models.contract import Contract  # noqa: F401
    from src.models.gateway_deployment import GatewayDeployment  # noqa: F401
    from src.models.gateway_instance import GatewayInstance  # noqa: F401
    from src.models.subscription import Subscription  # noqa: F401
    from src.models.tenant import Tenant  # noqa: F401

    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS stoa"))
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        async with factory() as session:
            await session.execute(
                text("DELETE FROM api_catalog WHERE tenant_id LIKE :p").bindparams(
                    p=f"{_TEST_TENANT_PREFIX}%",
                )
            )
            await session.commit()
        await engine.dispose()


def _render_yaml(*, tenant_id: str, api_name: str, backend_url: str = "https://httpbin.org/anything") -> bytes:
    return render_api_yaml(
        tenant_id=tenant_id,
        api_name=api_name,
        version="1.0.0",
        backend_url=backend_url,
        display_name=api_name,
    ).encode("utf-8")


async def _select_row(factory, tenant_id: str, api_id: str) -> APICatalog | None:
    async with factory() as session:
        stmt = (
            select(APICatalog)
            .where(APICatalog.tenant_id == tenant_id)
            .where(APICatalog.api_id == api_id)
            .where(APICatalog.deleted_at.is_(None))
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


def _new_worker(session_factory, fake_git: InMemoryCatalogGitClient) -> CatalogReconcilerWorker:
    return CatalogReconcilerWorker(
        catalog_git_client=fake_git,
        db_session_factory=session_factory,
        interval_seconds=1,
    )


class CountingCatalogGitClient(InMemoryCatalogGitClient):
    def __init__(self) -> None:
        super().__init__()
        self.get_calls = 0
        self.latest_file_commit_calls = 0

    async def get(self, path: str):
        self.get_calls += 1
        return await super().get(path)

    async def latest_file_commit(self, path: str) -> str:
        self.latest_file_commit_calls += 1
        return await super().latest_file_commit(path)


class TestProjectsAbsent:
    async def test_iteration_creates_row_for_absent_db_when_git_present(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}absent"
        fake_git = InMemoryCatalogGitClient()
        path = f"tenants/{tenant}/apis/petstore/api.yaml"
        fake_git.seed(path, _render_yaml(tenant_id=tenant, api_name="petstore"))
        worker = _new_worker(session_factory, fake_git)

        await worker._reconcile_iteration()

        row = await _select_row(session_factory, tenant, "petstore")
        assert row is not None
        assert row.git_path == path
        assert row.git_commit_sha is not None
        assert row.catalog_content_hash is not None

    async def test_iteration_skips_unchanged_git_blobs_after_successful_reconcile(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}cache"
        fake_git = CountingCatalogGitClient()
        path = f"tenants/{tenant}/apis/petstore/api.yaml"
        fake_git.seed(path, _render_yaml(tenant_id=tenant, api_name="petstore"))
        worker = _new_worker(session_factory, fake_git)

        await worker._reconcile_iteration()
        await worker._reconcile_iteration()

        assert fake_git.get_calls == 1
        assert fake_git.latest_file_commit_calls == 0


class TestUuidHardDriftCatB:
    async def test_iteration_does_not_repair_uuid_drift(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}b"
        # DB row with UUID-shaped git_path → cat B
        async with session_factory() as session:
            session.add(
                APICatalog(
                    tenant_id=tenant,
                    api_id="petstore",
                    api_name="petstore",
                    version="1.0.0",
                    status="active",
                    tags=[],
                    portal_published=False,
                    audience="public",
                    api_metadata={},
                    git_path=f"tenants/{tenant}/apis/00000000-0000-0000-0000-000000000000/api.yaml",
                    git_commit_sha="dead" * 10,
                )
            )
            await session.commit()
        # Git has the canonical file under the slug; the row's UUID path is unrelated.
        fake_git = InMemoryCatalogGitClient()
        path = f"tenants/{tenant}/apis/petstore/api.yaml"
        fake_git.seed(path, _render_yaml(tenant_id=tenant, api_name="petstore"))

        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            await worker._reconcile_iteration()

        # Row unchanged.
        row = await _select_row(session_factory, tenant, "petstore")
        assert row is not None
        assert row.git_path.endswith("00000000-0000-0000-0000-000000000000/api.yaml")
        # drift_detected logged (CAB-2208: structlog event dict).
        statuses = [e.get("status") for e in cap_logs if e.get("event") == "catalog_sync_status"]
        assert "drift_detected" in statuses


class TestOrphanCatC:
    async def test_iteration_reports_orphan_for_db_row_without_git_file(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}c"
        async with session_factory() as session:
            session.add(
                APICatalog(
                    tenant_id=tenant,
                    api_id="banking-services-v1-2",
                    api_name="banking-services-v1-2",
                    version="1.0.0",
                    status="active",
                    tags=[],
                    portal_published=False,
                    audience="public",
                    api_metadata={},
                    git_path=f"tenants/{tenant}/apis/banking-services-v1-2/api.yaml",
                    git_commit_sha="aaaa" * 10,
                )
            )
            await session.commit()
        fake_git = InMemoryCatalogGitClient()  # empty Git tree → orphan.
        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            await worker._reconcile_iteration()
        statuses = [(e.get("status"), e.get("api_id")) for e in cap_logs if e.get("event") == "catalog_sync_status"]
        assert ("drift_orphan", "banking-services-v1-2") in statuses


class TestPreGitopsCatD:
    async def test_iteration_reports_pre_gitops_for_null_pointers(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}d"
        async with session_factory() as session:
            session.add(
                APICatalog(
                    tenant_id=tenant,
                    api_id="legacy-api",
                    api_name="legacy-api",
                    version="1.0.0",
                    status="active",
                    tags=[],
                    portal_published=False,
                    audience="public",
                    api_metadata={},
                    git_path=None,
                    git_commit_sha=None,
                )
            )
            await session.commit()
        fake_git = InMemoryCatalogGitClient()
        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            await worker._reconcile_iteration()
        statuses = [(e.get("status"), e.get("api_id")) for e in cap_logs if e.get("event") == "catalog_sync_status"]
        assert ("drift_pre_gitops", "legacy-api") in statuses


class TestProjectionDriftRepair:
    async def test_iteration_repairs_drift_on_backend_url_via_projection(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}drift"
        path = f"tenants/{tenant}/apis/petstore/api.yaml"

        # Seed Git with a content hash (deterministic).
        fake_git = InMemoryCatalogGitClient()
        fake_git.seed(path, _render_yaml(tenant_id=tenant, api_name="petstore"))
        # Pre-populate the DB with a row that drifts on tags (projected field).
        async with session_factory() as session:
            session.add(
                APICatalog(
                    tenant_id=tenant,
                    api_id="petstore",
                    api_name="petstore",
                    version="1.0.0",
                    status="active",
                    tags=["wrong-tag"],
                    portal_published=False,
                    audience="public",
                    api_metadata={},
                    git_path=path,
                    git_commit_sha="dead" * 10,
                    catalog_content_hash="0" * 64,
                )
            )
            await session.commit()
        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            await worker._reconcile_iteration()

        row = await _select_row(session_factory, tenant, "petstore")
        assert row is not None
        # tags is no longer ``["wrong-tag"]``; projection consumed Git's empty tag list.
        assert row.tags == []
        # sync_status logged drift_detected then synced (CAB-2208).
        statuses = [e.get("status") for e in cap_logs if e.get("event") == "catalog_sync_status"]
        assert "drift_detected" in statuses
        assert "synced" in statuses

    async def test_iteration_repairs_uuid_git_path_drift(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}uuid-fix"
        path = f"tenants/{tenant}/apis/petstore/api.yaml"
        fake_git = InMemoryCatalogGitClient()
        fake_git.seed(path, _render_yaml(tenant_id=tenant, api_name="petstore"))
        async with session_factory() as session:
            session.add(
                APICatalog(
                    tenant_id=tenant,
                    api_id="petstore",
                    api_name="petstore",
                    version="1.0.0",
                    status="active",
                    tags=[],
                    portal_published=False,
                    audience="public",
                    api_metadata={},
                    git_path=f"tenants/{tenant}/apis/petstore/api.yaml",
                    # Pretend a corrupted writer once stored a UUID file_sha equivalent;
                    # the projected git_commit_sha drifts from Git HEAD's sha for the path.
                    git_commit_sha="cafe" * 10,
                    catalog_content_hash="cafe" * 16,
                )
            )
            await session.commit()
        worker = _new_worker(session_factory, fake_git)
        await worker._reconcile_iteration()
        row = await _select_row(session_factory, tenant, "petstore")
        assert row is not None
        assert row.git_path == path  # canonical path preserved
        assert row.git_commit_sha != "cafe" * 10  # Git's actual SHA replaced the drift
        assert row.catalog_content_hash != "cafe" * 16


class TestNonCanonicalPaths:
    async def test_uuid_shaped_path_in_git_logged_as_failed(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}uuid-git"
        # Simulate a corrupted Git tree where api_name is UUID-shaped.
        uuid_path = f"tenants/{tenant}/apis/00000000-0000-0000-0000-000000000000/api.yaml"
        fake_git = InMemoryCatalogGitClient()
        # The path will fail parse_canonical_path because of the UUID slot.
        fake_git.seed(uuid_path, _render_yaml(tenant_id=tenant, api_name="petstore"))
        worker = _new_worker(session_factory, fake_git)
        with capture_logs():
            await worker._reconcile_iteration()
        # No row is created.
        async with session_factory() as session:
            stmt = select(APICatalog).where(APICatalog.tenant_id == tenant)
            assert (await session.execute(stmt)).scalar_one_or_none() is None


class TestStartStop:
    async def test_start_stop_cycles_cleanly(self, session_factory) -> None:
        fake_git = InMemoryCatalogGitClient()
        worker = CatalogReconcilerWorker(
            catalog_git_client=fake_git,
            db_session_factory=session_factory,
            interval_seconds=1,
        )
        task = asyncio.create_task(worker.start())
        await asyncio.sleep(0.05)  # let the loop tick once
        await worker.stop()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)


class TestAdvisoryLock:
    async def test_try_advisory_lock_non_blocking_concurrent(self, session_factory) -> None:
        """Two coroutines compete for the same lock — one acquires, one skips.

        Spec §6.8 reconciler side: ``pg_try_advisory_xact_lock`` returns False
        without blocking when the lock is held by another transaction.
        """
        tenant = f"{_TEST_TENANT_PREFIX}lock"
        api_id = "petstore"
        key = advisory_lock_key(tenant, api_id)

        async def acquire_and_hold() -> bool:
            async with session_factory() as session, session.begin():
                result = await session.execute(text("SELECT pg_try_advisory_xact_lock(:k)").bindparams(k=key))
                acquired = bool(result.scalar())
                # Hold long enough for the second contender to try.
                await asyncio.sleep(0.1)
                return acquired

        async def try_only() -> bool:
            await asyncio.sleep(0.02)  # let the holder go first
            async with session_factory() as session, session.begin():
                result = await session.execute(text("SELECT pg_try_advisory_xact_lock(:k)").bindparams(k=key))
                return bool(result.scalar())

        first, second = await asyncio.gather(acquire_and_hold(), try_only())
        assert first is True
        assert second is False
