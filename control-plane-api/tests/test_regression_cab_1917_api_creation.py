"""
Regression tests for CAB-1917 — Fix API creation and deployment pipeline.

Covers:
1. Legacy deployment endpoint returns deprecation headers
2. auto_deploy_on_promotion() is called on promotion approval
3. list_apis returns 503 on errors (not empty list)
4. OpenAPI spec validation rejects invalid specs
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 1. Legacy deploy endpoint — deprecation headers
# ---------------------------------------------------------------------------

class TestRegression_LegacyDeployDeprecation:
    """CAB-1917: deploy_to_environment must return Deprecation headers."""

    def test_deploy_returns_deprecation_header(self, client_as_tenant_admin):
        with patch("src.routers.api_gateway_assignments.DeploymentOrchestrationService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.deploy_api_to_env = AsyncMock(return_value=[MagicMock(id="dep-1")])
            mock_svc_cls.return_value = mock_svc

            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis/test-api/deploy",
                json={"environment": "dev"},
            )

        assert resp.status_code == 201
        assert resp.headers.get("Deprecation") == "true"
        assert resp.headers.get("Sunset") == "2026-06-01"


# ---------------------------------------------------------------------------
# 2. auto_deploy_on_promotion wired to approval flow
# ---------------------------------------------------------------------------

class TestRegression_AutoDeployOnPromotion:
    """CAB-1917: approve_promotion() must trigger auto_deploy_on_promotion()."""

    @pytest.mark.asyncio
    async def test_approve_calls_auto_deploy(self):
        from uuid import uuid4

        from src.services.promotion_service import PromotionService

        mock_db = AsyncMock()
        svc = PromotionService(mock_db)

        # Set up a mock promotion in PENDING state
        mock_promotion = MagicMock()
        mock_promotion.id = uuid4()
        mock_promotion.status = "pending"
        mock_promotion.requested_by = "other-user"
        mock_promotion.target_environment = "staging"
        mock_promotion.api_id = "api-123"
        mock_promotion.source_environment = "dev"

        svc.repo = MagicMock()
        svc.repo.get_by_id_and_tenant = AsyncMock(return_value=mock_promotion)
        svc.repo.update = AsyncMock(return_value=mock_promotion)

        mock_orch = MagicMock()
        mock_orch.auto_deploy_on_promotion = AsyncMock(return_value=["dep1"])

        with (
            patch("src.services.promotion_service.kafka_service") as mock_kafka,
            patch(
                "src.services.deployment_orchestration_service.DeploymentOrchestrationService",
                return_value=mock_orch,
            ) as mock_orch_cls,
            patch("src.services.promotion_service.notify_promotion_event", new_callable=AsyncMock),
        ):
            mock_kafka.publish = AsyncMock()
            # Also patch the lazy import inside approve_promotion
            with patch.dict(
                "sys.modules",
                {
                    "src.services.deployment_orchestration_service": MagicMock(
                        DeploymentOrchestrationService=MagicMock(return_value=mock_orch)
                    )
                },
            ):
                await svc.approve_promotion(
                    tenant_id="acme",
                    promotion_id=mock_promotion.id,
                    approved_by="admin",
                    user_id="user-1",
                )

            mock_orch.auto_deploy_on_promotion.assert_called_once_with(
                api_id="api-123",
                tenant_id="acme",
                target_environment="staging",
                approved_by="admin",
            )


# ---------------------------------------------------------------------------
# 3. list_apis error handling
# ---------------------------------------------------------------------------

class TestRegression_ListApisErrorHandling:
    """CAB-1917: list_apis must return 503 when backend fails, not empty list."""

    def test_git_error_returns_503(self, client_as_tenant_admin):
        with patch("src.routers.apis.git_service") as mock_git:
            mock_git.list_apis = AsyncMock(side_effect=ConnectionError("GitLab unreachable"))
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis")

        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    def test_git_error_does_not_return_200_empty(self, client_as_tenant_admin):
        with patch("src.routers.apis.git_service") as mock_git:
            mock_git.list_apis = AsyncMock(side_effect=RuntimeError("timeout"))
            resp = client_as_tenant_admin.get("/v1/tenants/acme/apis")

        assert resp.status_code != 200


# ---------------------------------------------------------------------------
# 4. OpenAPI spec validation
# ---------------------------------------------------------------------------

class TestRegression_OpenAPISpecValidation:
    """CAB-1917: create_api must validate OpenAPI spec syntax."""

    def test_valid_openapi_30_accepted(self, client_as_tenant_admin):
        spec = '{"openapi": "3.0.3", "info": {"title": "Test", "version": "1.0"}, "paths": {}}'
        with (
            patch("src.routers.apis.git_service") as mock_git,
            patch("src.routers.apis.kafka_service") as mock_kafka,
        ):
            mock_git._project = True
            mock_git.list_apis = AsyncMock(return_value=[])
            mock_git.create_api = AsyncMock()
            mock_kafka.emit_api_created = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()

            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "test-api",
                    "display_name": "Test API",
                    "backend_url": "https://api.example.com",
                    "openapi_spec": spec,
                },
            )

        assert resp.status_code == 200

    def test_invalid_json_spec_rejected(self, client_as_tenant_admin):
        with patch("src.routers.apis.git_service") as mock_git:
            mock_git._project = True
            mock_git.list_apis = AsyncMock(return_value=[])

            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "test-api",
                    "display_name": "Test API",
                    "backend_url": "https://api.example.com",
                    "openapi_spec": "{invalid json!!!",
                },
            )

        assert resp.status_code == 400
        assert "Invalid OpenAPI spec" in resp.json()["detail"]

    def test_spec_missing_version_rejected(self, client_as_tenant_admin):
        with patch("src.routers.apis.git_service") as mock_git:
            mock_git._project = True
            mock_git.list_apis = AsyncMock(return_value=[])

            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "test-api",
                    "display_name": "Test API",
                    "backend_url": "https://api.example.com",
                    "openapi_spec": '{"info": {"title": "No version"}}',
                },
            )

        assert resp.status_code == 400
        assert "missing" in resp.json()["detail"].lower()

    def test_no_spec_still_accepted(self, client_as_tenant_admin):
        """No spec = no validation needed (spec is optional)."""
        with (
            patch("src.routers.apis.git_service") as mock_git,
            patch("src.routers.apis.kafka_service") as mock_kafka,
        ):
            mock_git._project = True
            mock_git.list_apis = AsyncMock(return_value=[])
            mock_git.create_api = AsyncMock()
            mock_kafka.emit_api_created = AsyncMock()
            mock_kafka.emit_audit_event = AsyncMock()

            resp = client_as_tenant_admin.post(
                "/v1/tenants/acme/apis",
                json={
                    "name": "test-api",
                    "display_name": "Test API",
                    "backend_url": "https://api.example.com",
                },
            )

        assert resp.status_code == 200
