"""``CatalogReconcilerWorker`` — Phase 4-2 loop (CAB-2186 B-WORKER).

Spec §6.6: in-tree async loop reconciling ``api_catalog`` against the
``stoa-catalog`` Git remote. Started from ``main.py`` only when
``GITOPS_CREATE_API_ENABLED`` is True.

The reconciler is **non-destructive**:

* Cat A drift on projection → repaired (advisory lock + projection)
* Cat B / C / D drift → detected and logged, never auto-repaired (spec §6.14)
* DB orphans → logged as ``drift_orphan``; no DELETE, no soft-delete
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any, cast

import yaml
from sqlalchemy import select, text

from src.logging_config import get_logger
from src.services.catalog_api_definition import normalize_api_definition
from src.services.catalog_deployment_reconciler import CatalogDeploymentReconciler
from src.services.gitops_writer.advisory_lock import advisory_lock_key
from src.services.gitops_writer.hashing import compute_catalog_content_hash
from src.services.gitops_writer.paths import is_uuid_shaped, parse_canonical_path

from .classifier import LegacyCategory, classify_legacy
from .metrics import CATALOG_SYNC_STATUS_TOTAL
from .projection import (
    project_to_api_catalog,
    render_api_catalog_projection,
    row_matches_projection,
)

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from ..catalog_git_client.models import RemoteFileMetadata
    from ..catalog_git_client.protocol import CatalogGitClient

logger = get_logger(__name__)


class CatalogReconcilerWorker:
    """Async loop reconciling ``api_catalog`` against ``stoa-catalog`` Git.

    Args:
        catalog_git_client: Connected :class:`CatalogGitClient` instance.
        db_session_factory: Zero-arg callable returning an async context
            manager that yields an :class:`AsyncSession`. Each iteration
            opens a fresh session so the reconciler never accumulates DB
            state across ticks.
        interval_seconds: Tick interval (spec §6.6 default 10s).
    """

    def __init__(
        self,
        *,
        catalog_git_client: CatalogGitClient,
        db_session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        interval_seconds: int = 10,
    ) -> None:
        self._catalog_git_client = catalog_git_client
        self._db_session_factory = db_session_factory
        self._interval_seconds = interval_seconds
        self._shutdown = asyncio.Event()
        self._last_seen_blob_sha: dict[str, str] = {}

    async def start(self) -> None:
        """Run the reconciler loop until :meth:`stop` is called."""
        logger.info(
            "catalog_reconciler.start",
            interval_seconds=self._interval_seconds,
        )
        while not self._shutdown.is_set():
            try:
                await self._reconcile_iteration()
            except Exception:
                logger.exception("catalog_reconciler.iteration_failed")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._shutdown.wait(), timeout=self._interval_seconds)
        logger.info("catalog_reconciler.stopped")

    async def stop(self) -> None:
        """Signal the loop to exit at the next iteration boundary."""
        self._shutdown.set()

    async def _reconcile_iteration(self) -> None:
        """One pass: project cat A/ABSENT/GITOPS_CREATED, log drift for B/C/D."""
        files = await self._list_api_files("tenants/*/apis/*/api.yaml")
        seen_keys: set[tuple[str, str]] = set()
        current_paths = {remote.path for remote in files}
        for cached_path in list(self._last_seen_blob_sha):
            if cached_path not in current_paths:
                self._last_seen_blob_sha.pop(cached_path, None)

        for remote_file in files:
            git_path = remote_file.path
            try:
                if remote_file.sha and self._last_seen_blob_sha.get(git_path) == remote_file.sha:
                    key = self._seen_key_from_path(git_path)
                    if key is not None:
                        seen_keys.add(key)
                    continue

                key = await self._reconcile_one_path(git_path, remote_metadata=remote_file)
                if remote_file.sha:
                    self._last_seen_blob_sha[git_path] = remote_file.sha
                if key is not None:
                    seen_keys.add(key)
            except Exception:
                logger.exception(
                    "catalog_reconciler.path_failed",
                    git_path=git_path,
                )

        try:
            await self._detect_legacy_orphans(seen_keys)
        except Exception:
            logger.exception("catalog_reconciler.orphan_detection_failed")

    async def _list_api_files(self, glob_pattern: str) -> list[RemoteFileMetadata]:
        """List Git API files with blob metadata when the client supports it."""
        from ..catalog_git_client.models import RemoteFileMetadata

        list_file_metadata = getattr(self._catalog_git_client, "list_file_metadata", None)
        if callable(list_file_metadata):
            typed_list_file_metadata = cast(
                Callable[[str], Awaitable[Sequence[RemoteFileMetadata]]],
                list_file_metadata,
            )
            return list(await typed_list_file_metadata(glob_pattern))

        paths = await self._catalog_git_client.list(glob_pattern)
        return [RemoteFileMetadata(path=path, sha="", commit_sha=None) for path in paths]

    def _seen_key_from_path(self, git_path: str) -> tuple[str, str] | None:
        """Return the canonical ``(tenant, api)`` key for an already-seen path."""
        parts = git_path.rstrip("/").split("/")
        if len(parts) >= 5 and parts[0] == "tenants" and parts[2] == "apis" and is_uuid_shaped(parts[3]):
            return None
        try:
            return parse_canonical_path(git_path)
        except ValueError:
            return None

    async def _reconcile_one_path(
        self,
        git_path: str,
        *,
        remote_metadata: RemoteFileMetadata | None = None,
    ) -> tuple[str, str] | None:
        """Reconcile one Git path. Returns ``(tenant_id, api_id)`` if processed.

        Implements spec §6.6 lines 352-402 for a single canonical path. The
        method itself owns the Git fetch + content validation; the per-row
        DB decision tree is delegated to :meth:`_reconcile_db_row` to keep
        each helper readable.
        """
        # Spec §6.6: a UUID-shaped api_name in the git_path is a "corruption
        # Git" signal that must surface as ``status=failed`` (a distinct
        # operational event from a generic non-canonical layout). The check
        # therefore runs *before* ``parse_canonical_path`` — that helper
        # rejects UUID segments by raising ``ValueError``, which would
        # otherwise be funneled into the warning-only branch below.
        parts = git_path.rstrip("/").split("/")
        if len(parts) >= 5 and parts[0] == "tenants" and parts[2] == "apis" and is_uuid_shaped(parts[3]):
            self._log_sync_status(
                tenant_id=parts[1],
                api_id=parts[3],
                status="failed",
                git_commit_sha=None,
                catalog_content_hash=None,
                git_path=git_path,
                last_error="uuid-shaped api_name in git_path",
            )
            return None

        try:
            tenant_id, api_name = parse_canonical_path(git_path)
        except ValueError as exc:
            logger.warning(
                "catalog_reconciler.non_canonical_path",
                git_path=git_path,
                error=str(exc),
            )
            return None

        remote = await self._catalog_git_client.get(git_path)
        if remote is None:
            return None

        content_bytes = remote.content
        content_hash = compute_catalog_content_hash(content_bytes)
        if remote_metadata is not None and remote_metadata.commit_sha:
            commit_sha = remote_metadata.commit_sha
        else:
            try:
                commit_sha = await self._catalog_git_client.latest_file_commit(git_path)
            except FileNotFoundError:
                return None

        parsed = self._parse_and_validate_yaml(
            content_bytes=content_bytes,
            tenant_id=tenant_id,
            api_name=api_name,
            commit_sha=commit_sha,
            content_hash=content_hash,
            git_path=git_path,
        )
        if parsed is None:
            return (tenant_id, api_name)
        parsed = normalize_api_definition(parsed)

        try:
            # ``render_api_catalog_projection`` is the schema-validation step
            # that follows ``yaml.safe_load`` (spec §6.10): it asserts the
            # canonical layout, refuses ``id != name``, validates types, and
            # rejects UUID-shaped slugs. Any malformed Git content fails here
            # before reaching the DB.
            expected = render_api_catalog_projection(
                parsed_content=parsed,
                git_commit_sha=commit_sha,
                catalog_content_hash=content_hash,
                git_path=git_path,
            )
        except ValueError as exc:
            self._log_sync_status(
                tenant_id=tenant_id,
                api_id=api_name,
                status="failed",
                git_commit_sha=commit_sha,
                catalog_content_hash=content_hash,
                git_path=git_path,
                last_error=str(exc),
            )
            return (tenant_id, api_name)

        await self._reconcile_db_row(
            tenant_id=tenant_id,
            api_name=api_name,
            git_path=git_path,
            commit_sha=commit_sha,
            content_hash=content_hash,
            expected=expected,
            api_content=parsed,
        )
        return (tenant_id, api_name)

    def _parse_and_validate_yaml(
        self,
        *,
        content_bytes: bytes,
        tenant_id: str,
        api_name: str,
        commit_sha: str,
        content_hash: str,
        git_path: str,
    ) -> dict[str, Any] | None:
        """Parse ``api.yaml`` bytes and return a mapping or ``None`` on failure.

        On failure the helper logs a structured ``failed`` status so the
        caller can move on without raising. The schema-level validation
        (spec §6.10) happens later in
        :func:`render_api_catalog_projection`.
        """
        try:
            parsed = yaml.safe_load(content_bytes)
        except yaml.YAMLError as exc:
            self._log_sync_status(
                tenant_id=tenant_id,
                api_id=api_name,
                status="failed",
                git_commit_sha=commit_sha,
                catalog_content_hash=content_hash,
                git_path=git_path,
                last_error=f"yaml parse error: {exc}",
            )
            return None
        if not isinstance(parsed, dict):
            self._log_sync_status(
                tenant_id=tenant_id,
                api_id=api_name,
                status="failed",
                git_commit_sha=commit_sha,
                catalog_content_hash=content_hash,
                git_path=git_path,
                last_error="api.yaml root is not a mapping",
            )
            return None
        return parsed

    async def _reconcile_db_row(
        self,
        *,
        tenant_id: str,
        api_name: str,
        git_path: str,
        commit_sha: str,
        content_hash: str,
        expected: Any,
        api_content: dict[str, Any],
    ) -> None:
        """Apply the §6.6 per-row decision tree against the DB.

        Branches:

        * cat ``UUID_HARD_DRIFT`` (B) → log drift, no mutation.
        * cat ``PRE_GITOPS`` (D) → log drift, no mutation.
        * cat ``ABSENT`` → take advisory lock, project a new row, commit.
        * cat ``HEALTHY_ADOPTABLE`` / ``GITOPS_CREATED`` → drift check; if
          drifting, lock + project; otherwise log ``synced``.
        """
        from src.models.catalog import APICatalog

        async with self._db_session_factory() as session:
            stmt = (
                select(APICatalog)
                .where(APICatalog.tenant_id == tenant_id)
                .where(APICatalog.api_id == api_name)
                .where(APICatalog.deleted_at.is_(None))
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            actual_row = self._row_to_dict(row) if row is not None else None

            category = await classify_legacy(actual_row=actual_row, git_file_exists=True)

            if category == LegacyCategory.UUID_HARD_DRIFT:
                self._log_sync_status(
                    tenant_id=tenant_id,
                    api_id=api_name,
                    status="drift_detected",
                    git_commit_sha=commit_sha,
                    catalog_content_hash=content_hash,
                    git_path=git_path,
                    last_error=(
                        f"uuid hard drift: row api_id={actual_row.get('api_id') if actual_row else None!r} "
                        f"row git_path={actual_row.get('git_path') if actual_row else None!r} "
                        f"real_git_name={api_name!r}"
                    ),
                )
                return

            if category == LegacyCategory.PRE_GITOPS:
                self._log_sync_status(
                    tenant_id=tenant_id,
                    api_id=api_name,
                    status="drift_pre_gitops",
                    git_commit_sha=commit_sha,
                    catalog_content_hash=content_hash,
                    git_path=git_path,
                    last_error="no git_path nor commit pointer",
                )
                return

            if category == LegacyCategory.ABSENT:
                if await self._try_advisory_lock(session, tenant_id, api_name):
                    await project_to_api_catalog(session, expected)
                    row = await self._get_catalog_row(session, tenant_id, api_name)
                    await CatalogDeploymentReconciler(session).reconcile_api(
                        tenant_id=tenant_id,
                        api_id=api_name,
                        api_content=api_content,
                        catalog_entry=row,
                    )
                    await session.commit()
                    self._log_sync_status(
                        tenant_id=tenant_id,
                        api_id=api_name,
                        status="synced",
                        git_commit_sha=commit_sha,
                        catalog_content_hash=content_hash,
                        git_path=git_path,
                    )
                return

            assert actual_row is not None
            if not row_matches_projection(actual_row, expected):
                if await self._try_advisory_lock(session, tenant_id, api_name):
                    self._log_sync_status(
                        tenant_id=tenant_id,
                        api_id=api_name,
                        status="drift_detected",
                        git_commit_sha=commit_sha,
                        catalog_content_hash=content_hash,
                        git_path=git_path,
                        last_error="projection drift",
                    )
                    await project_to_api_catalog(session, expected)
                    row = await self._get_catalog_row(session, tenant_id, api_name)
                    await CatalogDeploymentReconciler(session).reconcile_api(
                        tenant_id=tenant_id,
                        api_id=api_name,
                        api_content=api_content,
                        catalog_entry=row,
                    )
                    await session.commit()
                    self._log_sync_status(
                        tenant_id=tenant_id,
                        api_id=api_name,
                        status="synced",
                        git_commit_sha=commit_sha,
                        catalog_content_hash=content_hash,
                        git_path=git_path,
                    )
            else:
                self._log_sync_status(
                    tenant_id=tenant_id,
                    api_id=api_name,
                    status="synced",
                    git_commit_sha=commit_sha,
                    catalog_content_hash=content_hash,
                    git_path=git_path,
                )
                changed = await CatalogDeploymentReconciler(session).reconcile_api(
                    tenant_id=tenant_id,
                    api_id=api_name,
                    api_content=api_content,
                    catalog_entry=row,
                )
                if changed:
                    await session.commit()

    async def _detect_legacy_orphans(self, seen_keys: set[tuple[str, str]]) -> None:
        """Iterate active DB rows not seen in the Git tree this tick.

        Logs the appropriate ``drift_*`` status per category. Never mutates
        ``api_catalog`` (spec §6.14 garde-fou §9.13 + §9.15).
        """
        from src.models.catalog import APICatalog

        async with self._db_session_factory() as session:
            stmt = select(APICatalog).where(APICatalog.deleted_at.is_(None))
            result = await session.execute(stmt)
            rows = result.scalars().all()
            for row in rows:
                key = (row.tenant_id, row.api_id)
                if key in seen_keys:
                    continue
                actual = self._row_to_dict(row)
                category = await classify_legacy(actual_row=actual, git_file_exists=False)

                if category == LegacyCategory.UUID_HARD_DRIFT:
                    status = "drift_detected"
                    last_error = "uuid hard drift"
                elif category == LegacyCategory.PRE_GITOPS:
                    status = "drift_pre_gitops"
                    last_error = "no git_path nor commit pointer"
                elif category == LegacyCategory.ORPHAN_DB:
                    status = "drift_orphan"
                    last_error = "no git file at HEAD"
                else:
                    # HEALTHY_ADOPTABLE / GITOPS_CREATED with a missing canonical
                    # path during this tick is treated as transient; skip.
                    continue

                self._log_sync_status(
                    tenant_id=str(row.tenant_id),
                    api_id=str(row.api_id),
                    status=status,
                    git_commit_sha=str(row.git_commit_sha) if row.git_commit_sha is not None else None,
                    catalog_content_hash=(
                        str(row.catalog_content_hash) if row.catalog_content_hash is not None else None
                    ),
                    git_path=str(row.git_path) if row.git_path is not None else None,
                    last_error=last_error,
                )

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "tenant_id": row.tenant_id,
            "api_id": row.api_id,
            "api_name": row.api_name,
            "version": row.version,
            "status": row.status,
            "category": row.category,
            "tags": list(row.tags or []),
            "portal_published": bool(row.portal_published),
            "audience": row.audience,
            "api_metadata": dict(row.api_metadata or {}),
            "git_path": row.git_path,
            "git_commit_sha": row.git_commit_sha,
            "catalog_content_hash": row.catalog_content_hash,
        }

    @staticmethod
    async def _get_catalog_row(session: AsyncSession, tenant_id: str, api_id: str) -> Any:
        from src.models.catalog import APICatalog

        result = await session.execute(
            select(APICatalog).where(
                APICatalog.tenant_id == tenant_id,
                APICatalog.api_id == api_id,
                APICatalog.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def _try_advisory_lock(session: AsyncSession, tenant_id: str, api_id: str) -> bool:
        """Non-blocking transaction-scoped advisory lock (spec §6.8 reconciler side)."""
        key = advisory_lock_key(tenant_id, api_id)
        result = await session.execute(text("SELECT pg_try_advisory_xact_lock(:k)").bindparams(k=key))
        acquired = bool(result.scalar())
        if not acquired:
            logger.info(
                "catalog_reconciler.lock_skipped",
                tenant_id=tenant_id,
                api_id=api_id,
                lock_key=key,
            )
        return acquired

    @staticmethod
    def _log_sync_status(
        *,
        tenant_id: str,
        api_id: str,
        status: str,
        git_commit_sha: str | None,
        catalog_content_hash: str | None,
        git_path: str | None,
        last_error: str | None = None,
    ) -> None:
        """Spec §6.6 ``update_status``.

        See the writer's ``_log_sync_status`` for the rationale: persistent
        ``api_sync_status`` is deferred; the structured log plus
        ``catalog_sync_status_total`` Prometheus counter (CAB-2208) are the
        observability surface in Phase 4-2.
        """
        CATALOG_SYNC_STATUS_TOTAL.labels(
            tenant_id=tenant_id,
            api_id=api_id,
            status=status,
        ).inc()
        logger.info(
            "catalog_sync_status",
            tenant_id=tenant_id,
            api_id=api_id,
            target="api_catalog",
            status=status,
            git_commit_sha=git_commit_sha,
            catalog_content_hash=catalog_content_hash,
            git_path=git_path,
            last_error=last_error,
        )
