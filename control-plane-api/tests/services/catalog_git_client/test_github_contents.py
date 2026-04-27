"""Tests for ``GitHubContentsCatalogClient``.

Spec §6.7 (CAB-2184 B-CLIENT). Mocks PyGithub so no real GitHub call is
issued. Each test asserts both the wire shape (what is called on PyGithub)
and the contract shape (what the client returns).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from github import GithubException

from src.services.catalog_git_client.github_contents import (
    CatalogShaConflictError,
    GitHubContentsCatalogClient,
)
from src.services.catalog_git_client.models import RemoteCommit, RemoteFile


@pytest.fixture
def fake_repo() -> MagicMock:
    return MagicMock(name="repo")


@pytest.fixture
def fake_gh(fake_repo: MagicMock) -> MagicMock:
    gh = MagicMock(name="github")
    gh.get_repo.return_value = fake_repo
    return gh


@pytest.fixture
def fake_github_service(fake_gh: MagicMock) -> MagicMock:
    svc = MagicMock(name="github_service")
    svc._require_gh.return_value = fake_gh
    return svc


@pytest.fixture
def client(fake_github_service: MagicMock) -> GitHubContentsCatalogClient:
    return GitHubContentsCatalogClient(github_service=fake_github_service)


def _make_content_file(*, path: str, content: bytes, sha: str) -> MagicMock:
    cf = MagicMock(name="content_file")
    cf.path = path
    cf.decoded_content = content
    cf.sha = sha
    return cf


class TestGet:
    @pytest.mark.asyncio
    async def test_returns_remote_file_on_200(self, client: GitHubContentsCatalogClient, fake_repo: MagicMock) -> None:
        fake_repo.get_contents.return_value = _make_content_file(
            path="tenants/demo/apis/petstore/api.yaml",
            content=b"id: petstore\nname: petstore\n",
            sha="abc123",
        )
        result = await client.get("tenants/demo/apis/petstore/api.yaml")
        assert isinstance(result, RemoteFile)
        assert result.path == "tenants/demo/apis/petstore/api.yaml"
        assert result.content == b"id: petstore\nname: petstore\n"
        assert result.sha == "abc123"

    @pytest.mark.asyncio
    async def test_returns_none_on_404(self, client: GitHubContentsCatalogClient, fake_repo: MagicMock) -> None:
        fake_repo.get_contents.side_effect = GithubException(404, {"message": "Not Found"}, None)
        result = await client.get("tenants/demo/apis/missing/api.yaml")
        assert result is None

    @pytest.mark.asyncio
    async def test_directory_resolves_to_value_error(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        fake_repo.get_contents.return_value = [MagicMock(), MagicMock()]
        with pytest.raises(ValueError, match="resolves to a directory"):
            await client.get("tenants/demo/apis/petstore")

    @pytest.mark.asyncio
    async def test_other_github_errors_bubble(self, client: GitHubContentsCatalogClient, fake_repo: MagicMock) -> None:
        fake_repo.get_contents.side_effect = GithubException(500, {"message": "boom"}, None)
        with pytest.raises(GithubException):
            await client.get("tenants/demo/apis/petstore/api.yaml")


class TestCreateOrUpdate:
    @pytest.mark.asyncio
    async def test_create_on_absent_sha_calls_create_file(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        fake_repo.create_file.return_value = {
            "commit": MagicMock(sha="commit-sha-1"),
            "content": MagicMock(sha="blob-sha-1"),
        }
        result = await client.create_or_update(
            path="tenants/demo-gitops/apis/petstore/api.yaml",
            content=b"id: petstore\n",
            expected_sha=None,
            actor="user@example.com",
            message="create api petstore",
        )
        fake_repo.create_file.assert_called_once()
        # Update path must NOT be touched on creation
        fake_repo.update_file.assert_not_called()
        assert isinstance(result, RemoteCommit)
        assert result.commit_sha == "commit-sha-1"
        assert result.file_sha == "blob-sha-1"

    @pytest.mark.asyncio
    async def test_update_with_expected_sha_calls_update_file(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        fake_repo.update_file.return_value = {
            "commit": MagicMock(sha="commit-sha-2"),
            "content": MagicMock(sha="blob-sha-2"),
        }
        result = await client.create_or_update(
            path="tenants/demo/apis/petstore/api.yaml",
            content=b"id: petstore\n",
            expected_sha="prior-blob-sha",
            actor="user@example.com",
            message="update api petstore",
        )
        fake_repo.update_file.assert_called_once()
        # Verify the SHA is forwarded as the optimistic-CAS guard
        args, _kwargs = fake_repo.update_file.call_args
        assert "prior-blob-sha" in args
        assert result.commit_sha == "commit-sha-2"
        assert result.file_sha == "blob-sha-2"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [409, 422])
    async def test_sha_mismatch_raises_conflict(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock, status_code: int
    ) -> None:
        fake_repo.update_file.side_effect = GithubException(status_code, {"message": "sha conflict"}, None)
        with pytest.raises(CatalogShaConflictError) as excinfo:
            await client.create_or_update(
                path="tenants/demo/apis/petstore/api.yaml",
                content=b"id: petstore\n",
                expected_sha="stale-sha",
                actor="user",
                message="update",
            )
        assert excinfo.value.path == "tenants/demo/apis/petstore/api.yaml"
        assert excinfo.value.expected_sha == "stale-sha"
        assert excinfo.value.status == status_code

    @pytest.mark.asyncio
    async def test_actor_appended_to_commit_message(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        fake_repo.create_file.return_value = {
            "commit": MagicMock(sha="x"),
            "content": MagicMock(sha="y"),
        }
        await client.create_or_update(
            path="tenants/demo/apis/petstore/api.yaml",
            content=b"id: petstore\n",
            expected_sha=None,
            actor="alice@stoa",
            message="create api petstore",
        )
        args, _ = fake_repo.create_file.call_args
        # args[1] is commit message in PyGithub create_file signature
        commit_message = args[1]
        assert "create api petstore" in commit_message
        assert "alice@stoa" in commit_message

    @pytest.mark.asyncio
    async def test_other_errors_bubble(self, client: GitHubContentsCatalogClient, fake_repo: MagicMock) -> None:
        fake_repo.create_file.side_effect = GithubException(500, {"message": "boom"}, None)
        with pytest.raises(GithubException):
            await client.create_or_update(
                path="tenants/demo/apis/petstore/api.yaml",
                content=b"id: petstore\n",
                expected_sha=None,
                actor="user",
                message="create",
            )


class TestReadAtCommit:
    @pytest.mark.asyncio
    async def test_returns_bytes_for_known_commit(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        fake_repo.get_contents.return_value = _make_content_file(
            path="tenants/demo/apis/petstore/api.yaml",
            content=b"version: 1.0.0\n",
            sha="blob-x",
        )
        result = await client.read_at_commit("tenants/demo/apis/petstore/api.yaml", "commit-abc")
        assert result == b"version: 1.0.0\n"
        # Confirm the ref was the commit SHA, not a branch name
        _, kwargs = fake_repo.get_contents.call_args
        assert kwargs.get("ref") == "commit-abc"

    @pytest.mark.asyncio
    async def test_returns_none_on_404(self, client: GitHubContentsCatalogClient, fake_repo: MagicMock) -> None:
        fake_repo.get_contents.side_effect = GithubException(404, {"message": "Not Found"}, None)
        result = await client.read_at_commit("tenants/demo/apis/petstore/api.yaml", "deadbeef")
        assert result is None


class TestLatestFileCommit:
    @pytest.mark.asyncio
    async def test_returns_first_commit_sha(self, client: GitHubContentsCatalogClient, fake_repo: MagicMock) -> None:
        commit1 = MagicMock(sha="newest")
        commit2 = MagicMock(sha="older")
        fake_repo.get_commits.return_value = iter([commit1, commit2])
        result = await client.latest_file_commit("tenants/demo/apis/petstore/api.yaml")
        assert result == "newest"

    @pytest.mark.asyncio
    async def test_raises_filenotfound_on_empty_history(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        fake_repo.get_commits.return_value = iter([])
        with pytest.raises(FileNotFoundError, match="no commits touch"):
            await client.latest_file_commit("tenants/demo/apis/missing/api.yaml")


class TestList:
    @pytest.mark.asyncio
    async def test_lists_paths_matching_reconciler_glob(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        ref = MagicMock(name="ref")
        ref.object.sha = "head-sha"
        fake_repo.get_git_ref.return_value = ref
        tree = MagicMock(name="tree")
        tree.tree = [
            MagicMock(type="blob", path="tenants/demo/apis/petstore/api.yaml"),
            MagicMock(type="blob", path="tenants/demo/apis/petstore/uac.json"),
            MagicMock(type="blob", path="tenants/demo/apis/payment-api/api.yaml"),
            MagicMock(type="tree", path="tenants/demo/apis/petstore"),
            MagicMock(type="blob", path="tenants/demo/tenant.yaml"),
        ]
        fake_repo.get_git_tree.return_value = tree
        result = await client.list("tenants/*/apis/*/api.yaml")
        assert sorted(result) == [
            "tenants/demo/apis/payment-api/api.yaml",
            "tenants/demo/apis/petstore/api.yaml",
        ]

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_missing_ref(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        fake_repo.get_git_ref.side_effect = GithubException(404, {"message": "Not Found"}, None)
        result = await client.list("tenants/*/apis/*/api.yaml")
        assert result == []
