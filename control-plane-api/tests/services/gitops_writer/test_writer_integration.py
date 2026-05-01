"""Integration tests for ``GitOpsWriter.create_api`` (Phase 4-2).

Spec §6.5 (CAB-2185 B-FLOW). Uses the ``integration_db`` fixture (real
PostgreSQL) so ``pg_advisory_lock`` and the ``api_catalog`` upsert run
against the production schema. The Git side uses
:class:`InMemoryCatalogGitClient` to keep the suite hermetic.

These tests are auto-skipped when ``DATABASE_URL`` is not set.
"""

from __future__ import annotations

import pytest
import yaml
from sqlalchemy import select

from src.models.catalog import APICatalog
from src.services.gitops_writer.exceptions import (
    GitOpsConflictError,
    GitOpsRaceExhaustedError,
    InfrastructureBugError,
    InvalidApiNameError,
    LegacyCollisionError,
)
from src.services.gitops_writer.models import ApiCreatePayload
from src.services.gitops_writer.writer import GitOpsWriter
from tests.services._fakes import InMemoryCatalogGitClient, _RaceOnceCatalogGitClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def _payload(
    *,
    name: str = "petstore",
    backend_url: str = "https://httpbin.org/anything",
    version: str = "1.0.0",
    tags: tuple[str, ...] = (),
) -> ApiCreatePayload:
    return ApiCreatePayload(
        api_name=name,
        display_name=name.replace("-", " ").title(),
        version=version,
        backend_url=backend_url,
        tags=tags,
    )


@pytest.fixture
def fake_git() -> InMemoryCatalogGitClient:
    return InMemoryCatalogGitClient()


@pytest.fixture
def writer(integration_db, fake_git: InMemoryCatalogGitClient) -> GitOpsWriter:
    return GitOpsWriter(catalog_git_client=fake_git, db_session=integration_db)


async def _select_row(session, tenant_id: str, api_id: str) -> APICatalog | None:
    stmt = (
        select(APICatalog)
        .where(APICatalog.tenant_id == tenant_id)
        .where(APICatalog.api_id == api_id)
        .where(APICatalog.deleted_at.is_(None))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


class TestCaseACommit:
    async def test_creates_file_and_projects_row(
        self, writer: GitOpsWriter, fake_git: InMemoryCatalogGitClient, integration_db
    ) -> None:
        result = await writer.create_api(
            tenant_id="demo-gitops",
            contract_payload=_payload(),
            actor="alice",
        )

        assert result.api_id == "petstore"
        assert result.case == "created"
        assert result.git_path == "tenants/demo-gitops/apis/petstore/api.yaml"
        assert result.git_commit_sha
        assert result.catalog_content_hash
        # Git side: file exists with rendered content
        remote = await fake_git.get(result.git_path)
        assert remote is not None
        parsed = yaml.safe_load(remote.content)
        assert parsed["id"] == "petstore"
        assert parsed["name"] == "petstore"
        assert parsed["backend_url"] == "https://httpbin.org/anything"
        # DB side: projection persisted
        row = await _select_row(integration_db, "demo-gitops", "petstore")
        assert row is not None
        assert row.git_path == result.git_path
        assert row.git_commit_sha == result.git_commit_sha
        assert row.catalog_content_hash == result.catalog_content_hash


class TestPullRequestReleaseMode:
    async def test_creates_catalog_release_after_pr_merge_and_tag(
        self, fake_git: InMemoryCatalogGitClient, integration_db
    ) -> None:
        writer = GitOpsWriter(
            catalog_git_client=fake_git,
            db_session=integration_db,
            catalog_write_mode="pull_request",
        )

        result = await writer.create_api(
            tenant_id="demo-gitops",
            contract_payload=_payload(name="release-petstore", version="1.2.3"),
            actor="alice",
        )

        assert result.case == "created"
        assert result.catalog_release is not None
        assert result.catalog_release.pull_request_url.endswith("/pull/1")
        assert result.catalog_release.pull_request_number == 1
        assert result.catalog_release.source_branch.startswith("stoa/api/demo-gitops/release-petstore/v1.2.3/")
        assert result.catalog_release.tag_name.startswith("stoa/api/demo-gitops/release-petstore/v1.2.3/")
        assert result.git_commit_sha == result.catalog_release.merge_commit_sha

        row = await _select_row(integration_db, "demo-gitops", "release-petstore")
        assert row is not None
        assert row.catalog_release_id == result.catalog_release.release_id
        assert row.catalog_release_tag == result.catalog_release.tag_name
        assert row.catalog_pr_url == result.catalog_release.pull_request_url
        assert row.catalog_pr_number == result.catalog_release.pull_request_number
        assert row.catalog_source_branch == result.catalog_release.source_branch
        assert row.catalog_merge_commit_sha == result.catalog_release.merge_commit_sha


class TestCaseBIdempotent:
    async def test_same_payload_replays_idempotently(self, writer: GitOpsWriter, integration_db) -> None:
        first = await writer.create_api(
            tenant_id="demo-gitops",
            contract_payload=_payload(),
            actor="alice",
        )
        # The fake's create_or_update is one-shot; second create from the
        # same writer instance follows the Case B (file present, same hash)
        # branch and re-projects without committing again.
        second = await writer.create_api(
            tenant_id="demo-gitops",
            contract_payload=_payload(),
            actor="alice",
        )
        assert second.case == "idempotent"
        assert second.git_commit_sha == first.git_commit_sha
        assert second.catalog_content_hash == first.catalog_content_hash
        # Single row persisted (not two).
        rows = (
            (
                await integration_db.execute(
                    select(APICatalog).where(
                        APICatalog.tenant_id == "demo-gitops",
                        APICatalog.api_id == "petstore",
                        APICatalog.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1


class TestCaseCConflict:
    async def test_different_hash_raises_409(self, writer: GitOpsWriter, fake_git: InMemoryCatalogGitClient) -> None:
        await writer.create_api(
            tenant_id="demo-gitops",
            contract_payload=_payload(backend_url="https://httpbin.org/anything"),
            actor="alice",
        )
        with pytest.raises(GitOpsConflictError):
            await writer.create_api(
                tenant_id="demo-gitops",
                contract_payload=_payload(backend_url="https://other.example/anything"),
                actor="alice",
            )


class TestRaceRetry:
    async def test_race_then_idempotent_succeeds(self, integration_db) -> None:
        # Render the YAML the writer will produce so the racer can seed
        # the same bytes (forcing Case B on retry rather than Case C).
        from src.services.catalog.write_api_yaml import render_api_yaml

        race_yaml = render_api_yaml(
            tenant_id="demo-gitops",
            api_name="petstore",
            version="1.0.0",
            backend_url="https://httpbin.org/anything",
            display_name="Petstore",
        ).encode("utf-8")
        racer = _RaceOnceCatalogGitClient(race_content=race_yaml)
        writer = GitOpsWriter(catalog_git_client=racer, db_session=integration_db)
        result = await writer.create_api(
            tenant_id="demo-gitops",
            contract_payload=_payload(),
            actor="alice",
        )
        # First attempt raised, second attempt found the same file → Case B.
        assert result.case == "idempotent"

    async def test_race_exhausted_raises_503(self, integration_db) -> None:
        from src.services.catalog_git_client.github_contents import CatalogShaConflictError
        from src.services.catalog_git_client.models import RemoteCommit

        class AlwaysRaceClient(InMemoryCatalogGitClient):
            async def create_or_update(self, **kw) -> RemoteCommit:
                raise CatalogShaConflictError(
                    path=kw["path"], expected_sha=kw["expected_sha"], status=409, message="forced race"
                )

        always = AlwaysRaceClient()
        writer = GitOpsWriter(catalog_git_client=always, db_session=integration_db)
        with pytest.raises(GitOpsRaceExhaustedError) as exc:
            await writer.create_api(
                tenant_id="demo-gitops",
                contract_payload=_payload(),
                actor="alice",
            )
        assert exc.value.attempts == 3


class TestStep12InfrastructureBug:
    async def test_read_at_commit_returns_none_raises_500_grade_error(
        self, integration_db, fake_git: InMemoryCatalogGitClient
    ) -> None:
        class LosesContentClient(InMemoryCatalogGitClient):
            async def read_at_commit(self, path: str, commit_sha: str) -> bytes | None:
                return None  # simulate Git remote losing the path

        loses = LosesContentClient()
        writer = GitOpsWriter(catalog_git_client=loses, db_session=integration_db)
        with pytest.raises(InfrastructureBugError):
            await writer.create_api(
                tenant_id="demo-gitops",
                contract_payload=_payload(),
                actor="alice",
            )


class TestStep14PreservesNonProjectedColumns:
    async def test_target_gateways_preserved_on_re_adoption(
        self, integration_db, fake_git: InMemoryCatalogGitClient
    ) -> None:
        existing = APICatalog(
            tenant_id="demo-gitops",
            api_id="petstore",
            api_name="petstore",
            version="1.0.0",
            status="active",
            tags=[],
            portal_published=False,
            audience="public",
            api_metadata={"display_name": "Manually set"},
            openapi_spec={"openapi": "3.0.0", "info": {"title": "Pet"}},
            target_gateways=["webmethods-prod", "kong-staging"],
            git_path="tenants/demo-gitops/apis/petstore/api.yaml",
            git_commit_sha="0" * 40,
            catalog_content_hash="0" * 64,
        )
        integration_db.add(existing)
        await integration_db.flush()
        # Seed Git so classify_legacy returns GITOPS_CREATED (cat A re-adoption).
        from src.services.catalog.write_api_yaml import render_api_yaml

        rendered = render_api_yaml(
            tenant_id="demo-gitops",
            api_name="petstore",
            version="1.0.0",
            backend_url="https://httpbin.org/anything",
            display_name="Petstore",
        ).encode("utf-8")
        fake_git.seed("tenants/demo-gitops/apis/petstore/api.yaml", rendered)

        writer = GitOpsWriter(catalog_git_client=fake_git, db_session=integration_db)
        await writer.create_api(
            tenant_id="demo-gitops",
            contract_payload=_payload(),
            actor="alice",
        )
        row = await _select_row(integration_db, "demo-gitops", "petstore")
        assert row is not None
        # The reserved columns survive the upsert.
        assert row.target_gateways == ["webmethods-prod", "kong-staging"]
        assert row.openapi_spec == {"openapi": "3.0.0", "info": {"title": "Pet"}}


class TestStep7AntiCollision:
    async def test_uuid_hard_drift_raises_409(self, writer: GitOpsWriter, integration_db) -> None:
        existing = APICatalog(
            tenant_id="demo",
            api_id="petstore",
            api_name="petstore",
            version="1.0.0",
            status="active",
            tags=[],
            portal_published=False,
            audience="public",
            api_metadata={},
            git_path="tenants/demo/apis/00000000-0000-0000-0000-000000000000/api.yaml",
            git_commit_sha="dead" * 10,
        )
        integration_db.add(existing)
        await integration_db.flush()

        with pytest.raises(LegacyCollisionError) as exc:
            await writer.create_api(
                tenant_id="demo",
                contract_payload=_payload(),
                actor="alice",
            )
        assert exc.value.category == "B"

    async def test_pre_gitops_raises_409(self, writer: GitOpsWriter, integration_db) -> None:
        existing = APICatalog(
            tenant_id="demo",
            api_id="petstore",
            api_name="petstore",
            version="1.0.0",
            status="active",
            tags=[],
            portal_published=False,
            audience="public",
            api_metadata={},
            git_path=None,
            git_commit_sha=None,
        )
        integration_db.add(existing)
        await integration_db.flush()

        with pytest.raises(LegacyCollisionError) as exc:
            await writer.create_api(
                tenant_id="demo",
                contract_payload=_payload(),
                actor="alice",
            )
        assert exc.value.category == "D"

    async def test_orphan_db_raises_409(
        self, writer: GitOpsWriter, integration_db, fake_git: InMemoryCatalogGitClient
    ) -> None:
        existing = APICatalog(
            tenant_id="demo",
            api_id="petstore",
            api_name="petstore",
            version="1.0.0",
            status="active",
            tags=[],
            portal_published=False,
            audience="public",
            api_metadata={},
            git_path="tenants/demo/apis/petstore/api.yaml",
            git_commit_sha="aaaa" * 10,
        )
        integration_db.add(existing)
        await integration_db.flush()
        # Git side empty → file does not exist → ORPHAN_DB.
        with pytest.raises(LegacyCollisionError) as exc:
            await writer.create_api(
                tenant_id="demo",
                contract_payload=_payload(),
                actor="alice",
            )
        assert exc.value.category == "C"

    async def test_healthy_adoptable_proceeds(
        self,
        writer: GitOpsWriter,
        integration_db,
        fake_git: InMemoryCatalogGitClient,
    ) -> None:
        existing = APICatalog(
            tenant_id="demo",
            api_id="petstore",
            api_name="petstore",
            version="1.0.0",
            status="active",
            tags=[],
            portal_published=False,
            audience="public",
            api_metadata={},
            git_path="tenants/demo/apis/petstore/api.yaml",
            git_commit_sha="cafe" * 10,
        )
        integration_db.add(existing)
        await integration_db.flush()
        # Seed Git so the row is classified HEALTHY_ADOPTABLE.
        from src.services.catalog.write_api_yaml import render_api_yaml

        rendered = render_api_yaml(
            tenant_id="demo",
            api_name="petstore",
            version="1.0.0",
            backend_url="https://httpbin.org/anything",
            display_name="Petstore",
        ).encode("utf-8")
        fake_git.seed("tenants/demo/apis/petstore/api.yaml", rendered)

        result = await writer.create_api(
            tenant_id="demo",
            contract_payload=_payload(),
            actor="alice",
        )
        # Re-adoption took the idempotent (Case B) branch since the seeded
        # content matches the rendered YAML byte-for-byte.
        assert result.case == "idempotent"


class TestStep2InvalidName:
    async def test_uuid_shaped_name_rejected_422(self, writer: GitOpsWriter) -> None:
        payload = ApiCreatePayload(
            api_name="00000000-0000-0000-0000-000000000000",
            display_name="UUID API",
            version="1.0.0",
            backend_url="https://httpbin.org/anything",
        )
        with pytest.raises(InvalidApiNameError):
            await writer.create_api(
                tenant_id="demo-gitops",
                contract_payload=payload,
                actor="alice",
            )

    async def test_empty_name_rejected_422(self, writer: GitOpsWriter) -> None:
        payload = ApiCreatePayload(
            api_name="",
            display_name="Empty",
            version="1.0.0",
            backend_url="https://httpbin.org/anything",
        )
        with pytest.raises(InvalidApiNameError):
            await writer.create_api(
                tenant_id="demo-gitops",
                contract_payload=payload,
                actor="alice",
            )
