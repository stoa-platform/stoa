"""Tests for GitHubService (CAB-1890 Wave 2)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from github import GithubException

from src.services.github_service import GitHubService


@pytest.fixture
def service():
    """Create a GitHubService with a mocked PyGithub client."""
    svc = GitHubService()
    svc._gh = MagicMock()
    return svc


@pytest.fixture
def mock_repo():
    """Create a mock PyGithub Repository."""
    repo = MagicMock()
    repo.name = "stoa-catalog"
    repo.default_branch = "main"
    repo.html_url = "https://github.com/stoa-platform/stoa-catalog"
    repo.private = False
    return repo


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_success(self):
        svc = GitHubService()
        with (
            patch("src.services.github_service.Github") as mock_gh_cls,
            patch("src.services.github_service.Auth") as mock_auth,
        ):
            mock_gh = MagicMock()
            mock_user = MagicMock()
            mock_user.login = "stoa-bot"
            mock_gh.get_user.return_value = mock_user
            mock_gh_cls.return_value = mock_gh

            await svc.connect()

            mock_auth.Token.assert_called_once()
            assert svc._gh is mock_gh

    @pytest.mark.asyncio
    async def test_connect_failure_raises(self):
        svc = GitHubService()
        with patch("src.services.github_service.Github") as mock_gh_cls, patch("src.services.github_service.Auth"):
            mock_gh = MagicMock()
            mock_gh.get_user.side_effect = Exception("Bad credentials")
            mock_gh_cls.return_value = mock_gh

            with pytest.raises(Exception, match="Bad credentials"):
                await svc.connect()


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_closes_client(self, service):
        gh_mock = service._gh
        await service.disconnect()
        gh_mock.close.assert_called_once()
        assert service._gh is None

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        svc = GitHubService()
        await svc.disconnect()
        assert svc._gh is None


class TestCloneRepo:
    @pytest.mark.asyncio
    async def test_clone_repo_success(self, service):
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")

        with patch("src.services.github_service.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await service.clone_repo("https://github.com/stoa-platform/stoa-catalog.git")

            assert isinstance(result, Path)
            args = mock_exec.call_args[0]
            assert args[0] == "git"
            assert args[1] == "clone"
            assert "--depth=1" in args
            # Token injected into URL
            assert "x-access-token:" in args[3]

    @pytest.mark.asyncio
    async def test_clone_repo_failure_raises(self, service):
        mock_proc = AsyncMock()
        mock_proc.returncode = 128
        mock_proc.communicate.return_value = (b"", b"fatal: repository not found")

        with (
            patch("src.services.github_service.asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(RuntimeError, match="git clone failed"),
        ):
            await service.clone_repo("https://github.com/stoa-platform/nonexistent.git")


class TestGetFileContent:
    @pytest.mark.asyncio
    async def test_get_file_content_success(self, service, mock_repo):
        content_file = MagicMock()
        content_file.decoded_content = b"hello: world"
        mock_repo.get_contents.return_value = content_file
        service._gh.get_repo.return_value = mock_repo

        result = await service.get_file_content("stoa-platform/stoa-catalog", "config.yaml")

        assert result == "hello: world"
        mock_repo.get_contents.assert_called_once_with("config.yaml", ref="main")

    @pytest.mark.asyncio
    async def test_get_file_content_custom_ref(self, service, mock_repo):
        content_file = MagicMock()
        content_file.decoded_content = b"data"
        mock_repo.get_contents.return_value = content_file
        service._gh.get_repo.return_value = mock_repo

        await service.get_file_content("stoa-platform/stoa-catalog", "f.txt", ref="develop")

        mock_repo.get_contents.assert_called_once_with("f.txt", ref="develop")

    @pytest.mark.asyncio
    async def test_get_file_content_not_found(self, service, mock_repo):
        mock_repo.get_contents.side_effect = GithubException(404, {"message": "Not Found"}, {})
        service._gh.get_repo.return_value = mock_repo

        with pytest.raises(FileNotFoundError, match="not found"):
            await service.get_file_content("stoa-platform/stoa-catalog", "missing.yaml")

    @pytest.mark.asyncio
    async def test_get_file_content_directory_raises(self, service, mock_repo):
        mock_repo.get_contents.return_value = [MagicMock(), MagicMock()]
        service._gh.get_repo.return_value = mock_repo

        with pytest.raises(FileNotFoundError, match="directory"):
            await service.get_file_content("stoa-platform/stoa-catalog", "src/")

    @pytest.mark.asyncio
    async def test_get_file_content_not_connected(self):
        svc = GitHubService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_file_content("org/repo", "file.txt")


class TestListFiles:
    @pytest.mark.asyncio
    async def test_list_files_success(self, service, mock_repo):
        item1 = MagicMock()
        item1.path = "README.md"
        item2 = MagicMock()
        item2.path = "src/main.py"
        mock_repo.get_contents.return_value = [item1, item2]
        service._gh.get_repo.return_value = mock_repo

        result = await service.list_files("stoa-platform/stoa-catalog")

        assert result == ["README.md", "src/main.py"]
        mock_repo.get_contents.assert_called_once_with("", ref="main")

    @pytest.mark.asyncio
    async def test_list_files_with_path(self, service, mock_repo):
        item = MagicMock()
        item.path = "src/config.py"
        mock_repo.get_contents.return_value = [item]
        service._gh.get_repo.return_value = mock_repo

        result = await service.list_files("stoa-platform/stoa-catalog", path="src", ref="develop")

        assert result == ["src/config.py"]
        mock_repo.get_contents.assert_called_once_with("src", ref="develop")

    @pytest.mark.asyncio
    async def test_list_files_single_file(self, service, mock_repo):
        """When get_contents returns a single ContentFile (not a list)."""
        item = MagicMock()
        item.path = "README.md"
        mock_repo.get_contents.return_value = item  # Not a list
        service._gh.get_repo.return_value = mock_repo

        result = await service.list_files("stoa-platform/stoa-catalog")

        assert result == ["README.md"]

    @pytest.mark.asyncio
    async def test_list_files_not_found_returns_empty(self, service, mock_repo):
        mock_repo.get_contents.side_effect = GithubException(404, {"message": "Not Found"}, {})
        service._gh.get_repo.return_value = mock_repo

        result = await service.list_files("stoa-platform/stoa-catalog", path="nonexistent/")

        assert result == []


class TestCreateWebhook:
    @pytest.mark.asyncio
    async def test_create_webhook_success(self, service, mock_repo):
        mock_hook = MagicMock()
        mock_hook.id = 12345
        mock_hook.config = {"url": "https://example.com/hook"}
        mock_repo.create_hook.return_value = mock_hook
        service._gh.get_repo.return_value = mock_repo

        result = await service.create_webhook(
            "stoa-platform/stoa-catalog",
            "https://example.com/hook",
            "secret123",
            ["push", "merge_request"],
        )

        assert result == {"id": "12345", "url": "https://example.com/hook"}
        mock_repo.create_hook.assert_called_once_with(
            name="web",
            config={"url": "https://example.com/hook", "secret": "secret123", "content_type": "json"},
            events=["push", "pull_request"],
            active=True,
        )

    @pytest.mark.asyncio
    async def test_create_webhook_event_mapping(self, service, mock_repo):
        """Verify generic event names are mapped to GitHub events."""
        mock_hook = MagicMock()
        mock_hook.id = 1
        mock_hook.config = {"url": "https://x.com"}
        mock_repo.create_hook.return_value = mock_hook
        service._gh.get_repo.return_value = mock_repo

        await service.create_webhook("org/repo", "https://x.com", "s", ["push", "tag", "issues"])

        _, kwargs = mock_repo.create_hook.call_args
        assert kwargs["events"] == ["push", "create", "issues"]

    @pytest.mark.asyncio
    async def test_create_webhook_unknown_event_passthrough(self, service, mock_repo):
        """Unknown events are passed through unchanged."""
        mock_hook = MagicMock()
        mock_hook.id = 1
        mock_hook.config = {"url": "https://x.com"}
        mock_repo.create_hook.return_value = mock_hook
        service._gh.get_repo.return_value = mock_repo

        await service.create_webhook("org/repo", "https://x.com", "s", ["deployment"])

        _, kwargs = mock_repo.create_hook.call_args
        assert kwargs["events"] == ["deployment"]


class TestDeleteWebhook:
    @pytest.mark.asyncio
    async def test_delete_webhook_success(self, service, mock_repo):
        mock_hook = MagicMock()
        mock_repo.get_hook.return_value = mock_hook
        service._gh.get_repo.return_value = mock_repo

        result = await service.delete_webhook("stoa-platform/stoa-catalog", "12345")

        assert result is True
        mock_repo.get_hook.assert_called_once_with(12345)
        mock_hook.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_webhook_not_found(self, service, mock_repo):
        mock_repo.get_hook.side_effect = GithubException(404, {"message": "Not Found"}, {})
        service._gh.get_repo.return_value = mock_repo

        result = await service.delete_webhook("stoa-platform/stoa-catalog", "99999")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_webhook_other_error_raises(self, service, mock_repo):
        mock_repo.get_hook.side_effect = GithubException(500, {"message": "Server Error"}, {})
        service._gh.get_repo.return_value = mock_repo

        with pytest.raises(GithubException):
            await service.delete_webhook("stoa-platform/stoa-catalog", "12345")


class TestGetRepoInfo:
    @pytest.mark.asyncio
    async def test_get_repo_info_public(self, service, mock_repo):
        service._gh.get_repo.return_value = mock_repo

        result = await service.get_repo_info("stoa-platform/stoa-catalog")

        assert result == {
            "name": "stoa-catalog",
            "default_branch": "main",
            "url": "https://github.com/stoa-platform/stoa-catalog",
            "visibility": "public",
        }

    @pytest.mark.asyncio
    async def test_get_repo_info_private(self, service, mock_repo):
        mock_repo.private = True
        service._gh.get_repo.return_value = mock_repo

        result = await service.get_repo_info("stoa-platform/stoa-catalog")

        assert result["visibility"] == "private"

    @pytest.mark.asyncio
    async def test_get_repo_info_not_connected(self):
        svc = GitHubService()
        with pytest.raises(RuntimeError, match="not connected"):
            await svc.get_repo_info("org/repo")
