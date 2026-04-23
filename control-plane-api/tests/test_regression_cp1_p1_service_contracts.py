"""Regression guards for CP-1 P1 — service-layer contract hardening.

Closes:
- H.2 (deployment_orchestration swallow real failures via suppress(Exception))
- H.6 (list_tree returns file-as-blob singleton on GitHub, breaks ABC contract)

These tests pin:
- GitHubService.list_tree MUST return [] when the path points at a file,
  matching the "enumerate children" contract implemented by GitLabService.
- DeploymentOrchestrationService._sync_api_from_git catches ONLY
  FileNotFoundError. Transient provider failures (TimeoutError, rate-limit,
  auth) MUST propagate past the narrow except, ensuring _upsert_api is NOT
  called with silently-None inputs derived from a real failure.

regression for CP-1 H.2
regression for CP-1 H.6
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.github_service import GitHubService

# ──────────────────────────────────────────────────────────────────
# H.6 — list_tree contract parity across providers
# ──────────────────────────────────────────────────────────────────


def _make_github_service() -> GitHubService:
    svc = GitHubService()
    svc._gh = MagicMock()
    return svc


class TestListTreeContractParity:
    """GitHubService.list_tree must return [] for file paths (no children)."""

    @pytest.mark.asyncio
    async def test_github_list_tree_returns_empty_on_file_path(self):
        """When repo.get_contents returns a single ContentFile, list_tree must
        return [] — NOT a singleton [blob]. The abstract contract is
        "enumerate children"; a file has none.

        regression for CP-1 H.6
        """
        svc = _make_github_service()

        # Single ContentFile (what GitHub returns for a file path).
        single_file = MagicMock()
        single_file.name = "api.yaml"
        single_file.type = "file"
        single_file.path = "tenants/acme/apis/foo/api.yaml"

        repo = MagicMock()
        # get_contents for a FILE path returns the object itself (not a list).
        repo.get_contents.return_value = single_file
        svc._gh.get_repo.return_value = repo

        result = await svc.list_tree("tenants/acme/apis/foo/api.yaml")

        assert result == [], (
            f"GitHub list_tree on file path must return [] (no children), "
            f"got {result}"
        )

    @pytest.mark.asyncio
    async def test_github_list_tree_returns_entries_for_directory(self):
        """Happy path: directory still returns a proper enumeration.

        regression for CP-1 H.6
        """
        svc = _make_github_service()

        file_a = MagicMock()
        file_a.name = "a.yaml"
        file_a.type = "file"
        file_a.path = "tenants/acme/a.yaml"

        dir_b = MagicMock()
        dir_b.name = "subdir"
        dir_b.type = "dir"
        dir_b.path = "tenants/acme/subdir"

        repo = MagicMock()
        repo.get_contents.return_value = [file_a, dir_b]
        svc._gh.get_repo.return_value = repo

        result = await svc.list_tree("tenants/acme")

        assert len(result) == 2
        assert {e.name for e in result} == {"a.yaml", "subdir"}
        # Directory → "tree", file → "blob" (provider-agnostic TreeEntry type).
        by_name = {e.name: e.type for e in result}
        assert by_name["a.yaml"] == "blob"
        assert by_name["subdir"] == "tree"

    @pytest.mark.asyncio
    async def test_github_list_tree_returns_empty_on_404(self):
        """Path that does not exist → [] (pre-existing behaviour, pinned).

        regression for CP-1 H.6
        """
        from github import GithubException

        svc = _make_github_service()
        repo = MagicMock()
        repo.get_contents.side_effect = GithubException(status=404, data={}, headers={})
        svc._gh.get_repo.return_value = repo

        result = await svc.list_tree("tenants/nope")

        assert result == []


# ──────────────────────────────────────────────────────────────────
# H.2 — deployment_orchestration suppress(Exception) → narrow catch
# ──────────────────────────────────────────────────────────────────


class TestDeploymentOrchestrationNarrowCatch:
    """_sync_api_from_git must only swallow FileNotFoundError (expected-None).

    Any transient provider failure (TimeoutError, rate-limit, auth error)
    MUST NOT be swallowed silently at the data-gathering step. The prior
    behaviour called _upsert_api with openapi_spec=None / commit_sha=None
    derived from a real failure, persisting a corrupt catalog row.
    """

    @pytest.mark.asyncio
    async def test_missing_openapi_spec_proceeds_with_none(self):
        """FileNotFoundError on openapi spec → upsert still called with None.

        regression for CP-1 H.2
        """
        from src.services.deployment_orchestration_service import (
            DeploymentOrchestrationService,
        )

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: MagicMock()))
        mock_db.commit = AsyncMock()
        svc = DeploymentOrchestrationService(mock_db)

        mock_git = MagicMock()
        mock_git.is_connected.return_value = True
        mock_git.connect = AsyncMock()
        mock_git.get_api = AsyncMock(return_value={"name": "foo"})
        # FileNotFoundError = expected "no spec" outcome.
        mock_git.get_api_openapi_spec = AsyncMock(side_effect=FileNotFoundError("no spec"))
        mock_git.get_head_commit_sha = AsyncMock(return_value="abc123")

        mock_sync = MagicMock()
        mock_sync._upsert_api = AsyncMock()

        with (
            patch("src.services.git_service.git_service", mock_git),
            patch(
                "src.services.catalog_sync_service.CatalogSyncService",
                return_value=mock_sync,
            ),
        ):
            await svc._sync_api_from_git("acme", "foo")

        # upsert MUST have been called with openapi_spec=None (expected).
        mock_sync._upsert_api.assert_awaited_once()
        call_args = mock_sync._upsert_api.await_args
        # Positional args: tenant_id, api_id, api_data, openapi_spec, commit_sha
        assert call_args.args[3] is None, "openapi_spec should be None on FileNotFoundError"

    @pytest.mark.asyncio
    async def test_timeout_on_openapi_short_circuits_upsert(self):
        """TimeoutError on openapi fetch → _upsert_api is NOT called with a
        silently-None spec. The transient failure reaches the outer except,
        which logs + returns None, leaving the catalog untouched.

        regression for CP-1 H.2
        """
        from src.services.deployment_orchestration_service import (
            DeploymentOrchestrationService,
        )

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        svc = DeploymentOrchestrationService(mock_db)

        mock_git = MagicMock()
        mock_git.is_connected.return_value = True
        mock_git.connect = AsyncMock()
        mock_git.get_api = AsyncMock(return_value={"name": "foo"})
        # TimeoutError = transient provider failure, MUST propagate.
        mock_git.get_api_openapi_spec = AsyncMock(side_effect=TimeoutError("upstream slow"))
        mock_git.get_head_commit_sha = AsyncMock(return_value="abc123")

        mock_sync = MagicMock()
        mock_sync._upsert_api = AsyncMock()

        with (
            patch("src.services.git_service.git_service", mock_git),
            patch(
                "src.services.catalog_sync_service.CatalogSyncService",
                return_value=mock_sync,
            ),
        ):
            result = await svc._sync_api_from_git("acme", "foo")

        # Outer `except Exception: return None` kicks in → caller sees None.
        assert result is None
        # BUT _upsert_api MUST NOT have been called — no corrupt row written.
        mock_sync._upsert_api.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_timeout_on_head_commit_short_circuits_upsert(self):
        """Same contract for the head commit fetch: transient failure
        must not be silently swallowed into commit_sha=None.

        regression for CP-1 H.2
        """
        from src.services.deployment_orchestration_service import (
            DeploymentOrchestrationService,
        )

        mock_db = MagicMock()
        mock_db.execute = AsyncMock()
        mock_db.commit = AsyncMock()
        svc = DeploymentOrchestrationService(mock_db)

        mock_git = MagicMock()
        mock_git.is_connected.return_value = True
        mock_git.connect = AsyncMock()
        mock_git.get_api = AsyncMock(return_value={"name": "foo"})
        mock_git.get_api_openapi_spec = AsyncMock(return_value={"openapi": "3.0"})
        mock_git.get_head_commit_sha = AsyncMock(side_effect=TimeoutError("upstream slow"))

        mock_sync = MagicMock()
        mock_sync._upsert_api = AsyncMock()

        with (
            patch("src.services.git_service.git_service", mock_git),
            patch(
                "src.services.catalog_sync_service.CatalogSyncService",
                return_value=mock_sync,
            ),
        ):
            result = await svc._sync_api_from_git("acme", "foo")

        assert result is None
        mock_sync._upsert_api.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_head_commit_proceeds_with_none(self):
        """FileNotFoundError on head commit → upsert called with commit_sha=None.

        regression for CP-1 H.2
        """
        from src.services.deployment_orchestration_service import (
            DeploymentOrchestrationService,
        )

        mock_db = MagicMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: MagicMock()))
        mock_db.commit = AsyncMock()
        svc = DeploymentOrchestrationService(mock_db)

        mock_git = MagicMock()
        mock_git.is_connected.return_value = True
        mock_git.connect = AsyncMock()
        mock_git.get_api = AsyncMock(return_value={"name": "foo"})
        mock_git.get_api_openapi_spec = AsyncMock(return_value={"openapi": "3.0"})
        mock_git.get_head_commit_sha = AsyncMock(side_effect=FileNotFoundError("no commit"))

        mock_sync = MagicMock()
        mock_sync._upsert_api = AsyncMock()

        with (
            patch("src.services.git_service.git_service", mock_git),
            patch(
                "src.services.catalog_sync_service.CatalogSyncService",
                return_value=mock_sync,
            ),
        ):
            await svc._sync_api_from_git("acme", "foo")

        mock_sync._upsert_api.assert_awaited_once()
        call_args = mock_sync._upsert_api.await_args
        # commit_sha is the 5th positional arg
        assert call_args.args[4] is None, "commit_sha should be None on FileNotFoundError"
