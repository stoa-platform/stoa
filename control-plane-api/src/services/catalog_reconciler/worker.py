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
import logging
from typing import TYPE_CHECKING, Any

import yaml
from sqlalchemy import select, text

from src.services.gitops_writer.advisory_lock import advisory_lock_key
from src.services.gitops_writer.hashing import compute_catalog_content_hash
from src.services.gitops_writer.paths import is_uuid_shaped, parse_canonical_path

from .classifier import LegacyCategory, classify_legacy
from .projection import (
    project_to_api_catalog,
    render_api_catalog_projection,
    row_matches_projection,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractAsyncContextManager

    from sqlalchemy.ext.asyncio import AsyncSession

    from ..catalog_git_client.protocol import CatalogGitClient

logger = logging.getLogger(__name__)


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

    async def start(self) -> None:
        """Run the reconciler loop until :meth:`stop` is called."""
        logger.info(
            "catalog_reconciler.start",
            extra={"interval_seconds": self._interval_seconds},
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
        paths = await self._catalog_git_client.list("tenants/*/apis/*/api.yaml")
        seen_keys: set[tuple[str, str]] = set()

        for git_path in paths:
            try:
                key = await self._reconcile_one_path(git_path)
                if key is not None:
                    seen_keys.add(key)
            except Exception:
                logger.exception(
                    "catalog_reconciler.path_failed",
                    extra={"git_path": git_path},
                )

        try:
            await self._detect_legacy_orphans(seen_keys)
        except Exception:
            logger.exception("catalog_reconciler.orphan_detection_failed")

    async def _reconcile_one_path(self, git_path: str) -> tuple[str, str] | None:
        """Reconcile one Git path. Returns ``(tenant_id, api_id)`` if processed."""
        try:
            tenant_id, api_name = parse_canonical_path(git_path)
        except ValueError as exc:
            logger.warning(
                "catalog_reconciler.non_canonical_path",
                extra={"git_path": git_path, "error": str(exc)},
            )
            return None

        if is_uuid_shaped(api_name):
            self._log_sync_status(
                tenant_id=tenant_id,
                api_id=api_name,
                status="failed",
                git_commit_sha=None,
                catalog_content_hash=None,
                git_path=git_path,
                last_error="uuid-shaped api_name in git_path",
            )
            return None

        remote = await self._catalog_git_client.get(git_path)
        if remote is None:
            return None

        content_bytes = remote.content
        content_hash = compute_catalog_content_hash(content_bytes)
        try:
            commit_sha = await self._catalog_git_client.latest_file_commit(git_path)
        except FileNotFoundError:
            return None
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
            return (tenant_id, api_name)
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
            return (tenant_id, api_name)

        try:
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

        async with self._db_session_factory() as session:
            from src.models.catalog import APICatalog

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
                return (tenant_id, api_name)

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
                return (tenant_id, api_name)

            if category == LegacyCategory.ABSENT:
                if await self._try_advisory_lock(session, tenant_id, api_name):
                    await project_to_api_catalog(session, expected)
                    await session.commit()
                    self._log_sync_status(
                        tenant_id=tenant_id,
                        api_id=api_name,
                        status="synced",
                        git_commit_sha=commit_sha,
                        catalog_content_hash=content_hash,
                        git_path=git_path,
                    )
                return (tenant_id, api_name)

            # Cat HEALTHY_ADOPTABLE or GITOPS_CREATED — drift check then project.
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

        return (tenant_id, api_name)

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
            "git_path": row.git_path,
            "git_commit_sha": row.git_commit_sha,
            "catalog_content_hash": row.catalog_content_hash,
        }

    @staticmethod
    async def _try_advisory_lock(session: AsyncSession, tenant_id: str, api_id: str) -> bool:
        """Non-blocking transaction-scoped advisory lock (spec §6.8 reconciler side)."""
        key = advisory_lock_key(tenant_id, api_id)
        result = await session.execute(text("SELECT pg_try_advisory_xact_lock(:k)").bindparams(k=key))
        acquired = bool(result.scalar())
        if not acquired:
            logger.info(
                "catalog_reconciler.lock_skipped",
                extra={"tenant_id": tenant_id, "api_id": api_id, "lock_key": key},
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
        ``api_sync_status`` is deferred; logs are the surface in Phase 4-2.
        """
        logger.info(
            "catalog_sync_status",
            extra={
                "tenant_id": tenant_id,
                "api_id": api_id,
                "target": "api_catalog",
                "status": status,
                "git_commit_sha": git_commit_sha,
                "catalog_content_hash": catalog_content_hash,
                "git_path": git_path,
                "last_error": last_error,
            },
        )
