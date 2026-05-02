"""GitOps writer payload + result models.

Spec §6.2, §6.9 (CAB-2185 B-FLOW + CAB-2183 B-LAYOUT).

Phase 3 status: dataclasses only. The Pydantic schema mapping from the existing
``POST /v1/tenants/{tid}/apis`` payload to ``ApiCreatePayload`` is Phase 4 work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CatalogReleaseRef:
    """Catalog release metadata attached to a GitOps desired-state generation."""

    release_id: str
    tag_name: str
    source_branch: str
    pull_request_url: str
    pull_request_number: int
    merge_commit_sha: str


@dataclass(frozen=True)
class ApiCreatePayload:
    """Validated payload accepted by ``GitOpsWriter.create_api``.

    Mirrors the YAML mapping table in spec §6.9. ``api_name`` MUST be a slug
    (``[a-z0-9-]+``); UUID-shaped values are rejected at step 2 of the flow.
    """

    api_name: str
    display_name: str
    version: str
    backend_url: str
    description: str = ""
    category: str | None = None
    tags: tuple[str, ...] = ()
    audience: str = "public"
    openapi_spec: dict[str, Any] | None = None


@dataclass(frozen=True)
class CreateApiResult:
    """Result of a successful ``create_api`` call.

    The ``id`` returned to the HTTP layer is the slug ``api_id``, never the
    internal ``api_catalog.id`` PK (spec §6.4 — level 2 distinct from level 1).
    """

    api_id: str
    api_name: str
    git_path: str
    git_commit_sha: str
    catalog_content_hash: str
    case: str  # "A" (new), "B" (idempotent no-op), unused for "C" (raised as error)
    catalog_release: CatalogReleaseRef | None = None
    extra: dict[str, Any] = field(default_factory=dict)


CatalogContentHash = str
"""sha256_hex of the api.yaml bytes — see ``hashing.py``."""
