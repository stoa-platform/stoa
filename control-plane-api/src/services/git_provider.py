"""Git provider abstraction for multi-provider GitOps (CAB-1890).

ABC that defines the contract for git-based catalog operations.
Implementations: GitLabService (existing), GitHubService (Wave 2).
"""

from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import settings


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

        project_id = getattr(settings, "GITLAB_PROJECT_ID", None) or (
            f"{getattr(settings, 'GITHUB_ORG', '')}/{getattr(settings, 'GITHUB_CATALOG_REPO', '')}"
        )
        file_path = f"tenants/{tenant_id}/apis/{api_id}/overrides/{environment}.yaml"
        try:
            content = await self.get_file_content(str(project_id), file_path)
            return yaml.safe_load(content)
        except FileNotFoundError:
            return None

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
