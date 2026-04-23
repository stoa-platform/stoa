"""Regression coverage for CAB-1889 external GitProvider leak fixes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.deployment_orchestration_service import DeploymentOrchestrationService
from src.services.iam_sync_service import IAMSyncService


@pytest.mark.asyncio
async def test_regression_cab_1889_iam_sync_uses_provider_tree_listing():
    """sync_all_tenants must use the provider interface, not GitLab's `_project`."""
    svc = IAMSyncService()
    svc.sync_tenant = AsyncMock(return_value={"actions": [], "errors": []})
    tenant_dir = SimpleNamespace(type="tree", name="acme")

    with patch("src.services.iam_sync_service.git_service") as mock_git:
        mock_git.is_connected.return_value = True
        mock_git.list_tree = AsyncMock(return_value=[tenant_dir])

        await svc.sync_all_tenants()

    mock_git.is_connected.assert_called_once_with()
    # CP-1 P2 M.4: the caller drops the explicit ref so list_tree resolves
    # to settings.git.default_branch inside the provider. The important
    # invariant is that the ABC is used (no _project leakage).
    mock_git.list_tree.assert_awaited_once_with("tenants")
    svc.sync_tenant.assert_awaited_once_with("acme")
    assert not any("_project" in str(call) for call in mock_git.mock_calls), (
        f"_project leaked into calls: {mock_git.mock_calls}"
    )


@pytest.mark.asyncio
async def test_regression_cab_1889_deployment_sync_uses_provider_head_lookup():
    """_sync_api_from_git must fetch head SHA via GitProvider, not `_project`."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock()
    db.execute.return_value = mock_result

    svc = DeploymentOrchestrationService(db)

    with (
        patch("src.services.git_service.git_service") as mock_git,
        patch("src.services.catalog_sync_service.CatalogSyncService") as mock_catalog_cls,
    ):
        mock_git.is_connected.return_value = True
        mock_git.connect = AsyncMock()
        mock_git.get_api = AsyncMock(return_value={"api_id": "payments", "version": "2.0.0"})
        mock_git.get_api_openapi_spec = AsyncMock(return_value={"openapi": "3.0.0"})
        mock_git.get_head_commit_sha = AsyncMock(return_value="sha123")
        mock_catalog_cls.return_value._upsert_api = AsyncMock()

        await svc._sync_api_from_git("acme", "payments")

    mock_git.is_connected.assert_called_once_with()
    # CP-1 P2 M.4: the caller drops the explicit ref so get_head_commit_sha
    # resolves to settings.git.default_branch inside the provider. The
    # important invariant is that the ABC is used (no _project leakage).
    mock_git.get_head_commit_sha.assert_awaited_once_with()
    assert not any("_project" in str(call) for call in mock_git.mock_calls), (
        f"_project leaked into calls: {mock_git.mock_calls}"
    )
