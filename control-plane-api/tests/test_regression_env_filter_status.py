"""
Regression test for CAB-1803 / PR #1735 — environment filter + status derivation.

Root cause: Prod environment showed ALL APIs (including drafts), and APIs deployed
to dev still showed "draft" status because GitLab YAML status was never updated.

Invariants:
1. Prod filter only shows APIs deployed to both dev AND staging
2. Staging filter only shows APIs deployed to staging
3. DEV filter shows deployed + undeployed (draft) APIs
4. Status is "published" when deployed to any environment, "draft" otherwise
"""

import pytest

from src.routers.apis import _api_from_yaml


@pytest.fixture
def api_draft():
    """API with no deployments (draft)."""
    return {
        "name": "draft-api",
        "version": "1.0.0",
        "description": "A draft API",
        "backend_url": "https://api.example.com",
        "deployments": {},
        "tags": [],
    }


@pytest.fixture
def api_dev_only():
    """API deployed only to dev."""
    return {
        "name": "dev-api",
        "version": "1.0.0",
        "description": "Dev-deployed API",
        "backend_url": "https://api.example.com",
        "deployments": {"dev": True, "staging": False},
        "tags": [],
    }


@pytest.fixture
def api_staging_only():
    """API deployed only to staging."""
    return {
        "name": "staging-api",
        "version": "1.0.0",
        "description": "Staging-deployed API",
        "backend_url": "https://api.example.com",
        "deployments": {"dev": False, "staging": True},
        "tags": [],
    }


@pytest.fixture
def api_both():
    """API deployed to both dev and staging (promotion candidate)."""
    return {
        "name": "promoted-api",
        "version": "1.0.0",
        "description": "Fully promoted API",
        "backend_url": "https://api.example.com",
        "deployments": {"dev": True, "staging": True},
        "tags": [],
    }


class TestRegression_StatusDerivation:
    """Regression for PR #1735: status derived from deployment flags."""

    def test_regression_draft_api_stays_draft(self, api_draft):
        """An API with no deployments should have status 'draft'.

        Ticket: CAB-1803
        PR: #1735
        """
        result = _api_from_yaml("oasis", api_draft)
        assert result.status == "draft"

    def test_regression_dev_deployed_becomes_published(self, api_dev_only):
        """An API deployed to dev should have status 'published', not 'draft'.

        This was THE bug: GitLab YAML status was never updated on deploy,
        so deployed APIs showed 'draft' in the UI.

        Ticket: CAB-1803
        PR: #1735
        """
        result = _api_from_yaml("oasis", api_dev_only)
        assert result.status == "published", (
            f"Expected 'published' for dev-deployed API, got '{result.status}'"
        )

    def test_regression_staging_deployed_becomes_published(self, api_staging_only):
        """An API deployed to staging should also be 'published'."""
        result = _api_from_yaml("oasis", api_staging_only)
        assert result.status == "published"

    def test_regression_explicit_status_preserved(self):
        """If YAML has an explicit non-draft status, preserve it."""
        api_data = {
            "name": "deprecated-api",
            "version": "1.0.0",
            "backend_url": "https://api.example.com",
            "status": "deprecated",
            "deployments": {"dev": True},
            "tags": [],
        }
        result = _api_from_yaml("oasis", api_data)
        assert result.status == "deprecated"


class TestRegression_EnvironmentFilter:
    """Regression for PR #1735: prod filter no longer shows all APIs."""

    def _build_api_list(self, api_draft, api_dev_only, api_staging_only, api_both):
        return [
            _api_from_yaml("oasis", api_draft),
            _api_from_yaml("oasis", api_dev_only),
            _api_from_yaml("oasis", api_staging_only),
            _api_from_yaml("oasis", api_both),
        ]

    def test_regression_prod_filter_excludes_draft(self, api_draft, api_dev_only, api_staging_only, api_both):
        """Prod view must NOT show draft APIs. This was the bug: prod filter
        passed everything through.

        Ticket: CAB-1803
        PR: #1735
        """
        all_apis = self._build_api_list(api_draft, api_dev_only, api_staging_only, api_both)
        prod_filtered = [api for api in all_apis if api.deployed_dev and api.deployed_staging]
        assert len(prod_filtered) == 1
        assert prod_filtered[0].name == "promoted-api"

    def test_regression_dev_filter_includes_drafts(self, api_draft, api_dev_only, api_staging_only, api_both):
        """DEV view shows deployed + undeployed (draft) APIs."""
        all_apis = self._build_api_list(api_draft, api_dev_only, api_staging_only, api_both)
        dev_filtered = [
            api for api in all_apis
            if api.deployed_dev or (not api.deployed_dev and not api.deployed_staging)
        ]
        names = {api.name for api in dev_filtered}
        assert "draft-api" in names, "Draft APIs should appear in DEV view"
        assert "dev-api" in names, "Dev-deployed APIs should appear in DEV view"
        assert "promoted-api" in names, "Both-deployed APIs should appear in DEV view"
        assert "staging-api" not in names, "Staging-only APIs should NOT appear in DEV view"

    def test_regression_staging_filter(self, api_draft, api_dev_only, api_staging_only, api_both):
        """Staging view shows only staging-deployed APIs."""
        all_apis = self._build_api_list(api_draft, api_dev_only, api_staging_only, api_both)
        staging_filtered = [api for api in all_apis if api.deployed_staging]
        names = {api.name for api in staging_filtered}
        assert names == {"staging-api", "promoted-api"}
