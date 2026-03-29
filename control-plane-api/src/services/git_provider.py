"""Git provider abstraction for multi-provider GitOps (CAB-1890).

ABC that defines the contract for git-based catalog operations.
Implementations: GitLabService (existing), GitHubService (Wave 2).
"""

from abc import ABC, abstractmethod
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
        raise NotImplementedError("GitHub provider not yet implemented. Coming in Wave 2 (CAB-1890 Phase 3).")

    raise ValueError(f"Unsupported GIT_PROVIDER: '{settings.GIT_PROVIDER}'. " f"Supported values: 'gitlab', 'github'.")
