"""Legacy collision classifier — Phase 3 scaffold.

Spec §6.14 (CAB-2188 B12).

Four categories:

* **A** — sain adoptable (slug = api_name, git_path canonique, file present)
* **B** — UUID hard drift (api_id or git_path UUID-shaped)
* **C** — orphelin DB (row active, file absent from Git HEAD)
* **D** — pré-GitOps DB-only (git_path NULL and git_commit_sha NULL — surfaced
  by audit B14 / CAB-2193, see spec §6.14 cat D)
"""

from __future__ import annotations

from enum import StrEnum


class LegacyCategory(StrEnum):
    """Categories used by the reconciler when classifying an existing row.

    Names mirror the values written to ``api_sync_status.status`` /
    ``last_error`` per spec §6.14 + §11.
    """

    SAIN = "A"
    UUID_DRIFT = "B"
    ORPHAN = "C"
    PRE_GITOPS = "D"


async def classify_legacy(
    *,
    tenant_id: str,
    api_name: str,
    git_path: str | None,
    git_commit_sha: str | None,
    api_id: str,
) -> LegacyCategory:
    """Return the legacy category for a row.

    Phase 3 stub. Phase 4 implements the rules from spec §6.14 + §6.5 step 7.
    """
    raise NotImplementedError(
        "classify_legacy: stub Phase 3. " "Implementation in Phase 4 — see CAB-2188 (B12) and spec §6.14."
    )
