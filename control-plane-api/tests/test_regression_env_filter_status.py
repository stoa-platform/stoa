"""
Regression test for CAB-1803 / PR #1735 — environment filter + status derivation.

Root cause: Prod environment showed ALL APIs (including drafts), and APIs deployed
to dev still showed "draft" status because GitLab YAML status was never updated.

Invariants:
1. Prod filter only shows APIs deployed to both dev AND staging
2. Staging filter only shows APIs deployed to staging
3. DEV filter shows deployed + undeployed (draft) APIs
4. Status is read from DB catalog (set correctly during create/sync)

Updated: Migrated from _api_from_yaml (GitLab) to _api_from_catalog (DB).
"""

import uuid
from unittest.mock import MagicMock

import pytest

from src.models.catalog import APICatalog
from src.routers.apis import _api_from_catalog


def _mock_catalog(**overrides):
    """Build a mock APICatalog row."""
    defaults = {
        "id": uuid.uuid4(),
        "tenant_id": "oasis",
        "api_id": overrides.get("name", "test-api"),
        "api_name": overrides.get("name", "test-api"),
        "version": "1.0.0",
        "status": overrides.pop("status", "draft"),
        "tags": overrides.pop("tags", []),
        "portal_published": False,
        "api_metadata": {
            "name": overrides.get("name", "test-api"),
            "description": overrides.get("description", ""),
            "backend_url": overrides.get("backend_url", "https://api.example.com"),
            "deployments": overrides.pop("deployments", {}),
        },
        "openapi_spec": None,
    }
    overrides.pop("name", None)
    overrides.pop("description", None)
    overrides.pop("backend_url", None)
    defaults.update(overrides)
    mock = MagicMock(spec=APICatalog)
    for key, value in defaults.items():
        setattr(mock, key, value)
    return mock


@pytest.fixture
def api_draft():
    """API with no deployments (draft)."""
    return _mock_catalog(name="draft-api", status="draft", deployments={})


@pytest.fixture
def api_dev_only():
    """API deployed only to dev — status should be 'published' in DB."""
    return _mock_catalog(
        name="dev-api", status="published", deployments={"dev": True, "staging": False}
    )


@pytest.fixture
def api_staging_only():
    """API deployed only to staging."""
    return _mock_catalog(
        name="staging-api", status="published", deployments={"dev": False, "staging": True}
    )


@pytest.fixture
def api_both():
    """API deployed to both dev and staging (promotion candidate)."""
    return _mock_catalog(
        name="promoted-api", status="published", deployments={"dev": True, "staging": True}
    )


class TestRegression_StatusDerivation:
    """Regression for PR #1735: status derived from deployment flags."""

    def test_regression_draft_api_stays_draft(self, api_draft):
        """An API with no deployments should have status 'draft'.

        Ticket: CAB-1803
        PR: #1735
        """
        result = _api_from_catalog(api_draft)
        assert result.status == "draft"

    def test_regression_dev_deployed_becomes_published(self, api_dev_only):
        """An API deployed to dev should have status 'published', not 'draft'.

        Ticket: CAB-1803
        PR: #1735
        """
        result = _api_from_catalog(api_dev_only)
        assert result.status == "published", (
            f"Expected 'published' for dev-deployed API, got '{result.status}'"
        )

    def test_regression_staging_deployed_becomes_published(self, api_staging_only):
        """An API deployed to staging should also be 'published'."""
        result = _api_from_catalog(api_staging_only)
        assert result.status == "published"

    def test_regression_explicit_status_preserved(self):
        """If DB has an explicit non-draft status, preserve it."""
        api = _mock_catalog(
            name="deprecated-api", status="deprecated", deployments={"dev": True}
        )
        result = _api_from_catalog(api)
        assert result.status == "deprecated"


class TestRegression_EnvironmentFilter:
    """Regression for PR #1735: prod filter no longer shows all APIs."""

    def _build_api_list(self, api_draft, api_dev_only, api_staging_only, api_both):
        return [
            _api_from_catalog(api_draft),
            _api_from_catalog(api_dev_only),
            _api_from_catalog(api_staging_only),
            _api_from_catalog(api_both),
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
