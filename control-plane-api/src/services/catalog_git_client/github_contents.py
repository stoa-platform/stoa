"""``GitHubContentsCatalogClient`` — Phase 4-1 implementation.

Spec §6.7 (CAB-2184 B-CLIENT) + §6.5 steps 9-12 + §6.6.

The client speaks to ``stoa-catalog`` via PyGithub Contents/Git Data APIs,
reusing the existing :class:`GitHubService` connection (auth, semaphores,
``run_sync`` thread offload). Per garde-fou §9.10: no ``git`` CLI, no
worktree, no ``git push``.

Implementation rule (CP-1 C.1): every PyGithub object that lazy-loads must
be materialised inside the closure passed to ``run_sync`` — returning a
lazy ``ContentFile`` and reading ``decoded_content`` after ``await`` would
re-introduce sync-in-async blocking.
"""

from __future__ import annotations

import fnmatch
from typing import TYPE_CHECKING

from github import GithubException

from src.config import settings
from src.services.git_executor import (
    GITHUB_CONTENTS_WRITE_SEMAPHORE,
    GITHUB_READ_SEMAPHORE,
    run_sync,
)

from .models import RemoteCommit, RemoteFile, RemotePullRequest, RemoteTag

if TYPE_CHECKING:
    from src.services.github_service import GitHubService


class CatalogShaConflictError(Exception):
    """Raised when ``create_or_update`` hits an optimistic-CAS mismatch.

    Mapped to the spec §6.5 step 10 retry loop in the writer (``relire,
    réévaluer Case A/B/C, retry max 3x``).
    """

    def __init__(self, *, path: str, expected_sha: str | None, status: int, message: str) -> None:
        self.path = path
        self.expected_sha = expected_sha
        self.status = status
        super().__init__(message)


_ACTOR_MAX_LEN = 120


def _sanitize_actor(actor: str) -> str:
    """Strip newlines and control chars from ``actor`` before commit-message use.

    The HTTP layer is expected to extract ``actor`` from a validated JWT
    claim, but this client adds a defence-in-depth scrub so that even a
    misconfigured caller cannot inject a multi-line commit message via a
    crafted ``actor`` string. Length is capped to keep commit subjects
    manageable.
    """
    if not actor:
        return "<unknown>"
    cleaned = "".join(ch for ch in actor if ch == " " or (ch.isprintable() and ch not in "\r\n"))
    cleaned = cleaned.strip()
    if not cleaned:
        return "<unknown>"
    return cleaned[:_ACTOR_MAX_LEN]


class GitHubContentsCatalogClient:
    """PyGithub-backed ``CatalogGitClient`` implementation.

    Caller responsibilities (out of scope for this client):

    * **Authn/authz**: the caller (writer / reconciler) is responsible for
      tenant ownership and RBAC checks. This client does not validate that
      ``path`` belongs to the calling user's tenant.
    * **Retry policy**: this client maps optimistic-CAS failures to
      :class:`CatalogShaConflictError` for the writer's spec §6.5 step 10
      retry loop, and lets transient errors (5xx, timeouts via
      :class:`asyncio.TimeoutError`) bubble up so the caller can decide.

    Args:
        github_service: An already-connected :class:`GitHubService` instance.
            Connection lifecycle (connect/disconnect) is the caller's
            responsibility — this client only consumes the underlying
            ``Github`` client via ``github_service._require_gh()``.
    """

    def __init__(self, *, github_service: GitHubService) -> None:
        self._github_service = github_service

    @property
    def _project_id(self) -> str:
        return settings.git.github.catalog_project_id

    @property
    def _default_branch(self) -> str:
        return settings.git.default_branch

    async def get(self, path: str) -> RemoteFile | None:
        """Read ``path`` at HEAD on the default branch.

        Returns ``None`` on 404 — the caller distinguishes Case A (absent)
        from Case B/C (present) per spec §6.5 step 9.
        """
        gh = self._github_service._require_gh()
        project_id = self._project_id
        ref = self._default_branch

        def _get() -> RemoteFile | None:
            repo = gh.get_repo(project_id)
            try:
                content_file = repo.get_contents(path, ref=ref)
            except GithubException as exc:
                if exc.status == 404:
                    return None
                raise
            if isinstance(content_file, list):
                raise ValueError(f"{path} resolves to a directory, not a file")
            # Materialise lazy attributes inside the closure.
            return RemoteFile(
                path=path,
                content=bytes(content_file.decoded_content),
                sha=content_file.sha,
            )

        return await run_sync(
            _get,
            semaphore=GITHUB_READ_SEMAPHORE,
            op_name="catalog_git_client.get",
        )

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
        """Commit ``content`` at ``path`` via the Contents API.

        ``expected_sha is None`` → ``create_file``; otherwise ``update_file``
        with the prior blob SHA for optimistic CAS. On SHA mismatch the
        client raises :class:`CatalogShaConflictError` so the writer's retry
        loop (spec §6.5 step 10) can re-evaluate Case A/B/C.

        ``actor`` is appended to the commit message (PyGithub ``create_file``
        does not expose a per-call author; signing remains repo-side).
        """
        gh = self._github_service._require_gh()
        project_id = self._project_id
        target_branch = branch or self._default_branch
        # Sanitize actor before splicing into the commit message so a
        # JWT-derived string cannot inject newlines or control chars.
        safe_actor = _sanitize_actor(actor)
        full_message = f"{message}\n\nActor: {safe_actor}"
        # PyGithub expects str content for the Contents API.
        content_str = content.decode("utf-8")

        def _create_or_update() -> RemoteCommit:
            repo = gh.get_repo(project_id)
            try:
                if expected_sha is None:
                    result = repo.create_file(path, full_message, content_str, branch=target_branch)
                else:
                    result = repo.update_file(
                        path,
                        full_message,
                        content_str,
                        expected_sha,
                        branch=target_branch,
                    )
            except GithubException as exc:
                # 409 Conflict and 422 Unprocessable both indicate optimistic-CAS
                # mismatch in the Contents API, depending on whether the file
                # exists or has been concurrently mutated.
                if exc.status in (409, 422):
                    raise CatalogShaConflictError(
                        path=path,
                        expected_sha=expected_sha,
                        status=exc.status,
                        message=f"SHA mismatch on {path}: {exc.data}",
                    ) from exc
                raise

            commit_sha = result["commit"].sha
            file_sha = result["content"].sha
            return RemoteCommit(commit_sha=commit_sha, file_sha=file_sha, path=path)

        return await run_sync(
            _create_or_update,
            semaphore=GITHUB_CONTENTS_WRITE_SEMAPHORE,
            op_name="catalog_git_client.create_or_update",
        )

    async def create_branch(self, name: str, ref: str | None = None) -> str:
        """Create ``name`` from ``ref`` and return the branch HEAD SHA."""
        gh = self._github_service._require_gh()
        project_id = self._project_id
        base_ref_name = ref or self._default_branch

        def _create_branch() -> str:
            repo = gh.get_repo(project_id)
            try:
                base_ref = repo.get_git_ref(f"heads/{base_ref_name}")
                repo.create_git_ref(f"refs/heads/{name}", base_ref.object.sha)
            except GithubException as exc:
                # Idempotent retry: if a previous request created the same
                # branch, return its current head rather than failing the
                # catalog write before the PR step can inspect it.
                if exc.status != 422:
                    raise
            branch = repo.get_branch(name)
            return branch.commit.sha

        return await run_sync(
            _create_branch,
            semaphore=GITHUB_CONTENTS_WRITE_SEMAPHORE,
            op_name="catalog_git_client.create_branch",
        )

    async def create_pull_request(
        self,
        *,
        title: str,
        body: str,
        source_branch: str,
        target_branch: str | None = None,
    ) -> RemotePullRequest:
        """Open a PR for a catalog release branch."""
        gh = self._github_service._require_gh()
        project_id = self._project_id
        base_branch = target_branch or self._default_branch

        def _create_pr() -> RemotePullRequest:
            repo = gh.get_repo(project_id)
            pr = repo.create_pull(title=title, body=body, head=source_branch, base=base_branch)
            return RemotePullRequest(
                number=pr.number,
                url=pr.html_url,
                source_branch=source_branch,
                target_branch=base_branch,
                state=pr.state,
                merge_commit_sha=getattr(pr, "merge_commit_sha", None),
            )

        return await run_sync(
            _create_pr,
            semaphore=GITHUB_CONTENTS_WRITE_SEMAPHORE,
            op_name="catalog_git_client.create_pull_request",
        )

    async def merge_pull_request(self, number: int) -> RemotePullRequest:
        """Merge a catalog PR and return the provider metadata."""
        gh = self._github_service._require_gh()
        project_id = self._project_id

        def _merge_pr() -> RemotePullRequest:
            repo = gh.get_repo(project_id)
            pr = repo.get_pull(number)
            if not pr.merged:
                merge_status = pr.merge(merge_method="squash")
                merge_sha = getattr(merge_status, "sha", None)
            else:
                merge_sha = None
            merged = repo.get_pull(number)
            return RemotePullRequest(
                number=merged.number,
                url=merged.html_url,
                source_branch=merged.head.ref if merged.head else "",
                target_branch=merged.base.ref if merged.base else self._default_branch,
                state="merged" if merged.merged else merged.state,
                merge_commit_sha=merged.merge_commit_sha or merge_sha,
            )

        return await run_sync(
            _merge_pr,
            semaphore=GITHUB_CONTENTS_WRITE_SEMAPHORE,
            op_name="catalog_git_client.merge_pull_request",
        )

    async def create_tag(self, *, name: str, target_sha: str, message: str) -> RemoteTag:
        """Create an annotated tag for a catalog release generation."""
        gh = self._github_service._require_gh()
        project_id = self._project_id

        def _create_tag() -> RemoteTag:
            repo = gh.get_repo(project_id)
            try:
                existing = repo.get_git_ref(f"tags/{name}")
                existing_target_sha = existing.object.sha
                if getattr(existing.object, "type", None) == "tag":
                    existing_target_sha = repo.get_git_tag(existing.object.sha).object.sha
                if existing_target_sha == target_sha:
                    return RemoteTag(name=name, target_sha=target_sha, url=getattr(existing, "url", None))
                raise ValueError(f"tag {name!r} already exists and points to {existing_target_sha}")
            except GithubException as exc:
                if exc.status != 404:
                    raise

            tag = repo.create_git_tag(tag=name, message=message, object=target_sha, type="commit")
            ref = repo.create_git_ref(ref=f"refs/tags/{name}", sha=tag.sha)
            return RemoteTag(name=name, target_sha=target_sha, url=getattr(ref, "url", None))

        return await run_sync(
            _create_tag,
            semaphore=GITHUB_CONTENTS_WRITE_SEMAPHORE,
            op_name="catalog_git_client.create_tag",
        )

    async def read_at_commit(self, path: str, commit_sha: str) -> bytes | None:
        """Read ``path`` at the given commit SHA.

        Returns ``None`` on 404. Spec §6.5 step 12 + garde-fou Doctrine #6:
        the caller treats ``None`` after a successful push as a 500-grade
        infrastructure bug.
        """
        gh = self._github_service._require_gh()
        project_id = self._project_id

        def _read() -> bytes | None:
            repo = gh.get_repo(project_id)
            try:
                content_file = repo.get_contents(path, ref=commit_sha)
            except GithubException as exc:
                if exc.status == 404:
                    return None
                raise
            if isinstance(content_file, list):
                raise ValueError(f"{path} resolves to a directory, not a file at {commit_sha}")
            return bytes(content_file.decoded_content)

        return await run_sync(
            _read,
            semaphore=GITHUB_READ_SEMAPHORE,
            op_name="catalog_git_client.read_at_commit",
        )

    async def latest_file_commit(self, path: str) -> str:
        """Return the SHA of the latest commit touching ``path``.

        Spec §6.5 step 11. Walks the commit history filtered by ``path`` and
        materialises the first SHA inside the closure (no lazy iteration
        outside the thread).
        """
        gh = self._github_service._require_gh()
        project_id = self._project_id
        branch = self._default_branch

        def _latest() -> str:
            repo = gh.get_repo(project_id)
            commits = repo.get_commits(sha=branch, path=path)
            for commit in commits:
                # First page, first item — fully materialise the SHA before
                # returning so we never read off a lazy proxy.
                return commit.sha
            raise FileNotFoundError(f"no commits touch {path} on {branch}")

        return await run_sync(
            _latest,
            semaphore=GITHUB_READ_SEMAPHORE,
            op_name="catalog_git_client.latest_file_commit",
        )

    async def list(self, glob_pattern: str) -> list[str]:
        """Return paths matching ``glob_pattern`` on the default branch.

        Phase 4-1 supports the reconciler-only pattern
        ``tenants/*/apis/*/api.yaml`` (spec §6.6). Other patterns are
        accepted but evaluated by ``fnmatch``; see test coverage for the
        guarantees.
        """
        gh = self._github_service._require_gh()
        project_id = self._project_id
        branch = self._default_branch

        def _list() -> list[str]:
            repo = gh.get_repo(project_id)
            try:
                ref = repo.get_git_ref(f"heads/{branch}")
                tree = repo.get_git_tree(ref.object.sha, recursive=True)
            except GithubException as exc:
                if exc.status == 404:
                    return []
                raise
            paths: list[str] = []
            for entry in tree.tree:
                if entry.type != "blob":
                    continue
                if fnmatch.fnmatch(entry.path, glob_pattern):
                    paths.append(entry.path)
            return paths

        return await run_sync(
            _list,
            semaphore=GITHUB_READ_SEMAPHORE,
            op_name="catalog_git_client.list",
        )
