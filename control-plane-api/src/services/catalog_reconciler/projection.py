"""Projection helpers — Phase 3 scaffold.

Spec §6.5 step 14 + §6.6 + §6.9 mapping table (CAB-2186 B-WORKER + CAB-2180
B-CATALOG).

The reconciler reads ``stoa-catalog`` Git first, then projects the YAML to
``api_catalog``. The projection NEVER writes ``target_gateways`` or
``openapi_spec`` (preserved fields).
"""

from __future__ import annotations

from typing import Any


def render_api_catalog_projection(
    *,
    parsed_content: dict[str, Any],
    git_commit_sha: str,
    catalog_content_hash: str,
    git_path: str,
) -> dict[str, Any]:
    """Render the expected ``api_catalog`` row from a parsed YAML.

    Phase 3 stub. Phase 4 implements the §6.9 mapping table, including:
    - ``portal_published`` derived from ``"portal:published" in tags``
    - ``audience`` defaulting to ``"public"``
    - ``target_gateways`` and ``openapi_spec`` left out of the projection
    """
    raise NotImplementedError(
        "render_api_catalog_projection: stub Phase 3. "
        "Implementation in Phase 4 — see CAB-2186 (B-WORKER) and spec §6.9 mapping."
    )


def row_matches_projection(
    *,
    actual_row: dict[str, Any],
    expected_row: dict[str, Any],
) -> bool:
    """Return True iff every projected field matches.

    Phase 3 stub. Phase 4 implements the comparison set from spec §6.6 (api_id,
    tenant_id, api_name, version, status, category, tags, portal_published,
    audience, git_path, git_commit_sha, catalog_content_hash + non-null
    ``read_at_commit``). Excluded: target_gateways, openapi_spec, metadata.
    """
    raise NotImplementedError(
        "row_matches_projection: stub Phase 3. " "Implementation in Phase 4 — see CAB-2186 (B-WORKER) and spec §6.6."
    )
