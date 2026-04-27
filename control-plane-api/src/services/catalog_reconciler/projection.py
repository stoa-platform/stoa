"""``api.yaml`` → ``api_catalog`` projection (Phase 4-1 implementation).

Spec §6.5 step 14, §6.6, §6.9 mapping table, §6.10 (CAB-2186 B-WORKER, CAB-2180
B-CATALOG).

This module is intentionally pure on the rendering side and limited to a
single async function on the DB side. The reconciler tick (Phase 4-2) feeds
``parsed_content`` already pulled from ``stoa-catalog`` Git through
``CatalogGitClient.read_at_commit``; the writer flow follows the same path
(spec §6.5 step 14).

Contract:

* The projection NEVER reads or writes ``target_gateways``, ``openapi_spec``
  or ``metadata`` (preserved fields, owned by deployment / UAC V2).
* The projection NEVER touches ``id`` (PK UUID) on UPDATE.
* The projection rejects ``id != name`` content (§6.10) and UUID-shaped names.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.catalog import APICatalog
from src.services.gitops_writer.paths import is_uuid_shaped, parse_canonical_path

_PORTAL_PUBLISHED_TAG = "portal:published"
_DEFAULT_AUDIENCE = "public"
_DEFAULT_STATUS = "active"


@dataclass(frozen=True)
class ApiCatalogProjection:
    """Immutable projection of one ``api.yaml`` for ``api_catalog`` upsert.

    Spec §6.9 mapping table. Fields ``target_gateways``, ``openapi_spec`` and
    ``metadata`` are intentionally absent — they are owned by other flows and
    preserved on UPDATE.
    """

    tenant_id: str
    api_id: str
    api_name: str
    version: str
    status: str
    category: str | None
    tags: list[str]
    portal_published: bool
    audience: str
    git_path: str
    git_commit_sha: str
    catalog_content_hash: str


def _coerce_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t) for t in raw]
    raise ValueError(f"tags must be a list, got {type(raw).__name__}")


def render_api_catalog_projection(
    *,
    parsed_content: dict[str, Any],
    git_commit_sha: str,
    catalog_content_hash: str,
    git_path: str,
) -> ApiCatalogProjection:
    """Render the ``ApiCatalogProjection`` for a parsed ``api.yaml`` dict.

    Validation (spec §6.10):

    * ``git_path`` is canonical (parsed via :func:`parse_canonical_path`)
    * ``parsed_content['name']`` matches the slug from ``git_path``
    * ``parsed_content['id'] == parsed_content['name']``
    * ``api_name`` is not UUID-shaped (already enforced by ``parse_canonical_path``)

    Raises:
        ValueError: on §6.10 violation, missing required fields or bad types.
    """
    tenant_id, api_name_from_path = parse_canonical_path(git_path)

    if "name" not in parsed_content:
        raise ValueError("api.yaml missing required field 'name'")
    name = parsed_content["name"]
    if not isinstance(name, str) or not name:
        raise ValueError(f"api.yaml 'name' must be a non-empty string, got {name!r}")

    if name != api_name_from_path:
        raise ValueError(
            f"name mismatch: api.yaml 'name'={name!r} != git_path slug {api_name_from_path!r}. Spec §6.10."
        )

    yaml_id = parsed_content.get("id", name)
    if yaml_id != name:
        raise ValueError(f"id != name: api.yaml 'id'={yaml_id!r}, 'name'={name!r}. Spec §6.10.")

    if is_uuid_shaped(name):
        raise ValueError(f"api_name UUID-shaped not allowed: {name!r}. Spec §6.4 (CAB-2187 B10).")

    version = parsed_content.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("api.yaml 'version' must be a non-empty string")

    status_value = parsed_content.get("status", _DEFAULT_STATUS)
    if not isinstance(status_value, str) or not status_value:
        raise ValueError("api.yaml 'status' must be a non-empty string when present")

    category = parsed_content.get("category")
    if category is not None and not isinstance(category, str):
        raise ValueError("api.yaml 'category' must be a string when present")

    tags = _coerce_tags(parsed_content.get("tags"))
    portal_published = _PORTAL_PUBLISHED_TAG in tags

    audience = parsed_content.get("audience", _DEFAULT_AUDIENCE)
    if not isinstance(audience, str) or not audience:
        audience = _DEFAULT_AUDIENCE

    return ApiCatalogProjection(
        tenant_id=tenant_id,
        api_id=name,
        api_name=name,
        version=version,
        status=status_value,
        category=category,
        tags=tags,
        portal_published=portal_published,
        audience=audience,
        git_path=git_path,
        git_commit_sha=git_commit_sha,
        catalog_content_hash=catalog_content_hash,
    )


def row_matches_projection(
    actual_row: dict[str, Any],
    expected: ApiCatalogProjection,
) -> bool:
    """Return True iff every projected field of ``actual_row`` equals ``expected``.

    Compares only the projected fields (spec §6.6 + §6.9):
    ``api_id``, ``tenant_id``, ``api_name``, ``version``, ``status``,
    ``category``, ``tags``, ``portal_published``, ``audience``, ``git_path``,
    ``git_commit_sha``, ``catalog_content_hash``.

    Fields ``target_gateways``, ``openapi_spec``, ``metadata``, ``id``,
    ``synced_at`` and ``deleted_at`` are ignored — they are not under GitOps
    write authority.
    """
    expected_tags = list(expected.tags)
    actual_tags = list(actual_row.get("tags") or [])

    return (
        actual_row.get("tenant_id") == expected.tenant_id
        and actual_row.get("api_id") == expected.api_id
        and actual_row.get("api_name") == expected.api_name
        and actual_row.get("version") == expected.version
        and actual_row.get("status") == expected.status
        and actual_row.get("category") == expected.category
        and actual_tags == expected_tags
        and bool(actual_row.get("portal_published")) == expected.portal_published
        and actual_row.get("audience") == expected.audience
        and actual_row.get("git_path") == expected.git_path
        and actual_row.get("git_commit_sha") == expected.git_commit_sha
        and actual_row.get("catalog_content_hash") == expected.catalog_content_hash
    )


async def project_to_api_catalog(
    db_session: AsyncSession,
    projection: ApiCatalogProjection,
) -> None:
    """Upsert ``projection`` into ``api_catalog`` transactionally.

    INSERT path: a new row is created with ``id = gen_random_uuid()`` (default),
    ``metadata = {}``, ``openapi_spec = NULL``, ``target_gateways = []``
    (defaults from the schema).

    UPDATE path: only the projected columns are written. ``target_gateways``,
    ``openapi_spec``, ``metadata`` and the PK ``id`` are preserved by virtue
    of NOT being listed in the ``.values()`` clause.

    Spec §6.5 step 14, §6.9. NOT wired to the HTTP handler in Phase 4-1.

    The caller is responsible for the surrounding transaction; this function
    is idempotent within a transaction (re-entry produces the same result).
    """
    select_stmt = (
        select(APICatalog)
        .where(APICatalog.tenant_id == projection.tenant_id)
        .where(APICatalog.api_id == projection.api_id)
        .where(APICatalog.deleted_at.is_(None))
    )
    result = await db_session.execute(select_stmt)
    existing = result.scalar_one_or_none()

    if existing is None:
        new_row = APICatalog(
            tenant_id=projection.tenant_id,
            api_id=projection.api_id,
            api_name=projection.api_name,
            version=projection.version,
            status=projection.status,
            category=projection.category,
            tags=list(projection.tags),
            portal_published=projection.portal_published,
            audience=projection.audience,
            api_metadata={},
            git_path=projection.git_path,
            git_commit_sha=projection.git_commit_sha,
            catalog_content_hash=projection.catalog_content_hash,
        )
        db_session.add(new_row)
        await db_session.flush()
        return

    update_stmt = (
        update(APICatalog)
        .where(APICatalog.id == existing.id)
        .values(
            api_name=projection.api_name,
            version=projection.version,
            status=projection.status,
            category=projection.category,
            tags=list(projection.tags),
            portal_published=projection.portal_published,
            audience=projection.audience,
            git_path=projection.git_path,
            git_commit_sha=projection.git_commit_sha,
            catalog_content_hash=projection.catalog_content_hash,
        )
    )
    await db_session.execute(update_stmt)
    await db_session.flush()


__all__ = [
    "ApiCatalogProjection",
    "project_to_api_catalog",
    "render_api_catalog_projection",
    "row_matches_projection",
]
