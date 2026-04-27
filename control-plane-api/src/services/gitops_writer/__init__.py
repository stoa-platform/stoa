"""GitOps writer — Phase 4-2 orchestration.

Spec: ``specs/api-creation-gitops-rewrite.md`` v1.0 (PR #2600 + §11 audit-informed #2602).

Status: orchestration shipped. ``GitOpsWriter.create_api`` implements the 18-step
flow from §6.5 (CAB-2185 B-FLOW). The handler branch and reconciler loop ship
together in Phase 4-2; the flag ``GITOPS_CREATE_API_ENABLED`` defaults to OFF
so production behaviour is unchanged until Phase 6.
"""

from .advisory_lock import advisory_lock_key
from .exceptions import (
    GitOpsConflictError,
    GitOpsRaceExhaustedError,
    InfrastructureBugError,
    InvalidApiNameError,
    LegacyCollisionError,
)
from .hashing import compute_catalog_content_hash
from .models import ApiCreatePayload, CatalogContentHash, CreateApiResult
from .paths import canonical_catalog_path, is_uuid_shaped, parse_canonical_path
from .writer import GitOpsWriter

__all__ = [
    "ApiCreatePayload",
    "CatalogContentHash",
    "CreateApiResult",
    "GitOpsConflictError",
    "GitOpsRaceExhaustedError",
    "GitOpsWriter",
    "InfrastructureBugError",
    "InvalidApiNameError",
    "LegacyCollisionError",
    "advisory_lock_key",
    "canonical_catalog_path",
    "compute_catalog_content_hash",
    "is_uuid_shaped",
    "parse_canonical_path",
]
