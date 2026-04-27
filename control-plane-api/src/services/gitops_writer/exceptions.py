"""GitOps writer exceptions.

Spec §6.2, §6.5 steps 2/7/9/10/12, §6.14 (CAB-2185 B-FLOW, CAB-2188 B12,
CAB-2187 B10).
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
            or (f"GitOps conflict for {tenant_id}/{api_id}: remote hash {remote_hash} != attempted {attempted_hash}")
        )


class InvalidApiNameError(Exception):
    """Raised when ``api_name`` is empty or UUID-shaped (spec §6.5 step 2).

    Mapped to HTTP 422 by the POST handler.
    """

    def __init__(self, *, api_name: str, reason: str) -> None:
        self.api_name = api_name
        self.reason = reason
        super().__init__(f"invalid api_name {api_name!r}: {reason}")


class LegacyCollisionError(Exception):
    """Raised when an existing ``api_catalog`` row falls in legacy category B/C/D.

    Spec §6.14 + §11.1: B = UUID hard drift, C = orphan DB, D = pre-GitOps DB-only.
    All three require separate migration cycles and cannot be auto-repaired.

    Mapped to HTTP 409 by the POST handler.
    """

    def __init__(self, *, tenant_id: str, api_id: str, category: str, detail: str | None = None) -> None:
        self.tenant_id = tenant_id
        self.api_id = api_id
        self.category = category
        self.detail = detail
        msg = f"legacy collision for {tenant_id}/{api_id}: category={category}"
        if detail:
            msg = f"{msg} ({detail})"
        super().__init__(msg)


class InfrastructureBugError(Exception):
    """Raised when ``read_at_commit`` returns ``None`` after a successful push.

    Spec §6.5 step 12 + Doctrine #6: this is a 500-grade infrastructure bug —
    the writer pushed a commit but the same path no longer resolves at that
    commit. Surfaces explicitly rather than degrading silently.
    """

    def __init__(self, *, git_path: str, commit_sha: str) -> None:
        self.git_path = git_path
        self.commit_sha = commit_sha
        super().__init__(f"git_path 404 after commit at {commit_sha}: {git_path}")


class GitOpsRaceExhaustedError(Exception):
    """Raised after 3 retries on optimistic-CAS race conditions (spec §6.5 step 10).

    Mapped to HTTP 503 by the POST handler so the client can retry safely.
    """

    def __init__(self, *, tenant_id: str, api_id: str, attempts: int) -> None:
        self.tenant_id = tenant_id
        self.api_id = api_id
        self.attempts = attempts
        super().__init__(f"optimistic-CAS race not resolved for {tenant_id}/{api_id} after {attempts} retries")
