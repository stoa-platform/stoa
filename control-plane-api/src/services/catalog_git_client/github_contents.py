"""``GitHubContentsCatalogClient`` — Phase 3 scaffold (NotImplementedError).

Spec §6.7 (CAB-2184 B-CLIENT).

First implementation of ``CatalogGitClient``. Reuses the existing
``services.github_service.GitHubService`` PyGithub wrapper. Implementation
lands in Phase 4.
"""

from __future__ import annotations

from typing import Any

from .models import RemoteCommit, RemoteFile


class GitHubContentsCatalogClient:
    """PyGithub Contents API client for ``stoa-catalog``.

    Phase 3: every method raises ``NotImplementedError``. Phase 4 wires
    ``GitHubService.create_or_update_file`` and ``get_file_content``.
    """

    def __init__(self, *, github_service: Any | None = None) -> None:
        self._github_service = github_service

    async def get(self, path: str) -> RemoteFile | None:
        raise NotImplementedError(
            "GitHubContentsCatalogClient.get: stub Phase 3. "
            "Implementation in Phase 4 — see CAB-2184 (B-CLIENT) and spec §6.7."
        )

    async def create_or_update(
        self,
        *,
        path: str,
        content: bytes,
        expected_sha: str | None,
        actor: str,
        message: str,
    ) -> RemoteCommit:
        raise NotImplementedError(
            "GitHubContentsCatalogClient.create_or_update: stub Phase 3. "
            "Implementation in Phase 4 — see CAB-2184 (B-CLIENT) and spec §6.7."
        )

    async def read_at_commit(self, path: str, commit_sha: str) -> bytes | None:
        raise NotImplementedError(
            "GitHubContentsCatalogClient.read_at_commit: stub Phase 3. "
            "Implementation in Phase 4 — see CAB-2184 (B-CLIENT) and spec §6.5 step 12."
        )

    async def latest_file_commit(self, path: str) -> str:
        raise NotImplementedError(
            "GitHubContentsCatalogClient.latest_file_commit: stub Phase 3. "
            "Implementation in Phase 4 — see CAB-2184 (B-CLIENT) and spec §6.5 step 11."
        )

    async def list(self, glob_pattern: str) -> list[str]:
        raise NotImplementedError(
            "GitHubContentsCatalogClient.list: stub Phase 3. "
            "Implementation in Phase 4 — see CAB-2184 (B-CLIENT) and spec §6.6."
        )
