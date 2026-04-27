"""GitOps writer exceptions.

Spec §6.2 + §6.5 step 9 (CAB-2185 B-FLOW).
"""

from __future__ import annotations


class GitOpsConflictError(Exception):
    """Raised when the remote ``api.yaml`` exists with a different content hash.

    Mapped to HTTP 409 Conflict by the POST handler (Phase 4 wiring).
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        api_id: str,
        remote_hash: str,
        attempted_hash: str,
        message: str | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.api_id = api_id
        self.remote_hash = remote_hash
        self.attempted_hash = attempted_hash
        super().__init__(
            message
            or (
                f"GitOps conflict for {tenant_id}/{api_id}: " f"remote hash {remote_hash} != attempted {attempted_hash}"
            )
        )
