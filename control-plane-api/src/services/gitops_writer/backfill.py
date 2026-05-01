"""Controlled DB-only API backfill into ``stoa-catalog``.

This module is intentionally separate from ``GitOpsWriter.create_api``. The
HTTP create path still refuses pre-GitOps rows so user traffic cannot silently
adopt legacy drift. Ops can run this backfill as an explicit maintenance action:
write a canonical ``api.yaml`` from the current DB row, read it back from Git,
then project the Git content into ``api_catalog``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import yaml
from sqlalchemy import or_, select

from src.logging_config import get_logger
from src.models.catalog import APICatalog
from src.services.catalog.write_api_yaml import render_api_yaml
from src.services.catalog_reconciler.projection import (
    project_to_api_catalog,
    render_api_catalog_projection,
)

from .hashing import compute_catalog_content_hash
from .paths import canonical_catalog_path, is_uuid_shaped

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..catalog_git_client.protocol import CatalogGitClient

logger = get_logger(__name__)


@dataclass(frozen=True)
class BackfillApiResult:
    tenant_id: str
    api_id: str
    status: str
    git_path: str | None = None
    git_commit_sha: str | None = None
    detail: str = ""


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _backend_url_from_openapi(openapi_spec: Any) -> str | None:
    if not isinstance(openapi_spec, dict):
        return None
    servers = openapi_spec.get("servers")
    if not isinstance(servers, list):
        return None
    for server in servers:
        if not isinstance(server, dict):
            continue
        url = _first_string(server.get("url"))
        if url:
            return url
    return None


def _deployments_from_metadata(metadata: dict[str, Any]) -> dict[str, bool] | None:
    deployments = metadata.get("deployments")
    if not isinstance(deployments, dict):
        return None
    clean: dict[str, bool] = {}
    for key, value in deployments.items():
        if isinstance(key, str) and isinstance(value, bool):
            clean[key] = value
    return clean or None


def _render_row_api_yaml(row: APICatalog) -> bytes:
    tenant_id = cast(str, row.tenant_id)
    api_id = cast(str, row.api_id)
    api_name = cast(str, row.api_name)
    metadata = cast(dict[str, Any], row.api_metadata or {})
    tags = cast(list[Any], row.tags or [])
    openapi_spec = cast(Any, row.openapi_spec)
    row_category = cast(str | None, row.category)
    row_status = cast(str | None, row.status)
    row_version = cast(str | None, row.version)
    backend_url = _first_string(
        metadata.get("backend_url"),
        metadata.get("backendUrl"),
        _backend_url_from_openapi(openapi_spec),
    )
    if backend_url is None:
        raise ValueError("missing backend_url")

    yaml_str = render_api_yaml(
        tenant_id=tenant_id,
        api_name=api_id,
        version=row_version or str(metadata.get("version") or "1.0.0"),
        backend_url=backend_url,
        display_name=_first_string(metadata.get("display_name"), metadata.get("name"), api_name, api_id),
        description=_first_string(metadata.get("description")),
        category=row_category,
        tags=[str(tag) for tag in tags],
        status=row_status or str(metadata.get("status") or "active"),
        deployments=_deployments_from_metadata(metadata),
    )
    return yaml_str.encode("utf-8")


class GitOpsCatalogBackfill:
    """Backfill active ``api_catalog`` rows into canonical GitOps files."""

    def __init__(
        self,
        *,
        catalog_git_client: CatalogGitClient,
        db_session: AsyncSession,
        actor: str = "catalog-backfill",
        overwrite_conflicts: bool = False,
    ) -> None:
        self._catalog_git_client = catalog_git_client
        self._db_session = db_session
        self._actor = actor
        self._overwrite_conflicts = overwrite_conflicts

    async def backfill(
        self,
        *,
        tenant_id: str | None = None,
        api_id: str | None = None,
        include_git_tracked: bool = False,
        limit: int | None = None,
        dry_run: bool = False,
    ) -> list[BackfillApiResult]:
        stmt = select(APICatalog).where(APICatalog.deleted_at.is_(None)).order_by(APICatalog.tenant_id, APICatalog.api_id)
        if tenant_id:
            stmt = stmt.where(APICatalog.tenant_id == tenant_id)
        if api_id:
            stmt = stmt.where(APICatalog.api_id == api_id)
        if not include_git_tracked:
            stmt = stmt.where(
                or_(
                    APICatalog.git_path.is_(None),
                    APICatalog.git_commit_sha.is_(None),
                    APICatalog.catalog_content_hash.is_(None),
                )
            )
        if limit is not None:
            stmt = stmt.limit(limit)

        rows = (await self._db_session.execute(stmt)).scalars().all()
        results: list[BackfillApiResult] = []
        for row in rows:
            result = await self.backfill_row(row, dry_run=dry_run)
            results.append(result)
        return results

    async def backfill_row(self, row: APICatalog, *, dry_run: bool = False) -> BackfillApiResult:
        tenant_id = cast(str, row.tenant_id)
        api_id = cast(str, row.api_id)
        row_git_path = cast(str | None, row.git_path)
        if is_uuid_shaped(api_id) or (row_git_path and _git_path_api_segment_is_uuid(row_git_path)):
            return BackfillApiResult(
                tenant_id=tenant_id,
                api_id=api_id,
                status="skipped_uuid_hard_drift",
                git_path=row_git_path,
                detail="api_id or git_path contains a UUID-shaped API segment",
            )

        try:
            git_path = canonical_catalog_path(tenant_id, api_id)
            api_yaml_bytes = _render_row_api_yaml(row)
        except ValueError as exc:
            return BackfillApiResult(
                tenant_id=tenant_id,
                api_id=api_id,
                status="skipped_invalid_row",
                git_path=row_git_path,
                detail=str(exc),
            )

        attempted_hash = compute_catalog_content_hash(api_yaml_bytes)
        remote = await self._catalog_git_client.get(git_path)
        if dry_run:
            if remote is None:
                return BackfillApiResult(tenant_id, api_id, "dry_run_would_create", git_path=git_path)
            remote_hash = compute_catalog_content_hash(remote.content)
            status = "dry_run_would_project" if remote_hash == attempted_hash else "dry_run_remote_conflict"
            return BackfillApiResult(tenant_id, api_id, status, git_path=git_path)

        if remote is None:
            commit = await self._catalog_git_client.create_or_update(
                path=git_path,
                content=api_yaml_bytes,
                expected_sha=None,
                actor=self._actor,
                message=f"backfill api {tenant_id}/{api_id}",
            )
            file_commit_sha = commit.commit_sha
            status = "created"
        else:
            remote_hash = compute_catalog_content_hash(remote.content)
            if remote_hash != attempted_hash and not self._overwrite_conflicts:
                return BackfillApiResult(
                    tenant_id=tenant_id,
                    api_id=api_id,
                    status="remote_conflict",
                    git_path=git_path,
                    detail="remote api.yaml differs from DB projection",
                )
            if remote_hash != attempted_hash:
                commit = await self._catalog_git_client.create_or_update(
                    path=git_path,
                    content=api_yaml_bytes,
                    expected_sha=remote.sha,
                    actor=self._actor,
                    message=f"backfill update api {tenant_id}/{api_id}",
                )
                file_commit_sha = commit.commit_sha
                status = "updated"
            else:
                file_commit_sha = await self._catalog_git_client.latest_file_commit(git_path)
                status = "projected"

        committed_bytes = await self._catalog_git_client.read_at_commit(git_path, file_commit_sha)
        if committed_bytes is None:
            return BackfillApiResult(
                tenant_id=tenant_id,
                api_id=api_id,
                status="read_after_commit_failed",
                git_path=git_path,
                git_commit_sha=file_commit_sha,
                detail="api.yaml not readable at returned commit",
            )

        parsed = yaml.safe_load(committed_bytes)
        if not isinstance(parsed, dict):
            return BackfillApiResult(
                tenant_id=tenant_id,
                api_id=api_id,
                status="invalid_committed_yaml",
                git_path=git_path,
                git_commit_sha=file_commit_sha,
            )

        projection = render_api_catalog_projection(
            parsed_content=parsed,
            git_commit_sha=file_commit_sha,
            catalog_content_hash=compute_catalog_content_hash(committed_bytes),
            git_path=git_path,
        )
        await project_to_api_catalog(self._db_session, projection)
        logger.info(
            "gitops_catalog_backfill.projected",
            tenant_id=tenant_id,
            api_id=api_id,
            status=status,
            git_path=git_path,
            git_commit_sha=file_commit_sha,
        )
        return BackfillApiResult(
            tenant_id=tenant_id,
            api_id=api_id,
            status=status,
            git_path=git_path,
            git_commit_sha=file_commit_sha,
        )


def _git_path_api_segment_is_uuid(git_path: str) -> bool:
    parts = git_path.rstrip("/").split("/")
    return len(parts) >= 2 and is_uuid_shaped(parts[-2])


__all__ = ["BackfillApiResult", "GitOpsCatalogBackfill"]
