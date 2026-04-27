"""``CatalogGitClient`` Protocol — figé Phase 3.

Spec §6.7 (CAB-2184 B-CLIENT).

Five methods, runtime-checkable so tests can assert isinstance() on stubs.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import RemoteCommit, RemoteFile


@runtime_checkable
class CatalogGitClient(Protocol):
    """Read/write contract for the ``stoa-catalog`` remote.

    All implementations MUST go through PyGithub Contents API or an equivalent
    HTTP layer — never via ``git`` CLI / worktree (spec §6.7, garde-fou §9.10).
    """

    async def get(self, path: str) -> RemoteFile | None:
        """Return the file at ``path`` on the default branch HEAD, or ``None``.

        Phase 4 implementation must NOT raise on 404 — it returns ``None``.
        """
        ...

    async def create_or_update(
        self,
        *,
        path: str,
        content: bytes,
        expected_sha: str | None,
        actor: str,
        message: str,
    ) -> RemoteCommit:
        """Commit ``content`` at ``path``.

        ``expected_sha`` is the previous blob SHA (None for create). Implements
        optimistic CAS: a mismatch must trigger a re-read upstream (spec §6.5
        step 10 retry loop).
        """
        ...

    async def read_at_commit(self, path: str, commit_sha: str) -> bytes | None:
        """Return bytes of ``path`` at the given commit, or ``None`` (404).

        Used after the initial commit to confirm the path stored in DB
        actually resolves on Git (spec §6.5 step 12, garde-fou Doctrine #6).
        """
        ...

    async def latest_file_commit(self, path: str) -> str:
        """Return the commit SHA of the latest commit touching ``path``.

        Spec §6.5 step 11.
        """
        ...

    async def list(self, glob_pattern: str) -> list[str]:
        """Return paths matching ``glob_pattern`` (e.g. ``tenants/*/apis/*/api.yaml``).

        Used by the reconciler tick (spec §6.6).
        """
        ...
