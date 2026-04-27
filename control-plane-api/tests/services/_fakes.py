"""In-memory fakes for the GitOps create flow tests.

Spec §6.7 (CAB-2184). The :class:`InMemoryCatalogGitClient` mimics a tiny
slice of the GitHub Contents API behaviour without touching PyGithub:

* ``get`` returns a ``RemoteFile`` if the path is present, else ``None``.
* ``create_or_update`` performs optimistic CAS: ``expected_sha`` must match
  the stored blob SHA when the path already exists, else
  :class:`CatalogShaConflictError` is raised.
* ``read_at_commit`` returns the bytes recorded for a given (path,
  commit_sha) pair (defaults to the path's current content if the commit
  was issued by this fake).
* ``latest_file_commit`` returns the most recent commit SHA recorded for
  the path.
* ``list`` returns paths matching ``fnmatch.fnmatch(glob, path)``.

The fake is deterministic: blob and commit SHAs are derived from a
monotonic counter so tests can assert exact values when needed.
"""

from __future__ import annotations

import fnmatch
import hashlib
from dataclasses import dataclass

from src.services.catalog_git_client.github_contents import CatalogShaConflictError
from src.services.catalog_git_client.models import RemoteCommit, RemoteFile


@dataclass
class _Entry:
    content: bytes
    file_sha: str
    commit_sha: str


class InMemoryCatalogGitClient:
    """Test double satisfying :class:`CatalogGitClient`."""

    def __init__(self) -> None:
        self._files: dict[str, _Entry] = {}
        # commit_sha -> {path: bytes} — frozen state at that commit so
        # ``read_at_commit`` can replay a specific revision after the file
        # is mutated again.
        self._snapshots: dict[str, dict[str, bytes]] = {}
        self._counter = 0

    def _next_sha(self, kind: str) -> str:
        self._counter += 1
        raw = f"{kind}:{self._counter}".encode()
        # nosec B324 — SHA1 is intentional: test fixture only, deterministic
        # mock of GitHub blob/commit SHAs (which are SHA1 anyway). No security
        # boundary involves this hash.
        return hashlib.sha1(raw, usedforsecurity=False).hexdigest()  # noqa: S324

    def seed(self, path: str, content: bytes, *, commit_sha: str | None = None) -> str:
        """Pre-populate a file. Returns the recorded commit SHA."""
        commit = commit_sha or self._next_sha("commit")
        file_sha = self._next_sha("blob")
        self._files[path] = _Entry(content=content, file_sha=file_sha, commit_sha=commit)
        snapshot = {p: e.content for p, e in self._files.items()}
        self._snapshots[commit] = snapshot
        return commit

    async def get(self, path: str) -> RemoteFile | None:
        entry = self._files.get(path)
        if entry is None:
            return None
        return RemoteFile(path=path, content=entry.content, sha=entry.file_sha)

    async def create_or_update(
        self,
        *,
        path: str,
        content: bytes,
        expected_sha: str | None,
        actor: str,
        message: str,
    ) -> RemoteCommit:
        existing = self._files.get(path)
        if existing is None and expected_sha is not None:
            raise CatalogShaConflictError(
                path=path, expected_sha=expected_sha, status=409, message="missing file but expected_sha set"
            )
        if existing is not None and expected_sha is None:
            raise CatalogShaConflictError(
                path=path, expected_sha=None, status=422, message="file exists but expected_sha=None"
            )
        if existing is not None and expected_sha != existing.file_sha:
            raise CatalogShaConflictError(path=path, expected_sha=expected_sha, status=409, message="blob SHA mismatch")

        commit_sha = self._next_sha("commit")
        file_sha = self._next_sha("blob")
        self._files[path] = _Entry(content=content, file_sha=file_sha, commit_sha=commit_sha)
        snapshot = {p: e.content for p, e in self._files.items()}
        self._snapshots[commit_sha] = snapshot
        return RemoteCommit(commit_sha=commit_sha, file_sha=file_sha, path=path)

    async def read_at_commit(self, path: str, commit_sha: str) -> bytes | None:
        snapshot = self._snapshots.get(commit_sha)
        if snapshot is None:
            return None
        return snapshot.get(path)

    async def latest_file_commit(self, path: str) -> str:
        entry = self._files.get(path)
        if entry is None:
            raise FileNotFoundError(f"no commits touch {path}")
        return entry.commit_sha

    async def list(self, glob_pattern: str) -> list[str]:
        return [p for p in self._files if fnmatch.fnmatch(p, glob_pattern)]


class _RaceOnceCatalogGitClient(InMemoryCatalogGitClient):
    """Variant that injects ``CatalogShaConflictError`` on the first create.

    Used to verify the spec §6.5 step 10 retry loop: first attempt → race;
    second attempt → file appeared with same hash → idempotent (Case B).
    """

    def __init__(self, *, race_content: bytes) -> None:
        super().__init__()
        self._race_content = race_content
        self._raced = False

    async def create_or_update(
        self,
        *,
        path: str,
        content: bytes,
        expected_sha: str | None,
        actor: str,
        message: str,
    ) -> RemoteCommit:
        if not self._raced and expected_sha is None and self._files.get(path) is None:
            # Simulate a concurrent push that landed the same content
            # between our get() and our create_or_update().
            self._raced = True
            self.seed(path, self._race_content)
            raise CatalogShaConflictError(
                path=path, expected_sha=None, status=422, message="race: file appeared concurrently"
            )
        return await super().create_or_update(
            path=path, content=content, expected_sha=expected_sha, actor=actor, message=message
        )
