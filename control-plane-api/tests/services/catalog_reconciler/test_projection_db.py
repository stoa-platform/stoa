"""DB-level tests for ``project_to_api_catalog``.

Spec §6.5 step 14, §6.9 (CAB-2186 B-WORKER, CAB-2180 B-CATALOG).

These tests use the ``integration_db`` fixture (PostgreSQL) and are skipped
automatically when ``DATABASE_URL`` is not set. They verify the contract
that GitOps writes NEVER touch ``target_gateways``, ``openapi_spec`` or
``metadata`` on UPDATE.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.models.catalog import APICatalog
from src.models.deployment import Deployment
from src.services.catalog_reconciler.projection import (
    ApiCatalogProjection,
    project_to_api_catalog,
)


def _projection(
    *,
    tenant_id: str = "demo-gitops",
    api_id: str = "petstore",
    version: str = "1.0.0",
    git_commit_sha: str = "a" * 40,
    catalog_content_hash: str = "b" * 64,
    git_path: str | None = None,
) -> ApiCatalogProjection:
    return ApiCatalogProjection(
        tenant_id=tenant_id,
        api_id=api_id,
        api_name=api_id,
        version=version,
        status="active",
        category="Banking",
        tags=["portal:published", "banking"],
        portal_published=True,
        audience="public",
        api_metadata={
            "name": api_id,
            "display_name": api_id,
            "version": version,
            "description": "",
            "backend_url": "http://example.invalid",
            "status": "active",
            "deployments": {"dev": True, "staging": False},
            "tags": ["portal:published", "banking"],
            "category": "Banking",
            "audience": "public",
        },
        git_path=git_path or f"tenants/{tenant_id}/apis/{api_id}/api.yaml",
        git_commit_sha=git_commit_sha,
        catalog_content_hash=catalog_content_hash,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_insert_creates_row_with_defaults(integration_db) -> None:
    proj = _projection()

    await project_to_api_catalog(integration_db, proj)

    result = await integration_db.execute(
        select(APICatalog).where(
            APICatalog.tenant_id == proj.tenant_id,
            APICatalog.api_id == proj.api_id,
        )
    )
    row = result.scalar_one()
    assert row.id is not None  # gen_random_uuid()
    assert row.api_name == "petstore"
    assert row.version == "1.0.0"
    assert row.status == "active"
    assert row.category == "Banking"
    assert row.tags == ["portal:published", "banking"]
    assert row.portal_published is True
    assert row.audience == "public"
    assert row.git_path == "tenants/demo-gitops/apis/petstore/api.yaml"
    assert row.git_commit_sha == "a" * 40
    assert row.catalog_content_hash == "b" * 64
    assert row.api_metadata["backend_url"] == "http://example.invalid"
    assert row.openapi_spec is None
    assert row.target_gateways == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_preserves_target_gateways(integration_db) -> None:
    """A pre-existing row with target_gateways and openapi_spec keeps them on UPDATE."""
    existing = APICatalog(
        tenant_id="demo-gitops",
        api_id="petstore",
        api_name="petstore",
        version="1.0.0",
        status="active",
        tags=[],
        portal_published=False,
        audience="public",
        api_metadata={"display_name": "Manually set", "backend_url": "http://legacy"},
        openapi_spec={"openapi": "3.0.0", "info": {"title": "Pet"}},
        target_gateways=["webmethods-prod", "kong-staging"],
    )
    integration_db.add(existing)
    await integration_db.flush()
    original_id = existing.id

    proj = _projection(git_commit_sha="c" * 40, catalog_content_hash="d" * 64)
    await project_to_api_catalog(integration_db, proj)

    result = await integration_db.execute(
        select(APICatalog).where(APICatalog.tenant_id == "demo-gitops", APICatalog.api_id == "petstore")
    )
    row = result.scalar_one()
    # PK preserved
    assert row.id == original_id
    # Projected fields updated
    assert row.git_commit_sha == "c" * 40
    assert row.catalog_content_hash == "d" * 64
    assert row.category == "Banking"
    assert row.tags == ["portal:published", "banking"]
    assert row.portal_published is True
    # Non-projected fields preserved
    assert row.target_gateways == ["webmethods-prod", "kong-staging"]
    assert row.openapi_spec == {"openapi": "3.0.0", "info": {"title": "Pet"}}
    assert row.api_metadata["display_name"] == "petstore"
    assert row.api_metadata["backend_url"] == "http://example.invalid"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_adopts_legacy_uuid_identity_collision(integration_db) -> None:
    """A canonical Git row adopts a unique legacy UUID row by name/version.

    Prod observed this as ``UNIQUE (tenant_id, api_name, version)`` failures:
    the canonical ``tenants/{tenant}/apis/{name}/api.yaml`` file existed, but
    the DB row still used a UUID ``api_id`` from the pre-GitOps writer. The
    reconciler must update that row in place so Git becomes the identity truth
    and PK-based references survive.
    """
    existing = APICatalog(
        tenant_id="demo-gitops",
        api_id="4d678b27-6691-43c9-9d23-c51c02176049",
        api_name="petstore",
        version="1.0.0",
        status="draft",
        tags=[],
        portal_published=False,
        audience="public",
        api_metadata={"display_name": "Legacy Petstore", "backend_url": "http://legacy"},
        openapi_spec={"openapi": "3.0.0", "info": {"title": "Legacy Petstore"}},
        target_gateways=["webmethods-prod"],
        git_path="tenants/demo-gitops/apis/4d678b27-6691-43c9-9d23-c51c02176049",
    )
    integration_db.add(existing)
    integration_db.add(
        Deployment(
            tenant_id="demo-gitops",
            api_id="4d678b27-6691-43c9-9d23-c51c02176049",
            api_name="Legacy Petstore",
            environment="dev",
            version="1.0.0",
            status="pending",
            deployed_by="test",
        )
    )
    await integration_db.flush()
    original_id = existing.id

    proj = _projection(api_id="petstore", git_commit_sha="c" * 40, catalog_content_hash="d" * 64)
    await project_to_api_catalog(integration_db, proj)

    result = await integration_db.execute(
        select(APICatalog).where(APICatalog.tenant_id == "demo-gitops", APICatalog.api_id == "petstore")
    )
    row = result.scalar_one()
    assert row.id == original_id
    assert row.api_id == "petstore"
    assert row.api_name == "petstore"
    assert row.git_path == "tenants/demo-gitops/apis/petstore/api.yaml"
    assert row.git_commit_sha == "c" * 40
    assert row.catalog_content_hash == "d" * 64
    assert row.target_gateways == ["webmethods-prod"]
    assert row.openapi_spec == {"openapi": "3.0.0", "info": {"title": "Legacy Petstore"}}

    deployment_result = await integration_db.execute(
        select(Deployment).where(Deployment.tenant_id == "demo-gitops", Deployment.api_id == "petstore")
    )
    deployment = deployment_result.scalar_one()
    assert deployment.api_name == "petstore"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_update_adopts_legacy_uuid_when_soft_deleted_canonical_slug_exists(integration_db) -> None:
    """Soft-deleted canonical rows must not block Git identity reuse.

    Prod had rows like ``api_id=template-openapi`` already soft-deleted and
    active UUID rows with the same ``(tenant, api_name, version)``. The source
    of truth is the current Git path, so the active row must be able to take
    the canonical slug.
    """
    tenant_id = "free-aech"
    api_id = "template-openapi"
    legacy_api_id = "68a8ce45-3c0e-430e-beb5-9bb99dd32fa7"
    integration_db.add(
        APICatalog(
            tenant_id=tenant_id,
            api_id=api_id,
            api_name=api_id,
            version="1.0.0",
            status="draft",
            tags=[],
            portal_published=False,
            audience="public",
            api_metadata={"display_name": "Deleted canonical"},
            git_path=f"tenants/{tenant_id}/apis/{api_id}",
            deleted_at=datetime.now(UTC),
        )
    )
    active_legacy = APICatalog(
        tenant_id=tenant_id,
        api_id=legacy_api_id,
        api_name=api_id,
        version="1.0.0",
        status="draft",
        tags=[],
        portal_published=False,
        audience="public",
        api_metadata={"display_name": "Active legacy"},
        git_path=f"tenants/{tenant_id}/apis/{legacy_api_id}",
        openapi_spec={"openapi": "3.0.0", "info": {"title": "Template OpenAPI"}},
    )
    integration_db.add(active_legacy)
    await integration_db.flush()
    active_legacy_pk = active_legacy.id

    await project_to_api_catalog(
        integration_db,
        _projection(
            tenant_id=tenant_id,
            api_id=api_id,
            git_path=f"tenants/{tenant_id}/apis/{api_id}/api.yaml",
            git_commit_sha="c" * 40,
            catalog_content_hash="d" * 64,
        ),
    )

    result = await integration_db.execute(
        select(APICatalog)
        .where(APICatalog.tenant_id == tenant_id, APICatalog.api_id == api_id)
        .where(APICatalog.deleted_at.is_(None))
    )
    row = result.scalar_one()
    assert row.id == active_legacy_pk
    assert row.git_path == f"tenants/{tenant_id}/apis/{api_id}/api.yaml"
    assert row.git_commit_sha == "c" * 40
    assert row.catalog_content_hash == "d" * 64
    assert row.openapi_spec == {"openapi": "3.0.0", "info": {"title": "Template OpenAPI"}}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotent_re_entry_yields_same_state(integration_db) -> None:
    proj = _projection()

    await project_to_api_catalog(integration_db, proj)
    await project_to_api_catalog(integration_db, proj)
    await project_to_api_catalog(integration_db, proj)

    result = await integration_db.execute(
        select(APICatalog).where(APICatalog.tenant_id == proj.tenant_id, APICatalog.api_id == proj.api_id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].catalog_content_hash == proj.catalog_content_hash


@pytest.mark.integration
@pytest.mark.asyncio
async def test_transactional_rollback_on_caller_exception(integration_db) -> None:
    """If the caller raises after the projection flush, the row is rolled back.

    The fixture wraps each test in a SAVEPOINT-style ``session.begin()`` /
    rollback. We simulate a caller error by inserting the projection, then
    re-querying through a fresh nested transaction that is rolled back.
    The post-rollback SELECT must NOT see the row, proving the caller's
    transaction owns the visibility lifecycle (spec §6.5 step 14 invariant).
    """
    proj = _projection(api_id="rollback-target")

    async with integration_db.begin_nested() as savepoint:
        await project_to_api_catalog(integration_db, proj)
        # Sanity: the row is visible inside the savepoint.
        result = await integration_db.execute(
            select(APICatalog).where(
                APICatalog.tenant_id == proj.tenant_id,
                APICatalog.api_id == proj.api_id,
            )
        )
        assert result.scalar_one() is not None
        await savepoint.rollback()

    result_after = await integration_db.execute(
        select(APICatalog).where(
            APICatalog.tenant_id == proj.tenant_id,
            APICatalog.api_id == proj.api_id,
        )
    )
    assert result_after.scalar_one_or_none() is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_soft_deleted_row_does_not_block_insert(integration_db) -> None:
    """A soft-deleted row with same (tenant, api_id) must not match the SELECT.

    The ``deleted_at IS NOT NULL`` row should be ignored by the SELECT clause
    (deleted_at IS NULL), so a fresh INSERT may proceed. Note: the partial
    unique index on (tenant_id, api_id) WHERE deleted_at IS NULL allows this.
    """
    from datetime import UTC, datetime

    deleted = APICatalog(
        tenant_id="demo-gitops",
        api_id="petstore",
        api_name="petstore",
        version="0.9.0",
        status="active",
        tags=[],
        portal_published=False,
        audience="public",
        api_metadata={},
        deleted_at=datetime.now(UTC),
    )
    integration_db.add(deleted)
    await integration_db.flush()

    proj = _projection()
    await project_to_api_catalog(integration_db, proj)

    result = await integration_db.execute(
        select(APICatalog).where(
            APICatalog.tenant_id == proj.tenant_id,
            APICatalog.api_id == proj.api_id,
            APICatalog.deleted_at.is_(None),
        )
    )
    row = result.scalar_one()
    assert row.version == proj.version
    assert row.git_commit_sha == proj.git_commit_sha
