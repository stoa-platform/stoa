"""Regression test: Deploy dialog must resolve APIs by Git name, not only catalog UUID.

PR: #1898
Ticket: CAB-1888
Root cause: DeploymentOrchestrationService only accepted catalog UUIDs, but the
  deploy dialog loaded APIs from Git (string names). When api_catalog was empty
  (no catalog sync run), the dialog showed zero APIs.
Invariant: _resolve_api_catalog() MUST find an API by name/id even if the catalog
  was populated on-demand from Git, not pre-synced.
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestRegressionCAB1888DeployApiResolution:
    """Ensure deploy flow works with Git API names (not just catalog UUIDs)."""

    def _make_catalog(self, **overrides):
        defaults = {
            "id": uuid4(),
            "api_name": "payments",
            "api_id": "payments-v2",
            "tenant_id": "acme",
            "version": "2.0.0",
            "openapi_spec": {"openapi": "3.0.0"},
            "api_metadata": None,
            "status": "active",
        }
        defaults.update(overrides)
        mock = MagicMock()
        for k, v in defaults.items():
            setattr(mock, k, v)
        return mock

    @pytest.mark.asyncio
    async def test_resolve_by_api_id_string(self):
        """API should be found by Git api_id (string), not just catalog UUID."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()
        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        # First call (UUID lookup) returns None, second call (api_id lookup) returns catalog
        mock_result_none = MagicMock()
        mock_result_none.scalar_one_or_none.return_value = None
        mock_result_found = MagicMock()
        mock_result_found.scalar_one_or_none.return_value = catalog

        db.execute = AsyncMock(side_effect=[mock_result_none, mock_result_found])

        result = await svc._resolve_api_catalog("acme", "payments-v2")
        assert result == catalog

    @pytest.mark.asyncio
    async def test_resolve_by_api_name_string(self):
        """API should be found by api_name when api_id doesn't match."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()
        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        # UUID lookup → None, api_id lookup → None, api_name lookup → found
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        mock_found = MagicMock()
        mock_found.scalar_one_or_none.return_value = catalog

        db.execute = AsyncMock(side_effect=[mock_none, mock_none, mock_found])

        result = await svc._resolve_api_catalog("acme", "payments")
        assert result == catalog

    @pytest.mark.asyncio
    async def test_resolve_triggers_git_sync_when_not_in_catalog(self):
        """When API is not in catalog at all, _sync_api_from_git should be called."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog = self._make_catalog()
        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        # All DB lookups return None
        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_none)

        # Mock _sync_api_from_git to return the catalog entry
        with patch.object(svc, "_sync_api_from_git", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = catalog

            result = await svc._resolve_api_catalog("acme", "payments-v2")

            assert result == catalog
            mock_sync.assert_called_once_with("acme", "payments-v2")

    @pytest.mark.asyncio
    async def test_resolve_raises_when_not_found_anywhere(self):
        """When API doesn't exist in catalog or Git, should raise ValueError."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        mock_none = MagicMock()
        mock_none.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_none)

        with patch.object(svc, "_sync_api_from_git", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = None

            with pytest.raises(ValueError, match="not found"):
                await svc._resolve_api_catalog("acme", "nonexistent-api")

    @pytest.mark.asyncio
    async def test_resolve_by_uuid_still_works(self):
        """Backward compat: catalog UUID should still resolve directly."""
        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        catalog_id = uuid4()
        catalog = self._make_catalog(id=catalog_id)
        db = AsyncMock()
        svc = DeploymentOrchestrationService(db)

        mock_found = MagicMock()
        mock_found.scalar_one_or_none.return_value = catalog
        db.execute = AsyncMock(return_value=mock_found)

        result = await svc._resolve_api_catalog("acme", str(catalog_id))
        assert result == catalog
