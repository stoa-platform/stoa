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
from src.services.catalog_git_client.models import RemoteCommit, RemoteFile, RemotePullRequest, RemoteTag


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
    async def test_actor_sanitization_strips_newlines(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        """A malicious actor string with newlines must collapse to a single line.

        The security guarantee is that an attacker controlling ``actor``
        cannot inject a *new line* after our own ``Actor:`` prefix; they
        cannot fabricate what looks like an additional commit-trailer
        header. The substring is preserved (folded) but it stays on the
        same line as the prefix.
        """
        fake_repo.create_file.return_value = {
            "commit": MagicMock(sha="x"),
            "content": MagicMock(sha="y"),
        }
        await client.create_or_update(
            path="tenants/demo/apis/petstore/api.yaml",
            content=b"id: petstore\n",
            expected_sha=None,
            actor="alice\n\nFake-Header: injected\nstill-alice",
            message="create api petstore",
        )
        args, _ = fake_repo.create_file.call_args
        commit_message = args[1]
        # The commit message structure is: subject \n\n Actor: <one line>
        body_lines = commit_message.split("\n\n", 1)[1].splitlines()
        assert len(body_lines) == 1, f"Actor line must be single-line, got: {body_lines!r}"
        actor_line = body_lines[0]
        assert actor_line.startswith("Actor: ")
        # All remnants of the attacker-supplied input are inside the actor line,
        # never on a separate line where they could pose as a fake trailer.
        assert "\n" not in actor_line
        assert "\r" not in actor_line

    @pytest.mark.asyncio
    async def test_actor_sanitization_empty_falls_back(
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
            actor="",
            message="create api petstore",
        )
        args, _ = fake_repo.create_file.call_args
        commit_message = args[1]
        assert "Actor: <unknown>" in commit_message

    @pytest.mark.asyncio
    async def test_branch_is_forwarded_to_contents_api(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        fake_repo.create_file.return_value = {
            "commit": MagicMock(sha="commit-sha-branch"),
            "content": MagicMock(sha="blob-sha-branch"),
        }
        await client.create_or_update(
            path="tenants/demo/apis/petstore/api.yaml",
            content=b"id: petstore\n",
            expected_sha=None,
            actor="alice",
            message="create",
            branch="stoa/api/demo/petstore/v1/hash",
        )
        _, kwargs = fake_repo.create_file.call_args
        assert kwargs["branch"] == "stoa/api/demo/petstore/v1/hash"

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


class TestReleasePrimitives:
    @pytest.mark.asyncio
    async def test_create_branch_from_default_ref(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        base_ref = MagicMock()
        base_ref.object.sha = "base-sha"
        fake_repo.get_git_ref.return_value = base_ref
        branch = MagicMock()
        branch.commit.sha = "branch-head-sha"
        fake_repo.get_branch.return_value = branch

        result = await client.create_branch("stoa/api/acme/petstore/v1/hash")

        fake_repo.create_git_ref.assert_called_once_with("refs/heads/stoa/api/acme/petstore/v1/hash", "base-sha")
        assert result == "branch-head-sha"

    @pytest.mark.asyncio
    async def test_create_pull_request_returns_remote_pr(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        pr = MagicMock()
        pr.number = 12
        pr.html_url = "https://github.com/stoa-platform/stoa-catalog/pull/12"
        pr.state = "open"
        pr.merge_commit_sha = None
        fake_repo.create_pull.return_value = pr

        result = await client.create_pull_request(
            title="catalog release",
            body="body",
            source_branch="stoa/api/acme/petstore/v1/hash",
        )

        fake_repo.create_pull.assert_called_once_with(
            title="catalog release",
            body="body",
            head="stoa/api/acme/petstore/v1/hash",
            base="main",
        )
        assert isinstance(result, RemotePullRequest)
        assert result.number == 12
        assert result.url == "https://github.com/stoa-platform/stoa-catalog/pull/12"

    @pytest.mark.asyncio
    async def test_merge_pull_request_returns_merge_sha(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        pr = MagicMock()
        pr.merged = False
        pr.merge.return_value = MagicMock(sha="merge-sha")
        merged = MagicMock()
        merged.number = 12
        merged.html_url = "https://github.com/stoa-platform/stoa-catalog/pull/12"
        merged.merged = True
        merged.state = "closed"
        merged.merge_commit_sha = "merge-sha"
        merged.head.ref = "source-branch"
        merged.base.ref = "main"
        fake_repo.get_pull.side_effect = [pr, merged]

        result = await client.merge_pull_request(12)

        pr.merge.assert_called_once_with(merge_method="squash")
        assert result.state == "merged"
        assert result.merge_commit_sha == "merge-sha"

    @pytest.mark.asyncio
    async def test_create_tag_creates_annotated_ref(
        self, client: GitHubContentsCatalogClient, fake_repo: MagicMock
    ) -> None:
        fake_repo.get_git_ref.side_effect = GithubException(404, {"message": "Not Found"}, None)
        git_tag = MagicMock()
        git_tag.sha = "tag-object-sha"
        fake_repo.create_git_tag.return_value = git_tag
        ref = MagicMock()
        ref.url = "https://api.github.test/ref"
        fake_repo.create_git_ref.return_value = ref

        result = await client.create_tag(
            name="stoa/api/acme/petstore/v1/merge-sha",
            target_sha="merge-sha",
            message="release",
        )

        fake_repo.create_git_tag.assert_called_once_with(
            tag="stoa/api/acme/petstore/v1/merge-sha",
            message="release",
            object="merge-sha",
            type="commit",
        )
        fake_repo.create_git_ref.assert_called_once_with(
            ref="refs/tags/stoa/api/acme/petstore/v1/merge-sha",
            sha="tag-object-sha",
        )
        assert isinstance(result, RemoteTag)
        assert result.target_sha == "merge-sha"
