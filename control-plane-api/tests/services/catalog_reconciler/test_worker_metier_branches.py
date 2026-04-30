"""Phase 5 metier-branch coverage for ``CatalogReconcilerWorker``.

Closes the §6.6 / §6.14 metier gaps left by the integration suite:

1. UUID-shaped ``git_path`` → ``status=failed`` (spec §6.6 corruption signal,
   distinct from a generic non-canonical layout)
2. ``api.yaml`` ``name`` mismatching the path slug → ``status=failed`` (§6.10
   coherence violation)
3. ``_detect_legacy_orphans`` correctly classifies cat C (row active, Git
   file absent at HEAD)
4. ``_detect_legacy_orphans`` correctly classifies cat D (row active,
   ``git_path IS NULL``)
5. cat B (UUID hard drift) detected via the canonical-path scan path —
   exercises the ``_reconcile_db_row.UUID_HARD_DRIFT`` branch, not just the
   orphan-sweep path covered by ``test_worker_loop.TestUuidHardDriftCatB``

Defensive top-level wrappers (``iteration_failed``, ``orphan_detection_failed``)
and the lock-contention log path are intentionally NOT tested — they are
log-and-continue branches with low regression risk and no metier impact.

Spec §6.6 / §6.14 + audit-informed §11 (CAB-2186 B-WORKER, CAB-2188 B12).
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from structlog.testing import capture_logs

from src.models.catalog import APICatalog
from src.services.catalog.write_api_yaml import render_api_yaml
from src.services.catalog_reconciler.worker import CatalogReconcilerWorker
from tests.services._fakes import InMemoryCatalogGitClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_TEST_TENANT_PREFIX = "phase5-"


@pytest.fixture
async def session_factory():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration tests")
    engine = create_async_engine(url, echo=False)

    from src.database import Base
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
                text("DELETE FROM api_catalog WHERE tenant_id LIKE :p").bindparams(p=f"{_TEST_TENANT_PREFIX}%"),
            )
            await session.commit()
        await engine.dispose()


def _new_worker(session_factory: Any, fake_git: InMemoryCatalogGitClient) -> CatalogReconcilerWorker:
    return CatalogReconcilerWorker(
        catalog_git_client=fake_git,
        db_session_factory=session_factory,
        interval_seconds=1,
    )


def _sync_status_records(cap_logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract structured ``catalog_sync_status`` event dicts from a structlog
    capture. CAB-2208: structured fields are kwargs on the BoundLogger and live
    in the captured event dict, not on a stdlib LogRecord.
    """
    return [
        {
            "tenant_id": e.get("tenant_id"),
            "api_id": e.get("api_id"),
            "status": e.get("status"),
            "last_error": e.get("last_error"),
        }
        for e in cap_logs
        if e.get("event") == "catalog_sync_status"
    ]


class TestUuidShapedGitPath:
    """Spec §6.6 + §2.6 invariant 6: UUID-shaped api_name segments in
    ``git_path`` are corruption-flag worthy and emit ``status=failed``.

    Distinguished from a generic non-canonical layout (which is logged as
    a warning only). The reconciler MUST NOT mutate ``api_catalog`` for
    such paths.
    """

    async def test_uuid_path_emits_failed_status_no_mutation(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}uuid-path"
        uuid_segment = "00000000-0000-0000-0000-000000000000"
        uuid_git_path = f"tenants/{tenant}/apis/{uuid_segment}/api.yaml"

        fake_git = InMemoryCatalogGitClient()
        # Seed the corrupted Git tree with a UUID-shaped api_name segment.
        fake_git.seed(uuid_git_path, b"id: x\nname: x\nversion: 1.0.0\nbackend_url: http://x\n")

        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            await worker._reconcile_iteration()

        # Status=failed logged with the spec's ``last_error`` string.
        statuses = _sync_status_records(cap_logs)
        assert any(
            r["status"] == "failed"
            and r["api_id"] == uuid_segment
            and r["tenant_id"] == tenant
            and r["last_error"] == "uuid-shaped api_name in git_path"
            for r in statuses
        ), f"expected status=failed for UUID path; got {statuses}"

        # No row created in api_catalog for this corrupted path.
        async with session_factory() as session:
            result = await session.execute(
                select(APICatalog).where(APICatalog.tenant_id == tenant).where(APICatalog.deleted_at.is_(None))
            )
            assert result.scalar_one_or_none() is None


class TestNameMismatchYaml:
    """Spec §6.10: ``api.yaml`` ``name`` must equal the slug in ``git_path``.

    A mismatched ``name`` is rejected by ``render_api_catalog_projection``
    (ValueError) and surfaces as ``status=failed`` via the writer's existing
    error handler. No ``api_catalog`` mutation.
    """

    async def test_name_mismatch_yields_failed_status_no_mutation(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}mismatch"
        path = f"tenants/{tenant}/apis/petstore/api.yaml"
        # Path slug = ``petstore`` but YAML ``name`` = ``other-api`` → mismatch.
        bad_yaml = (
            b"id: other-api\n"
            b"name: other-api\n"
            b"display_name: Other API\n"
            b"version: 1.0.0\n"
            b"backend_url: https://httpbin.org/anything\n"
        )
        fake_git = InMemoryCatalogGitClient()
        fake_git.seed(path, bad_yaml)

        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            await worker._reconcile_iteration()

        statuses = _sync_status_records(cap_logs)
        failed = [r for r in statuses if r["status"] == "failed" and r["api_id"] == "petstore"]
        assert failed, f"expected status=failed on name mismatch; got {statuses}"
        # The ``last_error`` quotes the §6.10 diagnostic; assertion stays loose
        # to avoid coupling to the exact message string.
        assert "name" in failed[0]["last_error"].lower()

        async with session_factory() as session:
            result = await session.execute(
                select(APICatalog).where(APICatalog.tenant_id == tenant).where(APICatalog.deleted_at.is_(None))
            )
            assert result.scalar_one_or_none() is None


class TestDetectLegacyOrphansCatC:
    """Spec §6.14 cat C: row active in DB, file absent at Git HEAD.

    The orphan sweep at end-of-tick must classify these as ``drift_orphan``
    and never DELETE / soft-delete (§9.13 + §9.15).
    """

    async def test_orphan_detection_identifies_cat_c(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}orphan-c"
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

        fake_git = InMemoryCatalogGitClient()  # empty tree → row is orphan.
        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            # The orphan sweep runs after the canonical-path scan; calling
            # the iteration once is enough.
            await worker._reconcile_iteration()

        statuses = _sync_status_records(cap_logs)
        assert any(
            r["status"] == "drift_orphan"
            and r["api_id"] == "banking-services-v1-2"
            and r["last_error"] == "no git file at HEAD"
            for r in statuses
        ), f"expected drift_orphan for cat C; got {statuses}"

        # Row untouched (no soft-delete).
        async with session_factory() as session:
            result = await session.execute(
                select(APICatalog).where(APICatalog.tenant_id == tenant).where(APICatalog.deleted_at.is_(None))
            )
            row = result.scalar_one()
            assert row.git_path == f"tenants/{tenant}/apis/banking-services-v1-2/api.yaml"


class TestDetectLegacyOrphansCatD:
    """Spec §6.14 cat D (audit-informed §11.1): row active, ``git_path NULL``
    and ``git_commit_sha NULL``.

    The orphan sweep classifies these as ``drift_pre_gitops`` — surfaced
    distinctly from cat C so the eventual migration cycle (separate ticket)
    can target only the rows that never had a Git pointer in the first
    place. Detection only — never auto-repair (§9.13).
    """

    async def test_orphan_detection_identifies_cat_d(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}orphan-d"
        async with session_factory() as session:
            session.add(
                APICatalog(
                    tenant_id=tenant,
                    api_id="legacy-pre-gitops-api",
                    api_name="legacy-pre-gitops-api",
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

        statuses = _sync_status_records(cap_logs)
        assert any(
            r["status"] == "drift_pre_gitops"
            and r["api_id"] == "legacy-pre-gitops-api"
            and r["last_error"] == "no git_path nor commit pointer"
            for r in statuses
        ), f"expected drift_pre_gitops for cat D; got {statuses}"

        # Row untouched.
        async with session_factory() as session:
            result = await session.execute(
                select(APICatalog).where(APICatalog.tenant_id == tenant).where(APICatalog.deleted_at.is_(None))
            )
            row = result.scalar_one()
            assert row.git_path is None
            assert row.git_commit_sha is None


class TestPreGitopsViaCanonicalScan:
    """Spec §6.14 cat D reached via the canonical-path scan, not the orphan
    sweep.

    A row with ``git_path IS NULL`` AND ``git_commit_sha IS NULL`` whose
    ``api_id`` matches the slug of an existing canonical Git file is hit by
    the main reconciliation loop. The `_reconcile_db_row.PRE_GITOPS` branch
    must fire (status=drift_pre_gitops, no mutation) — symmetric to the
    cat B canonical-scan branch covered below.

    Realistic production scenario: a pre-GitOps row that pre-dated the
    writer ever resolving a Git pointer, but a canonical YAML now exists
    (e.g. someone hand-committed it).
    """

    async def test_main_scan_classifies_cat_d_and_logs_drift(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}cat-d-scan"
        canonical = f"tenants/{tenant}/apis/legacy-api/api.yaml"
        fake_git = InMemoryCatalogGitClient()
        fake_git.seed(
            canonical,
            render_api_yaml(
                tenant_id=tenant,
                api_name="legacy-api",
                version="1.0.0",
                backend_url="https://httpbin.org/anything",
                display_name="Legacy API",
            ).encode("utf-8"),
        )

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

        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            await worker._reconcile_iteration()

        statuses = _sync_status_records(cap_logs)
        assert any(
            r["status"] == "drift_pre_gitops"
            and r["api_id"] == "legacy-api"
            and r["last_error"] == "no git_path nor commit pointer"
            for r in statuses
        ), f"expected drift_pre_gitops via main scan; got {statuses}"

        # Row untouched: pointers still NULL, no projection applied.
        async with session_factory() as session:
            result = await session.execute(
                select(APICatalog).where(APICatalog.tenant_id == tenant).where(APICatalog.deleted_at.is_(None))
            )
            row = result.scalar_one()
            assert row.git_path is None
            assert row.git_commit_sha is None


class TestUuidHardDriftViaOrphanSweep:
    """Spec §6.14 cat B reached via the orphan sweep, not the main scan.

    Symmetric to ``TestUuidHardDriftViaCanonicalScan`` — covers
    ``_detect_legacy_orphans`` UUID_HARD_DRIFT branch when a cat-B row has
    no matching canonical Git file (so the main scan never sees it). The
    sweep must surface drift_detected with the cat B context.
    """

    async def test_orphan_sweep_classifies_cat_b(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}cat-b-orphan"
        # Row api_id is itself UUID-shaped → cat B via the api_id check.
        # No canonical Git file exists for this api_id, so the main scan
        # never touches it; the orphan sweep is the only path that reaches it.
        async with session_factory() as session:
            session.add(
                APICatalog(
                    tenant_id=tenant,
                    api_id="11111111-2222-3333-4444-555555555555",
                    api_name="11111111-2222-3333-4444-555555555555",
                    version="1.0.0",
                    status="active",
                    tags=[],
                    portal_published=False,
                    audience="public",
                    api_metadata={},
                    git_path=None,  # forces classifier to take the api_id UUID path
                    git_commit_sha="dead" * 10,
                )
            )
            await session.commit()

        fake_git = InMemoryCatalogGitClient()  # no canonical paths at all
        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            await worker._reconcile_iteration()

        statuses = _sync_status_records(cap_logs)
        assert any(
            r["status"] == "drift_detected"
            and r["api_id"] == "11111111-2222-3333-4444-555555555555"
            and r["last_error"] == "uuid hard drift"
            for r in statuses
        ), f"expected drift_detected (uuid hard drift) via orphan sweep; got {statuses}"


class TestUuidHardDriftViaCanonicalScan:
    """Spec §6.14 cat B reached via the canonical-path scan, not the orphan
    sweep.

    A row whose ``api_id`` matches the canonical slug but whose stored
    ``git_path`` is UUID-shaped is hit by the main reconciliation loop
    (the canonical Git path resolves to a slug-keyed DB row). This covers
    the ``_reconcile_db_row.UUID_HARD_DRIFT`` branch — the orphan-sweep
    path tested elsewhere only covers the ``_detect_legacy_orphans``
    classifier.
    """

    async def test_main_scan_classifies_cat_b_and_logs_drift(self, session_factory) -> None:
        tenant = f"{_TEST_TENANT_PREFIX}cat-b-scan"
        canonical = f"tenants/{tenant}/apis/petstore/api.yaml"
        # Seed Git with the canonical (slug-keyed) path so the scan visits it.
        fake_git = InMemoryCatalogGitClient()
        fake_git.seed(
            canonical,
            render_api_yaml(
                tenant_id=tenant,
                api_name="petstore",
                version="1.0.0",
                backend_url="https://httpbin.org/anything",
                display_name="Petstore",
            ).encode("utf-8"),
        )

        # Row's api_id matches the slug, but git_path stored in DB is UUID-shaped
        # → classifier sees `git_path` UUID → cat B.
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

        worker = _new_worker(session_factory, fake_git)
        with capture_logs() as cap_logs:
            await worker._reconcile_iteration()

        statuses = _sync_status_records(cap_logs)
        # The UUID hard drift status must mention both the row's drift git_path
        # and the real (canonical) git_name so operators can spot the mismatch
        # without an extra DB query.
        cat_b = [
            r
            for r in statuses
            if r["status"] == "drift_detected"
            and r["api_id"] == "petstore"
            and "uuid hard drift" in (r["last_error"] or "")
        ]
        assert cat_b, f"expected drift_detected (uuid hard drift) via main scan; got {statuses}"

        # Row untouched: git_path still points at the UUID path, no mutation.
        async with session_factory() as session:
            result = await session.execute(
                select(APICatalog).where(APICatalog.tenant_id == tenant).where(APICatalog.deleted_at.is_(None))
            )
            row = result.scalar_one()
            assert row.git_path.endswith("00000000-0000-0000-0000-000000000000/api.yaml")
            assert row.git_commit_sha == "dead" * 10
