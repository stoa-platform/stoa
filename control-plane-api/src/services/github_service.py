"""GitHub implementation of GitProvider (CAB-1890 Wave 2).

Uses PyGithub for API operations and subprocess git for clone.
project_id format: "org/repo" (e.g. "stoa-platform/stoa-catalog").
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from github import Auth, Github, GithubException

from ..config import settings
from .git_provider import GitProvider

logger = logging.getLogger(__name__)


class GitHubService(GitProvider):
    """GitHub implementation of GitProvider — GitOps source of truth."""

    def __init__(self) -> None:
        self._gh: Github | None = None

    async def connect(self) -> None:
        """Initialize GitHub connection using GITHUB_TOKEN."""
        try:
            auth = Auth.Token(settings.GITHUB_TOKEN)
            self._gh = Github(auth=auth)
            # Validate credentials by fetching authenticated user
            user = self._gh.get_user().login
            logger.info("Connected to GitHub as %s", user)
        except Exception as e:
            logger.error("Failed to connect to GitHub: %s", e)
            raise

    async def disconnect(self) -> None:
        """Close GitHub connection."""
        if self._gh:
            self._gh.close()
        self._gh = None

    async def clone_repo(self, repo_url: str) -> Path:
        """Clone a GitHub repository to a temporary directory."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="stoa-gh-"))
        token = settings.GITHUB_TOKEN
        # Inject token into HTTPS URL for auth
        authed_url = repo_url.replace("https://", f"https://x-access-token:{token}@")
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth=1",
            authed_url,
            str(tmp_dir / "repo"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone failed: {stderr.decode().strip()}")
        return tmp_dir / "repo"

    def _get_repo(self, project_id: str) -> Any:
        """Get a PyGithub Repository object.

        Args:
            project_id: "org/repo" format (e.g. "stoa-platform/stoa-catalog").
        """
        if not self._gh:
            raise RuntimeError("GitHub not connected")
        return self._gh.get_repo(project_id)

    async def get_file_content(self, project_id: str, file_path: str, ref: str = "main") -> str:
        """Retrieve raw file content from GitHub."""
        repo = self._get_repo(project_id)
        try:
            content_file = repo.get_contents(file_path, ref=ref)
            if isinstance(content_file, list):
                raise FileNotFoundError(f"{file_path} is a directory, not a file, in {project_id}")
            return content_file.decoded_content.decode("utf-8")
        except GithubException as exc:
            if exc.status == 404:
                raise FileNotFoundError(f"{file_path} not found in project {project_id}") from exc
            raise

    async def list_files(self, project_id: str, path: str = "", ref: str = "main") -> list[str]:
        """List files in a GitHub repository directory."""
        repo = self._get_repo(project_id)
        try:
            contents = repo.get_contents(path, ref=ref)
            if not isinstance(contents, list):
                contents = [contents]
            return [item.path for item in contents]
        except GithubException as exc:
            if exc.status == 404:
                return []
            raise

    async def create_webhook(
        self,
        project_id: str,
        url: str,
        secret: str,
        events: list[str],
    ) -> dict[str, Any]:
        """Register a webhook on a GitHub repository."""
        repo = self._get_repo(project_id)
        # Map generic event names to GitHub webhook events
        event_map = {
            "push": "push",
            "merge_request": "pull_request",
            "tag": "create",
            "issues": "issues",
        }
        gh_events = [event_map.get(e, e) for e in events]
        hook = repo.create_hook(
            name="web",
            config={"url": url, "secret": secret, "content_type": "json"},
            events=gh_events,
            active=True,
        )
        return {"id": str(hook.id), "url": hook.config["url"]}

    async def delete_webhook(self, project_id: str, hook_id: str) -> bool:
        """Remove a webhook from a GitHub repository."""
        repo = self._get_repo(project_id)
        try:
            hook = repo.get_hook(int(hook_id))
            hook.delete()
            return True
        except GithubException as exc:
            if exc.status == 404:
                return False
            raise

    async def get_repo_info(self, project_id: str) -> dict[str, Any]:
        """Retrieve GitHub repository metadata."""
        repo = self._get_repo(project_id)
        return {
            "name": repo.name,
            "default_branch": repo.default_branch,
            "url": repo.html_url,
            "visibility": "private" if repo.private else "public",
        }
