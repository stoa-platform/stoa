"""Tests for GitHubService (CAB-1890 Wave 2, CAB-2011 write methods)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from github import GithubException

from src.services.github_service import GitHubService

# Catalog project ID used by high-level methods
CATALOG_PROJECT = "stoa-platform/stoa-catalog"


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
        """CP-1 C.2: token must NOT be in argv (GIT_ASKPASS handles auth)."""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"", b"")

        repo_url = "https://github.com/stoa-platform/stoa-catalog.git"
        with patch("src.services.github_service.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            result = await service.clone_repo(repo_url)

            assert isinstance(result, Path)
            args = mock_exec.call_args[0]
            env = mock_exec.call_args[1].get("env", {})
            assert args[0] == "git"
            assert args[1] == "clone"
            assert "--depth=1" in args
            # URL is passed verbatim — no token injection.
            assert repo_url in args
            # Token travels via env, not argv.
            assert "x-access-token:" not in " ".join(str(a) for a in args)
            assert env.get("GIT_ASKPASS")
            assert env.get("STOA_GIT_USERNAME") == "x-access-token"

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


# ============================================================
# Write operations tests (CAB-2011)
# ============================================================


class TestCreateFile:
    @pytest.mark.asyncio
    async def test_create_file_success(self, service, mock_repo):
        mock_commit = MagicMock()
        mock_commit.sha = "abc123"
        mock_commit.html_url = "https://github.com/org/repo/commit/abc123"
        mock_repo.create_file.return_value = {"commit": mock_commit}
        service._gh.get_repo.return_value = mock_repo

        result = await service.create_file("org/repo", "new.yaml", "content", "add file")

        assert result["sha"] == "abc123"
        mock_repo.create_file.assert_called_once_with("new.yaml", "add file", "content", branch="main")

    @pytest.mark.asyncio
    async def test_create_file_already_exists(self, service, mock_repo):
        mock_repo.create_file.side_effect = GithubException(422, {"message": "sha"}, {})
        service._gh.get_repo.return_value = mock_repo

        with pytest.raises(ValueError, match="already exists"):
            await service.create_file("org/repo", "exists.yaml", "content", "add")


class TestUpdateFile:
    @pytest.mark.asyncio
    async def test_update_file_success(self, service, mock_repo):
        existing = MagicMock()
        existing.sha = "old_sha"
        mock_repo.get_contents.return_value = existing
        mock_commit = MagicMock()
        mock_commit.sha = "new_sha"
        mock_commit.html_url = "https://github.com/org/repo/commit/new_sha"
        mock_repo.update_file.return_value = {"commit": mock_commit}
        service._gh.get_repo.return_value = mock_repo

        result = await service.update_file("org/repo", "file.yaml", "new content", "update")

        assert result["sha"] == "new_sha"
        mock_repo.update_file.assert_called_once_with("file.yaml", "update", "new content", "old_sha", branch="main")

    @pytest.mark.asyncio
    async def test_update_file_not_found(self, service, mock_repo):
        mock_repo.get_contents.side_effect = GithubException(404, {"message": "Not Found"}, {})
        service._gh.get_repo.return_value = mock_repo

        with pytest.raises(FileNotFoundError):
            await service.update_file("org/repo", "missing.yaml", "content", "update")


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_delete_file_success(self, service, mock_repo):
        existing = MagicMock()
        existing.sha = "file_sha"
        mock_repo.get_contents.return_value = existing
        service._gh.get_repo.return_value = mock_repo

        result = await service.delete_file("org/repo", "old.yaml", "remove file")

        assert result is True
        mock_repo.delete_file.assert_called_once_with("old.yaml", "remove file", "file_sha", branch="main")

    @pytest.mark.asyncio
    async def test_delete_file_not_found(self, service, mock_repo):
        mock_repo.get_contents.side_effect = GithubException(404, {"message": "Not Found"}, {})
        service._gh.get_repo.return_value = mock_repo

        with pytest.raises(FileNotFoundError):
            await service.delete_file("org/repo", "missing.yaml", "remove")


class TestBatchCommit:
    @pytest.mark.asyncio
    async def test_batch_commit_create_and_delete(self, service, mock_repo):
        # Setup ref chain
        mock_ref = MagicMock()
        mock_ref.object.sha = "base_sha"
        mock_repo.get_git_ref.return_value = mock_ref

        mock_base_tree = MagicMock()
        mock_repo.get_git_tree.return_value = mock_base_tree

        mock_new_tree = MagicMock()
        mock_repo.create_git_tree.return_value = mock_new_tree

        mock_new_commit = MagicMock()
        mock_new_commit.sha = "new_commit_sha"
        mock_new_commit.html_url = "https://github.com/org/repo/commit/new_commit_sha"
        mock_repo.create_git_commit.return_value = mock_new_commit

        mock_base_commit = MagicMock()
        mock_repo.get_git_commit.return_value = mock_base_commit

        service._gh.get_repo.return_value = mock_repo

        actions = [
            {"action": "create", "file_path": "new.txt", "content": "hello"},
            {"action": "delete", "file_path": "old.txt"},
        ]
        result = await service.batch_commit("org/repo", actions, "batch op")

        assert result["sha"] == "new_commit_sha"
        mock_repo.create_git_tree.assert_called_once()
        mock_ref.edit.assert_called_once_with("new_commit_sha")

    @pytest.mark.asyncio
    async def test_batch_commit_empty_actions_raises(self, service, mock_repo):
        service._gh.get_repo.return_value = mock_repo
        mock_ref = MagicMock()
        mock_ref.object.sha = "sha"
        mock_repo.get_git_ref.return_value = mock_ref
        mock_repo.get_git_tree.return_value = MagicMock()

        with pytest.raises(ValueError, match="No actions"):
            await service.batch_commit("org/repo", [], "empty")

    @pytest.mark.asyncio
    async def test_batch_commit_unknown_action_raises(self, service, mock_repo):
        service._gh.get_repo.return_value = mock_repo
        mock_ref = MagicMock()
        mock_ref.object.sha = "sha"
        mock_repo.get_git_ref.return_value = mock_ref
        mock_repo.get_git_tree.return_value = MagicMock()

        with pytest.raises(ValueError, match="Unknown action"):
            await service.batch_commit("org/repo", [{"action": "rename", "file_path": "f"}], "bad")


class TestCreateTenantStructure:
    @pytest.mark.asyncio
    @patch.object(GitHubService, "batch_commit", new_callable=AsyncMock)
    async def test_create_tenant(self, mock_batch, service):
        result = await service.create_tenant_structure("acme", {"name": "Acme Corp"})

        assert result is True
        mock_batch.assert_called_once()
        args = mock_batch.call_args
        actions = args[1]["actions"] if "actions" in args[1] else args[0][1]
        paths = [a["file_path"] for a in actions]
        assert "tenants/acme/tenant.yaml" in paths
        assert "tenants/acme/apis/.gitkeep" in paths
        assert "tenants/acme/applications/.gitkeep" in paths


class TestCreateApi:
    @pytest.mark.asyncio
    @patch.object(GitHubService, "batch_commit", new_callable=AsyncMock)
    @patch.object(GitHubService, "_file_exists", new_callable=AsyncMock)
    @patch.object(GitHubService, "_ensure_tenant_exists", new_callable=AsyncMock)
    async def test_create_api_success(self, mock_tenant, mock_exists, mock_batch, service):
        mock_exists.return_value = False
        mock_batch.return_value = {"sha": "abc", "url": ""}

        api_data = {
            "name": "billing-api",
            "display_name": "Billing API",
            "version": "1.0.0",
            "description": "Billing service",
            "backend_url": "https://billing.internal",
        }
        result = await service.create_api("acme", api_data)

        assert result == "billing-api"
        mock_batch.assert_called_once()
        actions = mock_batch.call_args[1]["actions"]
        paths = [a["file_path"] for a in actions]
        assert "tenants/acme/apis/billing-api/api.yaml" in paths
        assert "tenants/acme/apis/billing-api/uac.json" in paths
        assert "tenants/acme/apis/billing-api/policies/.gitkeep" in paths

    @pytest.mark.asyncio
    @patch.object(GitHubService, "_file_exists", new_callable=AsyncMock)
    @patch.object(GitHubService, "_ensure_tenant_exists", new_callable=AsyncMock)
    async def test_create_api_already_exists(self, mock_tenant, mock_exists, service):
        mock_exists.return_value = True

        with pytest.raises(ValueError, match="already exists"):
            await service.create_api("acme", {"name": "billing-api"})

    @pytest.mark.asyncio
    @patch.object(GitHubService, "batch_commit", new_callable=AsyncMock)
    @patch.object(GitHubService, "_file_exists", new_callable=AsyncMock)
    @patch.object(GitHubService, "_ensure_tenant_exists", new_callable=AsyncMock)
    async def test_create_api_with_openapi_spec(self, mock_tenant, mock_exists, mock_batch, service):
        mock_exists.return_value = False
        mock_batch.return_value = {"sha": "abc", "url": ""}

        api_data = {
            "id": "pet-api",
            "name": "pet-api",
            "display_name": "Pet API",
            "backend_url": "https://pets.example.com",
            "openapi_spec": {
                "openapi": "3.0.0",
                "info": {"title": "Pets", "version": "1.0.0"},
                "paths": {"/pets": {"get": {"operationId": "listPets", "responses": {"200": {"description": "ok"}}}}},
            },
        }
        await service.create_api("demo", api_data)

        actions = mock_batch.call_args[1]["actions"]
        paths = {a["file_path"]: a["content"] for a in actions}
        assert "tenants/demo/apis/pet-api/openapi.yaml" in paths
        uac = json.loads(paths["tenants/demo/apis/pet-api/uac.json"])
        assert uac["name"] == "pet-api"
        assert uac["endpoints"][0]["backend_url"] == "https://pets.example.com/pets"


class TestUpdateApi:
    @pytest.mark.asyncio
    @patch.object(GitHubService, "batch_commit", new_callable=AsyncMock)
    @patch.object(GitHubService, "_file_exists", new_callable=AsyncMock)
    @patch.object(GitHubService, "get_file_content", new_callable=AsyncMock)
    async def test_update_api_success(self, mock_get, mock_exists, mock_batch, service):
        mock_get.return_value = "name: billing-api\nversion: 1.0.0\n"
        mock_exists.return_value = True
        mock_batch.return_value = {"sha": "new", "url": ""}

        result = await service.update_api("acme", "billing-api", {"version": "2.0.0"})

        assert result is True
        mock_batch.assert_called_once()
        actions = mock_batch.call_args[1]["actions"]
        assert any(a["file_path"].endswith("/api.yaml") and "2.0.0" in a["content"] for a in actions)
        assert any(a["file_path"].endswith("/uac.json") for a in actions)

    @pytest.mark.asyncio
    @patch.object(GitHubService, "get_file_content", new_callable=AsyncMock)
    async def test_update_api_not_found(self, mock_get, service):
        mock_get.side_effect = FileNotFoundError("not found")

        with pytest.raises(FileNotFoundError):
            await service.update_api("acme", "missing-api", {"version": "2.0.0"})


class TestDeleteApi:
    @pytest.mark.asyncio
    @patch.object(GitHubService, "batch_commit", new_callable=AsyncMock)
    async def test_delete_api_success(self, mock_batch, service, mock_repo):
        # Mock directory listing
        file1 = MagicMock()
        file1.type = "file"
        file1.path = "tenants/acme/apis/billing-api/api.yaml"
        file2 = MagicMock()
        file2.type = "file"
        file2.path = "tenants/acme/apis/billing-api/policies/.gitkeep"
        mock_repo.get_contents.return_value = [file1, file2]
        service._gh.get_repo.return_value = mock_repo

        result = await service.delete_api("acme", "billing-api")

        assert result is True
        actions = mock_batch.call_args[1]["actions"]
        assert len(actions) == 2
        assert all(a["action"] == "delete" for a in actions)

    @pytest.mark.asyncio
    async def test_delete_api_not_found(self, service, mock_repo):
        mock_repo.get_contents.side_effect = GithubException(404, {"message": "Not Found"}, {})
        service._gh.get_repo.return_value = mock_repo

        with pytest.raises(FileNotFoundError):
            await service.delete_api("acme", "missing-api")


class TestCreateMcpServer:
    @pytest.mark.asyncio
    @patch.object(GitHubService, "batch_commit", new_callable=AsyncMock)
    @patch.object(GitHubService, "_file_exists", new_callable=AsyncMock)
    async def test_create_mcp_server(self, mock_exists, mock_batch, service):
        mock_exists.return_value = False
        mock_batch.return_value = {"sha": "abc", "url": ""}

        result = await service.create_mcp_server("acme", {"name": "weather-server", "description": "Weather data"})

        assert result == "weather-server"
        actions = mock_batch.call_args[1]["actions"]
        assert actions[0]["file_path"] == "tenants/acme/mcp-servers/weather-server/server.yaml"

    @pytest.mark.asyncio
    @patch.object(GitHubService, "_file_exists", new_callable=AsyncMock)
    async def test_create_mcp_server_already_exists(self, mock_exists, service):
        mock_exists.return_value = True

        with pytest.raises(ValueError, match="already exists"):
            await service.create_mcp_server("acme", {"name": "weather-server"})

    @pytest.mark.asyncio
    @patch.object(GitHubService, "batch_commit", new_callable=AsyncMock)
    @patch.object(GitHubService, "_file_exists", new_callable=AsyncMock)
    async def test_create_platform_mcp_server(self, mock_exists, mock_batch, service):
        mock_exists.return_value = False
        mock_batch.return_value = {"sha": "abc", "url": ""}

        await service.create_mcp_server("_platform", {"name": "global-tools"})

        actions = mock_batch.call_args[1]["actions"]
        assert actions[0]["file_path"] == "platform/mcp-servers/global-tools/server.yaml"


class TestUpdateMcpServer:
    @pytest.mark.asyncio
    @patch.object(GitHubService, "update_file", new_callable=AsyncMock)
    @patch.object(GitHubService, "get_file_content", new_callable=AsyncMock)
    async def test_update_mcp_server(self, mock_get, mock_update, service):
        mock_get.return_value = "apiVersion: gostoa.dev/v1\nkind: MCPServer\nspec:\n  description: old\n"
        mock_update.return_value = {"sha": "new", "url": ""}

        result = await service.update_mcp_server("acme", "weather", {"description": "new desc"})

        assert result is True


class TestDeleteMcpServer:
    @pytest.mark.asyncio
    @patch.object(GitHubService, "batch_commit", new_callable=AsyncMock)
    async def test_delete_mcp_server(self, mock_batch, service, mock_repo):
        file1 = MagicMock()
        file1.type = "file"
        file1.path = "tenants/acme/mcp-servers/weather/server.yaml"
        mock_repo.get_contents.return_value = [file1]
        service._gh.get_repo.return_value = mock_repo

        result = await service.delete_mcp_server("acme", "weather")

        assert result is True
        actions = mock_batch.call_args[1]["actions"]
        assert actions[0]["action"] == "delete"
