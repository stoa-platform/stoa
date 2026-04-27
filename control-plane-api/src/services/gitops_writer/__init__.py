"""GitOps writer — Phase 3 scaffold.

Spec: ``specs/api-creation-gitops-rewrite.md`` v1.0 (PR #2600 + §11 audit-informed #2602).

Status: scaffold. Implementation in Phase 4 (CAB-2185 B-FLOW + CAB-2184 B-CLIENT).
"""

from .advisory_lock import advisory_lock_key
from .exceptions import GitOpsConflictError
from .hashing import compute_catalog_content_hash
from .models import ApiCreatePayload, CatalogContentHash, CreateApiResult
from .writer import GitOpsWriter

__all__ = [
    "ApiCreatePayload",
    "CatalogContentHash",
    "CreateApiResult",
    "GitOpsConflictError",
    "GitOpsWriter",
    "advisory_lock_key",
    "compute_catalog_content_hash",
]
