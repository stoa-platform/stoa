"""``GitOpsWriter`` — Phase 4-2 orchestration (CAB-2185 B-FLOW).

Implements the 18-step Git-first flow from spec §6.5. The writer owns the
``POST /v1/tenants/{tenant_id}/apis`` path when ``GITOPS_CREATE_API_ENABLED``
is ``True`` AND the tenant is in ``GITOPS_ELIGIBLE_TENANTS``.

Three idempotent cases per spec §6.2:

* ``A`` — file absent → commit + project
* ``B`` — file present with same hash → no-op Git, project (idempotent retry)
* ``C`` — file present with different hash → :class:`GitOpsConflictError`

The 4th-class side-effect — Kafka emission — is **not** performed (spec §6.13).
``target_gateways``, ``openapi_spec`` and ``metadata`` columns are preserved on
UPDATE (spec §6.9). The writer never derives ``git_path`` from any UUID source
(garde-fou §9.10, CAB-2187 B10).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import yaml
from sqlalchemy import select, text

from src.services.catalog.write_api_yaml import render_api_yaml
from src.services.catalog_reconciler.classifier import LegacyCategory, classify_legacy
from src.services.catalog_reconciler.projection import (
    project_to_api_catalog,
    render_api_catalog_projection,
)

from .advisory_lock import advisory_lock_key
from .exceptions import (
    GitOpsConflictError,
    GitOpsRaceExhaustedError,
    InfrastructureBugError,
    InvalidApiNameError,
    LegacyCollisionError,
)
from .hashing import compute_catalog_content_hash
from .models import ApiCreatePayload, CreateApiResult
from .paths import canonical_catalog_path, is_uuid_shaped

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from ..catalog_git_client.protocol import CatalogGitClient

logger = logging.getLogger(__name__)

_MAX_RACE_RETRIES = 3


class GitOpsWriter:
    """Git-first writer for ``POST /v1/tenants/{tid}/apis``.

    Constructor requires a connected :class:`CatalogGitClient` and an
    :class:`AsyncSession`. The session is reused across the call (advisory
    lock + projection share the same connection).
    """

    def __init__(
        self,
        *,
        catalog_git_client: CatalogGitClient,
        db_session: AsyncSession,
    ) -> None:
        self._catalog_git_client = catalog_git_client
        self._db_session = db_session

    async def create_api(
        self,
        *,
        tenant_id: str,
        contract_payload: ApiCreatePayload,
        actor: str,
    ) -> CreateApiResult:
        """Create an API by committing ``api.yaml`` to ``stoa-catalog`` first.

        18-step flow per spec §6.5. Returns the slug ``api_id`` as identity
        (level 2 — never the PK UUID, never a UUID-shaped value).
        """
        api_name = contract_payload.api_name
        if not api_name or is_uuid_shaped(api_name):
            raise InvalidApiNameError(
                api_name=api_name,
                reason="UUID-shaped or empty api_name (spec §6.5 step 2)",
            )

        api_yaml_str = render_api_yaml(
            tenant_id=tenant_id,
            api_name=api_name,
            version=contract_payload.version,
            backend_url=contract_payload.backend_url,
            display_name=contract_payload.display_name,
            description=contract_payload.description or None,
            category=contract_payload.category,
            tags=list(contract_payload.tags) or None,
        )
        api_yaml_bytes = api_yaml_str.encode("utf-8")
        attempted_hash = compute_catalog_content_hash(api_yaml_bytes)

        git_path = canonical_catalog_path(tenant_id, api_name)

        await self._check_legacy_collision(tenant_id=tenant_id, api_name=api_name)

        lock_key = advisory_lock_key(tenant_id, api_name)
        await self._acquire_advisory_lock(lock_key)
        try:
            file_commit_sha, case = await self._commit_or_noop(
                git_path=git_path,
                api_yaml_bytes=api_yaml_bytes,
                attempted_hash=attempted_hash,
                actor=actor,
                tenant_id=tenant_id,
                api_name=api_name,
            )

            committed_bytes = await self._catalog_git_client.read_at_commit(git_path, file_commit_sha)
            if committed_bytes is None:
                raise InfrastructureBugError(git_path=git_path, commit_sha=file_commit_sha)

            committed_hash = compute_catalog_content_hash(committed_bytes)
            parsed = yaml.safe_load(committed_bytes)
            if not isinstance(parsed, dict):
                raise InfrastructureBugError(git_path=git_path, commit_sha=file_commit_sha)

            projection = render_api_catalog_projection(
                parsed_content=parsed,
                git_commit_sha=file_commit_sha,
                catalog_content_hash=committed_hash,
                git_path=git_path,
            )
            await project_to_api_catalog(self._db_session, projection)

            self._log_sync_status(
                tenant_id=tenant_id,
                api_id=api_name,
                status="synced",
                git_commit_sha=file_commit_sha,
                catalog_content_hash=committed_hash,
                git_path=git_path,
            )
        finally:
            await self._release_advisory_lock(lock_key)

        return CreateApiResult(
            api_id=api_name,
            api_name=api_name,
            git_path=git_path,
            git_commit_sha=file_commit_sha,
            catalog_content_hash=committed_hash,
            case=case,
        )

    async def _check_legacy_collision(self, *, tenant_id: str, api_name: str) -> None:
        """Spec §6.5 step 7 — refuse Cat B / C / D, allow ABSENT / A / GITOPS_CREATED."""
        from src.models.catalog import APICatalog

        stmt = (
            select(
                APICatalog.api_id,
                APICatalog.git_path,
                APICatalog.git_commit_sha,
                APICatalog.catalog_content_hash,
            )
            .where(APICatalog.tenant_id == tenant_id)
            .where(APICatalog.api_id == api_name)
            .where(APICatalog.deleted_at.is_(None))
        )
        result = await self._db_session.execute(stmt)
        row = result.first()
        if row is None:
            return  # Cat ABSENT — continue

        actual_row: dict[str, Any] = {
            "api_id": row.api_id,
            "git_path": row.git_path,
            "git_commit_sha": row.git_commit_sha,
            "catalog_content_hash": row.catalog_content_hash,
        }

        git_file_exists = False
        if row.git_path is not None:
            try:
                remote = await self._catalog_git_client.get(row.git_path)
                git_file_exists = remote is not None
            except Exception:
                logger.exception(
                    "gitops_writer.collision_check_git_read_failed",
                    extra={"tenant_id": tenant_id, "api_id": api_name, "git_path": row.git_path},
                )
                git_file_exists = False

        category = await classify_legacy(actual_row=actual_row, git_file_exists=git_file_exists)

        if category in (
            LegacyCategory.UUID_HARD_DRIFT,
            LegacyCategory.ORPHAN_DB,
            LegacyCategory.PRE_GITOPS,
        ):
            raise LegacyCollisionError(
                tenant_id=tenant_id,
                api_id=api_name,
                category=category.value,
                detail=f"row api_id={row.api_id!r} git_path={row.git_path!r}",
            )
        # Cat HEALTHY_ADOPTABLE or GITOPS_CREATED → continue (re-adoption / idempotent).

    async def _commit_or_noop(
        self,
        *,
        git_path: str,
        api_yaml_bytes: bytes,
        attempted_hash: str,
        actor: str,
        tenant_id: str,
        api_name: str,
    ) -> tuple[str, str]:
        """Spec §6.5 steps 9-11. Returns ``(file_commit_sha, case)``.

        ``case`` is ``"created"`` (Case A) or ``"idempotent"`` (Case B); Case C
        raises :class:`GitOpsConflictError` directly. Optimistic-CAS races on
        Case A retry up to 3x before raising :class:`GitOpsRaceExhaustedError`.
        """
        from ..catalog_git_client.github_contents import CatalogShaConflictError

        last_exc: Exception | None = None
        for attempt in range(_MAX_RACE_RETRIES):
            existing = await self._catalog_git_client.get(git_path)
            if existing is None:
                try:
                    commit = await self._catalog_git_client.create_or_update(
                        path=git_path,
                        content=api_yaml_bytes,
                        expected_sha=None,
                        actor=actor,
                        message=f"create api {tenant_id}/{api_name}",
                    )
                    return commit.commit_sha, "created"
                except CatalogShaConflictError as exc:
                    last_exc = exc
                    logger.info(
                        "gitops_writer.optimistic_cas_race_retry",
                        extra={
                            "tenant_id": tenant_id,
                            "api_id": api_name,
                            "attempt": attempt + 1,
                            "max_attempts": _MAX_RACE_RETRIES,
                        },
                    )
                    continue

            existing_hash = compute_catalog_content_hash(existing.content)
            if existing_hash == attempted_hash:
                file_commit_sha = await self._catalog_git_client.latest_file_commit(git_path)
                return file_commit_sha, "idempotent"

            raise GitOpsConflictError(
                tenant_id=tenant_id,
                api_id=api_name,
                remote_hash=existing_hash,
                attempted_hash=attempted_hash,
            )

        raise GitOpsRaceExhaustedError(
            tenant_id=tenant_id,
            api_id=api_name,
            attempts=_MAX_RACE_RETRIES,
        ) from last_exc

    async def _acquire_advisory_lock(self, key: int) -> None:
        """Spec §6.8 — blocking session-scoped advisory lock."""
        await self._db_session.execute(text("SELECT pg_advisory_lock(:k)").bindparams(k=key))

    async def _release_advisory_lock(self, key: int) -> None:
        """Spec §6.8 — release the matching ``pg_advisory_unlock``.

        Swallowed exceptions: if release fails (e.g. session already dropped),
        we log but do not let the failure mask the original outcome of the
        flow.
        """
        try:
            await self._db_session.execute(text("SELECT pg_advisory_unlock(:k)").bindparams(k=key))
        except Exception:
            logger.exception("gitops_writer.advisory_unlock_failed", extra={"lock_key": key})

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
        """Spec §6.5 step 15 / §6.6 ``update_status``.

        Persistent ``api_sync_status`` table is intentionally deferred to a
        follow-up migration; Phase 4-2 surfaces sync state via structured
        logs so dashboards and tests can observe transitions without a
        schema change in this PR.
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
