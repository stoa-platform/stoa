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
* ``list_file_metadata`` returns matching paths with blob + commit SHAs.

The fake is deterministic: blob and commit SHAs are derived from a
monotonic counter so tests can assert exact values when needed.
"""

from __future__ import annotations

import fnmatch
import hashlib
from dataclasses import dataclass

from src.services.catalog_git_client.github_contents import CatalogShaConflictError
from src.services.catalog_git_client.models import (
    RemoteCommit,
    RemoteFile,
    RemoteFileMetadata,
    RemotePullRequest,
    RemoteTag,
)


@dataclass
class _Entry:
    content: bytes
    file_sha: str
    commit_sha: str


class InMemoryCatalogGitClient:
    """Test double satisfying :class:`CatalogGitClient`."""

    def __init__(self) -> None:
        self._files: dict[str, _Entry] = {}
        self._branches: dict[str, dict[str, _Entry]] = {}
        # commit_sha -> {path: bytes} — frozen state at that commit so
        # ``read_at_commit`` can replay a specific revision after the file
        # is mutated again.
        self._snapshots: dict[str, dict[str, bytes]] = {}
        self._pull_requests: dict[int, RemotePullRequest] = {}
        self._pull_request_branches: dict[int, str] = {}
        self._tags: dict[str, RemoteTag] = {}
        self._counter = 0
        self._pr_counter = 0

    def _next_sha(self, kind: str) -> str:
        self._counter += 1
        raw = f"{kind}:{self._counter}".encode()
        # nosec B324 — SHA1 is intentional: test fixture only, deterministic
        # mock of GitHub blob/commit SHAs (which are SHA1 anyway). No security
        # boundary involves this hash.
        return hashlib.sha1(raw, usedforsecurity=False).hexdigest()

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
        branch: str | None = None,
    ) -> RemoteCommit:
        target = self._branches.setdefault(branch, dict(self._files)) if branch else self._files
        existing = target.get(path)
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
        target[path] = _Entry(content=content, file_sha=file_sha, commit_sha=commit_sha)
        snapshot = {p: e.content for p, e in target.items()}
        self._snapshots[commit_sha] = snapshot
        return RemoteCommit(commit_sha=commit_sha, file_sha=file_sha, path=path)

    async def create_branch(self, name: str, ref: str | None = None) -> str:
        self._branches.setdefault(name, dict(self._files))
        return self._next_sha("branch")

    async def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        source_branch: str,
        target_branch: str | None = None,
    ) -> RemotePullRequest:
        self._pr_counter += 1
        pr = RemotePullRequest(
            number=self._pr_counter,
            url=f"https://github.test/stoa-platform/stoa-catalog/pull/{self._pr_counter}",
            source_branch=source_branch,
            target_branch=target_branch or "main",
            state="open",
        )
        self._pull_requests[pr.number] = pr
        self._pull_request_branches[pr.number] = source_branch
        return pr

    async def merge_pull_request(self, number: int) -> RemotePullRequest:
        pr = self._pull_requests[number]
        source_branch = self._pull_request_branches[number]
        branch_files = self._branches.get(source_branch, {})
        merge_sha = self._next_sha("merge")
        self._files = {
            path: _Entry(content=entry.content, file_sha=entry.file_sha, commit_sha=merge_sha)
            for path, entry in branch_files.items()
        }
        self._snapshots[merge_sha] = {p: e.content for p, e in self._files.items()}
        merged = RemotePullRequest(
            number=pr.number,
            url=pr.url,
            source_branch=pr.source_branch,
            target_branch=pr.target_branch,
            state="merged",
            merge_commit_sha=merge_sha,
        )
        self._pull_requests[number] = merged
        return merged

    async def create_tag(self, *, name: str, target_sha: str, message: str) -> RemoteTag:
        existing = self._tags.get(name)
        if existing is not None:
            if existing.target_sha != target_sha:
                raise ValueError(f"tag {name!r} already points to {existing.target_sha}")
            return existing
        tag = RemoteTag(name=name, target_sha=target_sha, url=f"https://github.test/stoa-platform/stoa-catalog/tags/{name}")
        self._tags[name] = tag
        return tag

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

    async def list_file_metadata(self, glob_pattern: str) -> list[RemoteFileMetadata]:
        return [
            RemoteFileMetadata(path=p, sha=entry.file_sha, commit_sha=entry.commit_sha)
            for p, entry in self._files.items()
            if fnmatch.fnmatch(p, glob_pattern)
        ]


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
        branch: str | None = None,
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
            path=path, content=content, expected_sha=expected_sha, actor=actor, message=message, branch=branch
        )
