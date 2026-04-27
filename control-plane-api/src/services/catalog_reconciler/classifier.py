"""Legacy collision classifier (Phase 4-1 implementation).

Spec §6.14 + §11.1 audit-informed (CAB-2188 B12, CAB-2193 B14).

Six categories — mutually exclusive, mapped from a row state plus the Git
HEAD presence of the canonical file:

* ``A`` — sain adoptable (slug = api_name, git_path canonique, file present)
* ``B`` — UUID hard drift (api_id or git_path UUID-shaped)
* ``C`` — orphelin DB (row active, file absent from Git HEAD)
* ``D`` — pré-GitOps DB-only (git_path NULL and git_commit_sha NULL — surfaced
  by audit B14 / CAB-2193)
* ``GITOPS_CREATED`` — created by the new flow (catalog_content_hash NOT NULL)
* ``ABSENT`` — no row in ``api_catalog``

The reconciler uses categories ``B``, ``C``, ``D`` as drift signals and never
mutates those rows automatically (spec §6.14 garde-fou §9.13 + §9.15).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from src.services.gitops_writer.paths import is_uuid_shaped


class LegacyCategory(StrEnum):
    """Mutually exclusive categories from spec §6.14 + §11.1.

    String values are stable identifiers used in
    ``api_sync_status.last_error`` and metrics.
    """

    HEALTHY_ADOPTABLE = "A"
    UUID_HARD_DRIFT = "B"
    ORPHAN_DB = "C"
    PRE_GITOPS = "D"
    GITOPS_CREATED = "gitops_created"
    ABSENT = "absent"


def _git_path_uuid_shaped(git_path: str | None) -> bool:
    """Return True iff the api_name segment of a canonical-ish path is UUID."""
    if not git_path:
        return False
    # Look at the segment before "/api.yaml": tenants/{tid}/apis/{name}/api.yaml
    parts = git_path.rstrip("/").split("/")
    # Defensive: tolerate non-canonical paths; we only check the second-to-last
    # segment (the api_name slot) for UUID shape.
    if len(parts) < 2:
        return False
    return is_uuid_shaped(parts[-2])


async def classify_legacy(
    *,
    actual_row: dict[str, Any] | None,
    git_file_exists: bool,
) -> LegacyCategory:
    """Classify ``actual_row`` against the canonical Git layout.

    Args:
        actual_row: ``api_catalog`` row as a dict (or None if absent).
            Expected keys: ``api_id``, ``git_path``, ``git_commit_sha``,
            ``catalog_content_hash``. ``deleted_at IS NULL`` filtering is
            the caller's responsibility.
        git_file_exists: True iff the canonical file exists at HEAD on
            ``stoa-catalog`` (caller invokes ``CatalogGitClient.get(path)``
            and passes the boolean here).

    Returns:
        :class:`LegacyCategory` — exactly one match per row state.

    Order of evaluation (matters because categories overlap on the surface):

    1. ``ABSENT`` — no row.
    2. ``UUID_HARD_DRIFT`` — ``api_id`` or ``git_path`` UUID-shaped (B).
       Evaluated before D so that a row whose ``api_id`` is a UUID and whose
       ``git_path`` is NULL is still classified B (the UUID is the dominant
       signal, per audit B14 §11.1).
    3. ``PRE_GITOPS`` — both ``git_path`` and ``git_commit_sha`` NULL (D).
    4. ``ORPHAN_DB`` — ``git_path`` NOT NULL but file absent at HEAD (C).
    5. ``GITOPS_CREATED`` — ``catalog_content_hash`` NOT NULL (created by the
       new writer; harmless overlap with HEALTHY_ADOPTABLE only on rows that
       have BOTH a hash and a Git file — which is the steady state for
       freshly-created GitOps APIs).
    6. ``HEALTHY_ADOPTABLE`` — fallback for slug rows with a canonical path
       and a Git file (A).
    """
    if actual_row is None:
        return LegacyCategory.ABSENT

    api_id = actual_row.get("api_id")
    git_path = actual_row.get("git_path")
    git_commit_sha = actual_row.get("git_commit_sha")
    catalog_content_hash = actual_row.get("catalog_content_hash")

    if (isinstance(api_id, str) and is_uuid_shaped(api_id)) or _git_path_uuid_shaped(git_path):
        return LegacyCategory.UUID_HARD_DRIFT

    if git_path is None and git_commit_sha is None:
        return LegacyCategory.PRE_GITOPS

    if git_path is not None and not git_file_exists:
        return LegacyCategory.ORPHAN_DB

    if catalog_content_hash is not None and git_commit_sha is not None and git_file_exists:
        return LegacyCategory.GITOPS_CREATED

    if git_file_exists:
        return LegacyCategory.HEALTHY_ADOPTABLE

    # Defensive default: a row with non-null git_path but the file absent is
    # already covered by ORPHAN_DB above. Anything reaching here is a partial
    # state we surface as ORPHAN_DB so the reconciler does not act on it.
    return LegacyCategory.ORPHAN_DB


__all__ = ["LegacyCategory", "classify_legacy"]
