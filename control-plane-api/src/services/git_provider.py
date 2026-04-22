"""Git provider abstraction for multi-provider GitOps (CAB-1890).

ABC that defines the contract for git-based catalog operations.
Implementations: GitLabService (existing), GitHubService (Wave 2).
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from ..config import settings


@dataclass(frozen=True)
class TreeEntry:
    """A single entry in a repository tree listing."""

    name: str
    type: Literal["tree", "blob"]
    path: str


@dataclass(frozen=True)
class CommitRef:
    """Provider-agnostic commit reference."""

    sha: str
    message: str
    author: str
    date: str


@dataclass(frozen=True)
class BranchRef:
    """Provider-agnostic branch reference."""

    name: str
    commit_sha: str
    protected: bool


@dataclass(frozen=True)
class MergeRequestRef:
    """Provider-agnostic merge request / pull request reference.

    On GitHub, ``iid`` is the PR number. On GitLab, ``iid`` is the project-scoped iid.
    """

    id: int
    iid: int
    title: str
    description: str
    state: str
    source_branch: str
    target_branch: str
    web_url: str
    created_at: str
    author: str


class GitProvider(ABC):
    """Abstract base class for git provider operations.

    All catalog/gitops operations go through this interface,
    enabling transparent switching between GitLab and GitHub.
    """

    @abstractmethod
    async def connect(self) -> None:
        """Initialize connection to the git provider."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the git provider."""

    @abstractmethod
    async def clone_repo(self, repo_url: str) -> Path:
        """Clone a repository and return the local path.

        Args:
            repo_url: HTTPS or SSH URL of the repository.

        Returns:
            Path to the cloned repository on disk.
        """

    @abstractmethod
    async def get_file_content(self, project_id: str, file_path: str, ref: str = "main") -> str:
        """Retrieve raw file content from a repository.

        Args:
            project_id: Provider-specific project identifier.
            file_path: Path to the file within the repository.
            ref: Branch, tag, or commit SHA. Defaults to "main".

        Returns:
            Raw file content as string.

        Raises:
            FileNotFoundError: If the file does not exist.
        """

    @abstractmethod
    async def list_files(self, project_id: str, path: str = "", ref: str = "main") -> list[str]:
        """List files in a repository directory.

        Args:
            project_id: Provider-specific project identifier.
            path: Directory path within the repository. Empty for root.
            ref: Branch, tag, or commit SHA. Defaults to "main".

        Returns:
            List of file paths relative to the repository root.
        """

    @abstractmethod
    async def create_webhook(
        self,
        project_id: str,
        url: str,
        secret: str,
        events: list[str],
    ) -> dict[str, Any]:
        """Register a webhook on the repository.

        Args:
            project_id: Provider-specific project identifier.
            url: Webhook callback URL.
            secret: Shared secret for payload verification.
            events: List of event types to subscribe to.

        Returns:
            Webhook metadata including provider-assigned ID.
        """

    @abstractmethod
    async def delete_webhook(self, project_id: str, hook_id: str) -> bool:
        """Remove a webhook from the repository.

        Args:
            project_id: Provider-specific project identifier.
            hook_id: Provider-assigned webhook identifier.

        Returns:
            True if deleted, False if not found.
        """

    @abstractmethod
    async def get_repo_info(self, project_id: str) -> dict[str, Any]:
        """Retrieve repository metadata.

        Args:
            project_id: Provider-specific project identifier.

        Returns:
            Dictionary with keys: name, default_branch, url, visibility.
        """

    # ============================================================
    # Write operations (CAB-2011: GitOps source of truth)
    # ============================================================

    @abstractmethod
    async def create_file(
        self, project_id: str, file_path: str, content: str, commit_message: str, branch: str = "main"
    ) -> dict[str, Any]:
        """Create a new file in the repository.

        Args:
            project_id: Provider-specific project identifier.
            file_path: Path for the new file.
            content: File content.
            commit_message: Git commit message.
            branch: Target branch. Defaults to "main".

        Returns:
            Commit metadata (sha, url).

        Raises:
            ValueError: If the file already exists.
        """

    @abstractmethod
    async def update_file(
        self, project_id: str, file_path: str, content: str, commit_message: str, branch: str = "main"
    ) -> dict[str, Any]:
        """Update an existing file in the repository.

        Args:
            project_id: Provider-specific project identifier.
            file_path: Path to the existing file.
            content: New file content.
            commit_message: Git commit message.
            branch: Target branch. Defaults to "main".

        Returns:
            Commit metadata (sha, url).

        Raises:
            FileNotFoundError: If the file does not exist.
        """

    @abstractmethod
    async def delete_file(self, project_id: str, file_path: str, commit_message: str, branch: str = "main") -> bool:
        """Delete a file from the repository.

        Args:
            project_id: Provider-specific project identifier.
            file_path: Path to the file to delete.
            commit_message: Git commit message.
            branch: Target branch. Defaults to "main".

        Returns:
            True if deleted.

        Raises:
            FileNotFoundError: If the file does not exist.
        """

    async def get_api_override(self, tenant_id: str, api_id: str, environment: str) -> dict | None:
        """Read per-environment override for an API (CAB-2015).

        Looks for ``tenants/{tenant}/apis/{api}/overrides/{environment}.yaml``.
        Returns parsed dict if file exists, ``None`` otherwise.
        Default implementation uses :meth:`get_file_content`; subclasses may override.
        """
        import yaml

        provider = getattr(settings, "GIT_PROVIDER", "gitlab").lower()
        if provider == "github":
            project_id = f"{getattr(settings, 'GITHUB_ORG', '')}/{getattr(settings, 'GITHUB_CATALOG_REPO', '')}"
        else:
            project_id = getattr(settings, "GITLAB_PROJECT_ID", None)
        file_path = f"tenants/{tenant_id}/apis/{api_id}/overrides/{environment}.yaml"
        try:
            content = await self.get_file_content(str(project_id), file_path)
            return yaml.safe_load(content)
        except FileNotFoundError:
            return None

    def is_connected(self) -> bool:
        """Return True when the provider client is initialized."""
        return bool(getattr(self, "_project", None) or getattr(self, "_gh", None))

    async def get_head_commit_sha(self, ref: str = "main") -> str | None:
        """Return the current HEAD commit SHA for the provider's catalog repo."""
        raise NotImplementedError("get_head_commit_sha() must be implemented by the provider")

    async def get_tenant(self, tenant_id: str) -> dict | None:
        """Return tenant metadata from the provider's catalog repo."""
        raise NotImplementedError("get_tenant() must be implemented by the provider")

    async def list_tenants(self) -> list[str]:
        """List tenant identifiers from the provider's catalog repo."""
        raise NotImplementedError("list_tenants() must be implemented by the provider")

    async def get_api(self, tenant_id: str, api_name: str) -> dict | None:
        """Return normalized API metadata for a tenant API."""
        raise NotImplementedError("get_api() must be implemented by the provider")

    async def list_apis(self, tenant_id: str) -> list[dict]:
        """List normalized APIs for a tenant."""
        raise NotImplementedError("list_apis() must be implemented by the provider")

    async def get_api_openapi_spec(self, tenant_id: str, api_name: str) -> dict | None:
        """Return the parsed OpenAPI spec for a tenant API, if present."""
        raise NotImplementedError("get_api_openapi_spec() must be implemented by the provider")

    async def list_apis_parallel(self, tenant_id: str) -> list[dict]:
        """Provider-agnostic fallback to sequential API listing."""
        return await self.list_apis(tenant_id)

    async def get_all_openapi_specs_parallel(self, tenant_id: str, api_ids: list[str]) -> dict[str, dict | None]:
        """Provider-agnostic fallback to parallel OpenAPI spec fetches."""

        async def fetch_spec(api_id: str) -> tuple[str, dict | None]:
            return (api_id, await self.get_api_openapi_spec(tenant_id, api_id))

        results = await asyncio.gather(*[fetch_spec(api_id) for api_id in api_ids])
        return dict(results)

    async def list_mcp_servers(self, tenant_id: str = "_platform") -> list[dict]:
        """List MCP servers defined for a tenant or platform scope."""
        raise NotImplementedError("list_mcp_servers() must be implemented by the provider")

    async def list_all_mcp_servers(self) -> list[dict]:
        """List MCP servers across platform and tenant scopes."""
        raise NotImplementedError("list_all_mcp_servers() must be implemented by the provider")

    @abstractmethod
    async def batch_commit(
        self,
        project_id: str,
        actions: list[dict[str, str]],
        commit_message: str,
        branch: str = "main",
    ) -> dict[str, Any]:
        """Create an atomic commit with multiple file operations.

        Args:
            project_id: Provider-specific project identifier.
            actions: List of file actions. Each action is a dict with keys:
                - action: "create", "update", or "delete"
                - file_path: Path within the repository
                - content: File content (required for create/update)
            commit_message: Git commit message.
            branch: Target branch. Defaults to "main".

        Returns:
            Commit metadata (sha, url).
        """

    # ============================================================
    # CAB-1889 CP-1: provider-agnostic surface used by routers.
    # Operates on the provider's default catalog repository — the
    # router never needs to know about project_id / org-repo.
    # ============================================================

    async def list_tree(self, path: str, ref: str = "main") -> list[TreeEntry]:
        """List immediate children of ``path`` in the catalog repo.

        Returns an empty list when the path is absent. Never raises on 404.
        """
        raise NotImplementedError("list_tree() must be implemented by the provider")

    async def read_file(self, path: str, ref: str = "main") -> str | None:
        """Return file content from the catalog repo, or ``None`` if missing.

        Unlike :meth:`get_file_content`, this method never raises FileNotFoundError.
        """
        raise NotImplementedError("read_file() must be implemented by the provider")

    async def list_path_commits(self, path: str | None, limit: int = 20) -> list[CommitRef]:
        """List recent commits touching ``path`` (or the whole catalog if None)."""
        raise NotImplementedError("list_path_commits() must be implemented by the provider")

    async def write_file(
        self, path: str, content: str, commit_message: str, branch: str = "main"
    ) -> Literal["created", "updated"]:
        """Create-or-update a file on the catalog repo.

        Returns ``"created"`` if the file did not exist before, ``"updated"`` otherwise.
        """
        raise NotImplementedError("write_file() must be implemented by the provider")

    async def remove_file(self, path: str, commit_message: str, branch: str = "main") -> bool:
        """Delete a file from the catalog repo. Raises FileNotFoundError if missing."""
        raise NotImplementedError("remove_file() must be implemented by the provider")

    async def list_branches(self) -> list[BranchRef]:
        """List branches on the catalog repo."""
        raise NotImplementedError("list_branches() must be implemented by the provider")

    async def create_branch(self, name: str, ref: str = "main") -> BranchRef:
        """Create a branch named ``name`` pointing at ``ref`` on the catalog repo."""
        raise NotImplementedError("create_branch() must be implemented by the provider")

    async def list_merge_requests(self, state: str = "opened") -> list[MergeRequestRef]:
        """List merge requests / pull requests on the catalog repo."""
        raise NotImplementedError("list_merge_requests() must be implemented by the provider")

    async def create_merge_request(
        self,
        title: str,
        description: str,
        source_branch: str,
        target_branch: str = "main",
    ) -> MergeRequestRef:
        """Open a merge request / pull request on the catalog repo."""
        raise NotImplementedError("create_merge_request() must be implemented by the provider")

    async def merge_merge_request(self, iid: int) -> MergeRequestRef:
        """Merge a merge request / pull request by its ``iid`` (GitHub: PR number)."""
        raise NotImplementedError("merge_merge_request() must be implemented by the provider")


def git_provider_factory() -> GitProvider:
    """Create a GitProvider instance based on GIT_PROVIDER setting.

    Returns:
        Configured GitProvider implementation.

    Raises:
        ValueError: If GIT_PROVIDER is not a supported provider.
    """
    provider = settings.GIT_PROVIDER.lower()

    if provider == "gitlab":
        # Lazy import to avoid circular dependencies and
        # keep GitLab SDK optional for GitHub-only deployments.
        from .git_service import GitLabService

        return GitLabService()

    if provider == "github":
        from .github_service import GitHubService

        return GitHubService()

    raise ValueError(f"Unsupported GIT_PROVIDER: '{settings.GIT_PROVIDER}'. " f"Supported values: 'gitlab', 'github'.")


@lru_cache(maxsize=1)
def get_git_provider() -> GitProvider:
    """FastAPI dependency — cached GitProvider singleton.

    Use with ``Depends(get_git_provider)`` in router endpoints.
    The instance is created once via ``git_provider_factory()`` and reused
    across all requests for the lifetime of the process.
    """
    return git_provider_factory()
