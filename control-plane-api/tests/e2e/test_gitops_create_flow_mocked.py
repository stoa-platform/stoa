"""End-to-end mocked tests for the GitOps create flow.

Spec §6.5 / §6.13 / §11 audit-informed (CAB-2185 B-FLOW). The Git side is
faked via :class:`InMemoryCatalogGitClient` so no real GitHub call is made.
The DB side uses ``integration_db`` (real PostgreSQL) for the cases that
need ``pg_advisory_lock`` to behave; pure-mock tests cover the flag-OFF
fall-through and the step-2 422 short-circuit.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.models.catalog import APICatalog
from tests.services._fakes import InMemoryCatalogGitClient

_TEST_TENANT_PREFIX = "e2e-gitops-"
_KAFKA_PATH = "src.routers.apis.kafka_service"
_BUILD_CLIENT_PATH = "src.routers.apis._build_catalog_git_client"


@pytest.fixture
def fake_git_client() -> InMemoryCatalogGitClient:
    return InMemoryCatalogGitClient()


@pytest.fixture
def patch_catalog_git_client(fake_git_client: InMemoryCatalogGitClient):
    with patch(_BUILD_CLIENT_PATH, return_value=fake_git_client):
        yield fake_git_client


@pytest.fixture
def gitops_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "GITOPS_CREATE_API_ENABLED", True)
    monkeypatch.setattr(settings, "GITOPS_ELIGIBLE_TENANTS", ["acme"])
    yield


@pytest.fixture
def gitops_flag_off(monkeypatch):
    monkeypatch.setattr(settings, "GITOPS_CREATE_API_ENABLED", False)
    monkeypatch.setattr(settings, "GITOPS_ELIGIBLE_TENANTS", [])
    yield


@pytest.fixture
async def integration_session_factory() -> AsyncGenerator:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration E2E tests")
    engine = create_async_engine(url, echo=False)

    # Mirror ``conftest_integration.integration_db``: create the ``stoa``
    # schema + all model tables before the test runs. The factory pattern
    # we use here (multiple short-lived sessions per test) bypasses the
    # shared fixture, so we must bootstrap the schema ourselves.
    from sqlalchemy import text

    from src.database import Base

    # Import every model so ``Base.metadata`` knows about all tables.
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
                text("DELETE FROM api_catalog WHERE tenant_id LIKE :p").bindparams(p=f"{_TEST_TENANT_PREFIX}%")
            )
            await session.commit()
        await engine.dispose()


@pytest.fixture
def app_with_real_db(app, mock_user_tenant_admin, integration_session_factory):
    """App where ``get_db`` yields from a real PostgreSQL connection.

    Auto-skipped when ``DATABASE_URL`` is missing. The session is committed
    when the request handler returns (matching the real ``get_db`` lifecycle)
    so the cleanup in :func:`integration_session_factory` removes the data
    afterwards.
    """
    from src.auth.dependencies import get_current_user
    from src.database import get_db

    async def override_get_current_user():
        return mock_user_tenant_admin

    async def override_get_db():
        async with integration_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    from tests.conftest import _add_http_bearer_overrides

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db
    _add_http_bearer_overrides(app)
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
def integration_client(app_with_real_db):
    with TestClient(app_with_real_db) as c:
        yield c


def _payload(name: str = "petstore", **overrides) -> dict:
    body = {
        "name": name,
        "display_name": "Petstore",
        "version": "1.0.0",
        "backend_url": "https://httpbin.org/anything",
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Pure-mock tests (no DATABASE_URL required)
# ---------------------------------------------------------------------------


class TestFlagOffUsesLegacyPath:
    def test_legacy_handler_runs_when_flag_off(
        self,
        gitops_flag_off,
        app_with_tenant_admin,
        client_as_tenant_admin,
    ) -> None:
        """With the flag OFF, the legacy DB-first path runs and emits Kafka.

        Verifies the spec §6.13 fallback semantics: existing callers see
        identical behaviour until Phase 6 strangler.
        """
        with patch("src.routers.apis.CatalogRepository"), patch(_KAFKA_PATH) as mock_kafka:
            mock_kafka.emit_api_created = AsyncMock(return_value="evt-1")
            mock_kafka.emit_audit_event = AsyncMock(return_value="evt-2")
            with patch(_BUILD_CLIENT_PATH) as build_client:
                resp = client_as_tenant_admin.post(
                    "/v1/tenants/acme/apis",
                    json=_payload(),
                )
        assert resp.status_code == 200
        # Legacy path emits Kafka.
        assert mock_kafka.emit_api_created.await_count == 1
        # GitOps client factory NEVER invoked.
        assert build_client.call_count == 0


class TestUuidShapedNameRejected:
    def test_uuid_name_returns_422_without_db_writes(
        self,
        gitops_flag_on,
        patch_catalog_git_client,
        app_with_tenant_admin,
        client_as_tenant_admin,
        mock_db_session,
    ) -> None:
        """The writer rejects UUID-shaped slugs at step 2 — before any DB call.

        Tests the §6.5 step 2 garde-fou with a fully-mocked session: no
        ``pg_advisory_lock`` is issued because the InvalidApiNameError is
        raised first.
        """
        with patch(_KAFKA_PATH):
            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json=_payload(name="00000000-0000-0000-0000-000000000000"),
            )
        # _slugify lowercases / dashes — UUID stays UUID-shaped.
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Real-DB E2E tests (auto-skip without DATABASE_URL)
# ---------------------------------------------------------------------------


class TestNoKafkaWhenFlagOnUsesGitops:
    """End-to-end Kafka-skip assertion via writer-level orchestration.

    Spec §6.13: ``stoa.api.lifecycle`` is NOT emitted on the GitOps path.
    Verified at the router boundary by spying on ``kafka_service`` while a
    successful create is dispatched through the GitOps branch.
    """

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_kafka_emit_api_created_not_invoked_on_gitops_path(
        self,
        gitops_flag_on,
        patch_catalog_git_client,
        integration_session_factory,
    ) -> None:
        tenant_id = f"{_TEST_TENANT_PREFIX}no-kafka"
        # Run the writer directly through the helper that the handler uses;
        # this preserves the post-condition (no Kafka emit) without going
        # through the auth-gated FastAPI route layer.
        from src.routers.apis import APICreate, _create_api_gitops
        from src.services.gitops_writer import ApiCreatePayload  # noqa: F401  (validates re-export)

        api_body = APICreate(
            name="petstore",
            display_name="Petstore",
            version="1.0.0",
            backend_url="https://httpbin.org/anything",
        )

        async with integration_session_factory() as session:
            with patch(_KAFKA_PATH) as kafka_spy:
                kafka_spy.emit_api_created = AsyncMock()
                kafka_spy.emit_audit_event = AsyncMock()

                # Use a stand-in user with permissions for this tenant.
                from src.auth import User

                user = User(
                    id="e2e-test-user",
                    email="e2e@test.invalid",
                    username="e2e-test",
                    roles=["tenant-admin"],
                    tenant_id=tenant_id,
                )

                response = await _create_api_gitops(
                    tenant_id=tenant_id,
                    api=api_body,
                    user=user,
                    db=session,
                )

                assert response.id == "petstore"
                assert response.name == "petstore"
                # Kafka NOT emitted on the GitOps path — spec §6.13.
                assert kafka_spy.emit_api_created.await_count == 0

        # Verify projection persisted.
        async with integration_session_factory() as session:
            stmt = (
                select(APICatalog)
                .where(APICatalog.tenant_id == tenant_id)
                .where(APICatalog.api_id == "petstore")
                .where(APICatalog.deleted_at.is_(None))
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            assert row is not None
            assert row.git_path == f"tenants/{tenant_id}/apis/petstore/api.yaml"
            assert row.git_commit_sha is not None
            assert row.catalog_content_hash is not None


class TestCaseCConflictReturns409:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_existing_remote_with_different_hash_raises_conflict(
        self,
        gitops_flag_on,
        patch_catalog_git_client,
        integration_session_factory,
    ) -> None:
        from fastapi import HTTPException

        from src.auth import User
        from src.routers.apis import APICreate, _create_api_gitops

        tenant_id = f"{_TEST_TENANT_PREFIX}case-c"
        # First POST succeeds.
        api_body = APICreate(
            name="petstore",
            display_name="Petstore",
            version="1.0.0",
            backend_url="https://httpbin.org/anything",
        )
        user = User(
            id="e2e-test-user",
            email="e2e@test.invalid",
            username="e2e-test",
            roles=["tenant-admin"],
            tenant_id=tenant_id,
        )
        async with integration_session_factory() as session:
            with patch(_KAFKA_PATH):
                await _create_api_gitops(tenant_id=tenant_id, api=api_body, user=user, db=session)

        # Second POST with a different backend_url → Case C → 409.
        api_body_drifted = APICreate(
            name="petstore",
            display_name="Petstore",
            version="1.0.0",
            backend_url="https://other.example/anything",
        )
        async with integration_session_factory() as session:
            with patch(_KAFKA_PATH):
                with pytest.raises(HTTPException) as exc:
                    await _create_api_gitops(tenant_id=tenant_id, api=api_body_drifted, user=user, db=session)
        assert exc.value.status_code == 409


class TestTargetGatewaysPreservedOnReadoption:
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_existing_row_target_gateways_survive_gitops_create(
        self,
        gitops_flag_on,
        patch_catalog_git_client,
        integration_session_factory,
        fake_git_client: InMemoryCatalogGitClient,
    ) -> None:
        from src.auth import User
        from src.routers.apis import APICreate, _create_api_gitops
        from src.services.catalog.write_api_yaml import render_api_yaml

        tenant_id = f"{_TEST_TENANT_PREFIX}preserve"
        # Pre-populate a row with target_gateways + stale DB-only openapi_spec.
        async with integration_session_factory() as session:
            session.add(
                APICatalog(
                    tenant_id=tenant_id,
                    api_id="petstore",
                    api_name="petstore",
                    version="1.0.0",
                    status="active",
                    tags=[],
                    portal_published=False,
                    audience="public",
                    api_metadata={"display_name": "Manually set"},
                    openapi_spec={"openapi": "3.0.0"},
                    target_gateways=["webmethods-prod"],
                    git_path=f"tenants/{tenant_id}/apis/petstore/api.yaml",
                    git_commit_sha="0" * 40,
                    catalog_content_hash="0" * 64,
                )
            )
            await session.commit()

        rendered = render_api_yaml(
            tenant_id=tenant_id,
            api_name="petstore",
            version="1.0.0",
            backend_url="https://httpbin.org/anything",
            display_name="Petstore",
        ).encode("utf-8")
        fake_git_client.seed(f"tenants/{tenant_id}/apis/petstore/api.yaml", rendered)

        api_body = APICreate(
            name="petstore",
            display_name="Petstore",
            version="1.0.0",
            backend_url="https://httpbin.org/anything",
        )
        user = User(
            id="e2e-test-user",
            email="e2e@test.invalid",
            username="e2e-test",
            roles=["tenant-admin"],
            tenant_id=tenant_id,
        )
        async with integration_session_factory() as session:
            with patch(_KAFKA_PATH):
                await _create_api_gitops(tenant_id=tenant_id, api=api_body, user=user, db=session)

        async with integration_session_factory() as session:
            stmt = (
                select(APICatalog)
                .where(APICatalog.tenant_id == tenant_id)
                .where(APICatalog.api_id == "petstore")
                .where(APICatalog.deleted_at.is_(None))
            )
            row = (await session.execute(stmt)).scalar_one()
            # Deployment-owned columns are untouched; API description is
            # re-projected from the Git-owned openapi.yaml sibling.
            assert row.target_gateways == ["webmethods-prod"]
            assert row.openapi_spec is not None
            assert row.openapi_spec["openapi"] == "3.0.3"
            assert row.openapi_spec["info"]["title"] == "Petstore"
