"""
Regression test for CAB-1803 / PR #1731 — deployment uses API name, not UUID.

Root cause: create_deployment() passed UUID to git_service.get_api() which
expects the API name (directory slug). GitLab lookup always failed silently
(except Exception: pass), so the deployment flag was never set — API stayed
as "draft" even when user selected "Deploy to DEV".

Invariant: git_service calls in the deployment flow MUST use the API name
(directory slug), not the UUID.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_git_service():
    """Git service that tracks lookup keys."""
    service = MagicMock()
    service._project = True  # connected

    lookup_keys = []

    async def mock_get_api(tenant_id: str, api_name: str):
        lookup_keys.append(api_name)
        if api_name == "petstore-api":
            return {
                "id": "petstore-api",
                "name": "petstore-api",
                "version": "1.0.0",
                "deployments": {"dev": False, "staging": False},
            }
        return None

    async def mock_update_api(tenant_id: str, api_name: str, data: dict):
        lookup_keys.append(f"update:{api_name}")
        return True

    service.get_api = AsyncMock(side_effect=mock_get_api)
    service.update_api = AsyncMock(side_effect=mock_update_api)
    service.lookup_keys = lookup_keys
    return service


def _get_unwrapped(fn):
    """Unwrap decorated async function to bypass RBAC decorators."""
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


class TestRegression_DeploymentNameLookup:
    """Regression for PR #1731: deployment must use API name, not UUID."""

    @pytest.mark.asyncio
    async def test_regression_deployment_uses_api_name_not_uuid(self, mock_git_service):
        """When api_name is provided, git_service.get_api must receive the name,
        not the UUID. This was THE bug: UUID lookup → 404 → deployment flag
        never set → API stuck in draft.

        Ticket: CAB-1803
        PR: #1731
        """
        from src.routers.deployments import create_deployment

        inner = _get_unwrapped(create_deployment)

        mock_request = MagicMock()
        mock_request.api_id = "a1b2c3d4-uuid-that-doesnt-exist-in-gitlab"
        mock_request.api_name = "petstore-api"
        mock_request.environment = MagicMock(value="dev")
        mock_request.version = "1.0.0"
        mock_request.gateway_id = None

        mock_user = MagicMock()
        mock_user.username = "admin"
        mock_user.id = "user-1"

        mock_db = AsyncMock()
        mock_deployment = MagicMock()
        mock_deployment.id = "dep-1"

        with (
            patch("src.routers.deployments.DeploymentService") as mock_svc_cls,
            patch("src.routers.deployments.DeploymentResponse") as mock_resp_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc.create_deployment = AsyncMock(return_value=mock_deployment)
            mock_resp_cls.model_validate = MagicMock(return_value=mock_deployment)

            await inner(
                tenant_id="oasis",
                request=mock_request,
                user=mock_user,
                db=mock_db,
                git=mock_git_service,
            )

        # THE INVARIANT: git provider must have been called with the name, not UUID
        assert "petstore-api" in mock_git_service.lookup_keys, (
            f"git provider was called with {mock_git_service.lookup_keys}, "
            "expected 'petstore-api' (the name), not the UUID"
        )
        # Verify update_api was also called with the name
        assert "update:petstore-api" in mock_git_service.lookup_keys, (
            f"git provider update_api was called with {mock_git_service.lookup_keys}, "
            "expected 'update:petstore-api'"
        )

    @pytest.mark.asyncio
    async def test_regression_deployment_falls_back_to_api_id_when_no_name(self, mock_git_service):
        """When api_name is not provided (legacy clients), fall back to api_id
        as the lookup key — this works when api_id IS the name (from list_apis).
        """
        from src.routers.deployments import create_deployment

        inner = _get_unwrapped(create_deployment)

        mock_request = MagicMock()
        mock_request.api_id = "petstore-api"  # name used as ID (from list response)
        mock_request.api_name = None
        mock_request.environment = MagicMock(value="dev")
        mock_request.version = None
        mock_request.gateway_id = None

        mock_user = MagicMock()
        mock_user.username = "admin"
        mock_user.id = "user-1"

        mock_db = AsyncMock()
        mock_deployment = MagicMock()

        with (
            patch("src.routers.deployments.DeploymentService") as mock_svc_cls,
            patch("src.routers.deployments.DeploymentResponse") as mock_resp_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc.create_deployment = AsyncMock(return_value=mock_deployment)
            mock_resp_cls.model_validate = MagicMock(return_value=mock_deployment)

            await inner(
                tenant_id="oasis",
                request=mock_request,
                user=mock_user,
                db=mock_db,
                git=mock_git_service,
            )

        # Should use api_id as lookup key (which is the name)
        assert "petstore-api" in mock_git_service.lookup_keys
