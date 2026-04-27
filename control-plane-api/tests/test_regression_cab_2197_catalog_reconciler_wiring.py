"""Regression tests for CAB-2197 (catalog_git_client wired to GitLabService).

Phase 6 strangler activation crashed the reconciler every 10s because
``main.py:343`` constructed ``GitHubContentsCatalogClient`` with the legacy
module-level ``git_service`` singleton from ``services.git_service`` — which
was hardcoded to a ``GitLabService`` instance. The GitHub adapter calls
``self._github_service._require_gh()``, which doesn't exist on
``GitLabService``, hence:

    AttributeError: 'GitLabService' object has no attribute '_require_gh'

Phase 4-2 (CAB-2185) and Phase 5 (CAB-2186) tests injected an in-memory
fake ``CatalogGitClient`` directly, so the production wiring (settings →
factory → connect → adapter) was never exercised in CI.

These tests pin the post-fix invariants:
  1. ``services.git_service.git_service`` resolves to whichever provider
     ``settings.git.provider`` selects (here: ``GitHubService`` for the
     prod default).
  2. Passing that singleton into ``GitHubContentsCatalogClient`` and
     calling ``.list()`` does NOT raise ``AttributeError`` on
     ``_require_gh``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from src.config import GitHubConfig, GitLabConfig, GitProviderConfig


def _github_cfg() -> GitProviderConfig:
    """Build a github-flavoured GitProviderConfig for factory tests."""
    return GitProviderConfig.model_construct(
        provider="github",
        github=GitHubConfig(
            token=SecretStr("test-token"),
            org="stoa-platform",
            catalog_repo="stoa-catalog",
        ),
        gitlab=GitLabConfig(
            url="https://gitlab.com",
            token=SecretStr(""),
            project_id="",
        ),
    )


class TestRegressionCab2197CatalogReconcilerWiring:
    """Pin the contract: factory(github) → catalog client → .list() works."""

    @pytest.mark.asyncio
    async def test_factory_to_catalog_client_no_attribute_error(self):
        """Pre-fix: ``main.py`` passed the GitLab singleton, ``.list()`` raised
        ``AttributeError`` because GitLabService has no ``_require_gh``.

        Post-fix: the factory yields ``GitHubService`` under
        ``GIT_PROVIDER=github``, and the adapter chain runs to completion.
        """
        from src.services.catalog_git_client.github_contents import (
            GitHubContentsCatalogClient,
        )
        from src.services.git_provider import git_provider_factory
        from src.services.github_service import GitHubService

        with patch("src.services.git_provider.settings") as mock_settings:
            mock_settings.git = _github_cfg()
            provider = git_provider_factory()

        # Guard: factory must return a GitHubService — otherwise the
        # legacy mis-wiring (GitLabService into a GitHub adapter) is back.
        assert isinstance(provider, GitHubService)

        # Bypass real PyGithub auth — _require_gh just returns self._gh
        # when set, so we can inject a fake client directly.
        fake_gh = MagicMock()
        fake_repo = MagicMock()
        fake_ref = MagicMock()
        fake_ref.object.sha = "deadbeef"
        fake_tree = MagicMock()
        fake_tree.tree = []  # empty repo
        fake_repo.get_git_ref.return_value = fake_ref
        fake_repo.get_git_tree.return_value = fake_tree
        fake_gh.get_repo.return_value = fake_repo
        provider._gh = fake_gh

        client = GitHubContentsCatalogClient(github_service=provider)

        # Pre-fix this raised AttributeError on _require_gh; post-fix
        # the adapter consumes the GitHubService, fans out to PyGithub
        # (here mocked), and returns an empty list for the empty tree.
        with patch("src.services.git_provider.settings") as mock_settings:
            mock_settings.git = _github_cfg()
            mock_settings.git.default_branch = "main"
            result = await client.list("tenants/*/apis/*/api.yaml")

        assert result == []

    def test_singleton_assignment_uses_provider_factory(self):
        """Structural pin: ``services/git_service.py`` must build its
        module-level ``git_service`` singleton via ``git_provider_factory()``,
        not by hardcoding ``GitLabService()``.

        A behavioural test through ``importlib.reload`` is unreliable here
        because ``services/__init__.py`` re-exports the singleton symbol,
        which shadows the submodule of the same name in attribute lookup.
        We resolve the module via ``sys.modules`` and grep its source — the
        bug was a single hardcoded line, so a source-level pin is the most
        targeted regression guard.
        """
        import sys
        from pathlib import Path

        gs_module = sys.modules["src.services.git_service"]
        src = Path(gs_module.__file__).read_text()

        assert "git_service = git_provider_factory()" in src, (
            "services/git_service.py must build the singleton via "
            "git_provider_factory(); pre-fix it hardcoded GitLabService(), "
            "causing CAB-2197 AttributeError on _require_gh in the catalog "
            "reconciler under GIT_PROVIDER=github."
        )
        assert "git_service = GitLabService()" not in src, (
            "Hardcoded GitLabService() singleton found — CAB-2197 regression. "
            "Use git_provider_factory() so the singleton is provider-aware."
        )
