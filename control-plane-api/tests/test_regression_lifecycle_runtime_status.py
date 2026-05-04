"""Regression tests for lifecycle runtime status projections."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from src.models.catalog import APICatalog
from src.routers.apis import _api_from_catalog


def test_regression_api_list_uses_gateway_deployment_runtime_status():
    """The API list must expose GatewayDeployment runtime state, not stale metadata."""

    catalog_api = MagicMock(spec=APICatalog)
    catalog_api.id = uuid4()
    catalog_api.tenant_id = "acme"
    catalog_api.api_id = "banking-demo"
    catalog_api.api_name = "Banking Demo"
    catalog_api.version = "1.0.0"
    catalog_api.status = "ready"
    catalog_api.tags = []
    catalog_api.portal_published = False
    catalog_api.openapi_spec = {"openapi": "3.0.0", "info": {"title": "Banking Demo", "version": "1.0.0"}, "paths": {}}
    catalog_api.synced_at = datetime.now(UTC)
    catalog_api.deleted_at = None
    catalog_api.api_metadata = {
        "name": "banking-demo",
        "display_name": "Banking Demo",
        "version": "1.0.0",
        "status": "ready",
        "deployments": {"dev": False, "staging": False},
        "tags": [],
    }

    api_response = _api_from_catalog(
        catalog_api,
        [
            {
                "environment": "dev",
                "status": "synced",
                "gateway_count": 1,
                "synced_count": 1,
                "error_count": 0,
                "pending_count": 0,
                "drifted_count": 0,
                "latest_error": None,
                "last_sync_success": None,
                "gateway_names": ["stoa-dev"],
            }
        ],
    )

    assert api_response.deployed_dev is True
    assert api_response.deployed_staging is False
    assert api_response.runtime_deployments[0].environment == "dev"
    assert api_response.runtime_deployments[0].status == "synced"
