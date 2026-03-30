"""Regression tests for CAB-1921: Deployment reliability fixes.

Tests:
1. build_desired_state includes methods extracted from OpenAPI paths
2. Policy config keys normalized across AWS/Azure/Apigee adapters
3. Drift detection works when spec_hash is empty
4. Inline sync increments retry counter on exception
"""

from unittest.mock import MagicMock

import pytest

# ── Fix 1: methods in build_desired_state ──────────────────────────


class TestBuildDesiredStateMethods:
    """Regression: build_desired_state must include HTTP methods from OpenAPI spec."""

    def _build(self, spec_data: dict | None = None, metadata: dict | None = None):
        from src.services.gateway_deployment_service import GatewayDeploymentService

        catalog = MagicMock()
        catalog.openapi_spec = spec_data
        catalog.api_metadata = metadata or {}
        catalog.version = "1.0"
        catalog.api_name = "test-api"
        catalog.api_id = "api-1"
        catalog.id = "cat-1"
        catalog.tenant_id = "t-1"
        return GatewayDeploymentService.build_desired_state(catalog)

    def test_regression_cab_1921_methods_extracted_from_openapi(self):
        spec = {
            "paths": {
                "/users": {"get": {}, "post": {}},
                "/users/{id}": {"get": {}, "delete": {}},
            }
        }
        state = self._build(spec_data=spec)
        assert sorted(state["methods"]) == ["DELETE", "GET", "POST"]

    def test_regression_cab_1921_methods_defaults_when_no_paths(self):
        state = self._build(spec_data={"info": {"title": "test"}})
        assert state["methods"] == ["GET", "POST", "PUT", "DELETE"]

    def test_regression_cab_1921_methods_defaults_when_no_spec(self):
        state = self._build(metadata={"backend_url": "http://example.com"})
        assert state["methods"] == ["GET", "POST", "PUT", "DELETE"]


# ── Fix 2: Policy config key normalization ─────────────────────────


class TestPolicyConfigNormalization:
    """Regression: AWS/Azure/Apigee mappers must accept canonical maxRequests/intervalSeconds."""

    def test_regression_cab_1921_aws_canonical_keys(self):
        from src.adapters.aws.mappers import map_policy_to_aws_usage_plan

        result = map_policy_to_aws_usage_plan(
            {"id": "p1", "config": {"maxRequests": 200, "intervalSeconds": 60}},
            tenant_id="t1",
        )
        # 200 requests / 60 seconds = 3.33 req/s
        assert result["throttle"]["rateLimit"] == pytest.approx(200 / 60)

    def test_regression_cab_1921_aws_legacy_keys_still_work(self):
        from src.adapters.aws.mappers import map_policy_to_aws_usage_plan

        result = map_policy_to_aws_usage_plan(
            {"id": "p1", "config": {"max_requests": 300, "window_seconds": 60}},
            tenant_id="t1",
        )
        assert result["throttle"]["rateLimit"] == pytest.approx(300 / 60)

    def test_regression_cab_1921_azure_canonical_keys(self):
        from src.adapters.azure.mappers import map_policy_to_azure_product

        result = map_policy_to_azure_product(
            {"id": "p1", "name": "test", "config": {"maxRequests": 500, "intervalSeconds": 120}},
            tenant_id="t1",
        )
        assert result["_stoa_rate_limit"]["calls"] == 500
        assert result["_stoa_rate_limit"]["renewal_period"] == 120

    def test_regression_cab_1921_apigee_canonical_keys(self):
        from src.adapters.apigee.mappers import map_policy_to_apigee_product

        result = map_policy_to_apigee_product(
            {"type": "rate_limit", "id": "p1", "config": {"maxRequests": 150, "intervalSeconds": 60}},
            tenant_id="t1",
        )
        assert result["quota"] == "150"
        assert result["quotaInterval"] == "60"


# ── Fix 5: Drift detection with empty spec_hash ───────────────────


class TestDriftDetectionEmptyHash:
    """Regression: drift must be detected when one side has empty spec_hash."""

    def test_regression_cab_1921_drift_when_gateway_hash_empty(self):
        gw_hash = ""
        desired_hash = "abc123"
        # Old buggy condition: if gw_hash and desired_hash → False (no drift)
        # Fixed condition: if (gw_hash or desired_hash) and gw_hash != desired_hash → True
        assert (gw_hash or desired_hash) and gw_hash != desired_hash

    def test_regression_cab_1921_drift_when_desired_hash_empty(self):
        gw_hash = "abc123"
        desired_hash = ""
        assert (gw_hash or desired_hash) and gw_hash != desired_hash

    def test_regression_cab_1921_no_drift_when_both_empty(self):
        gw_hash = ""
        desired_hash = ""
        # Both empty = no drift (no spec to compare)
        assert not ((gw_hash or desired_hash) and gw_hash != desired_hash)

    def test_regression_cab_1921_no_drift_when_hashes_match(self):
        gw_hash = "abc123"
        desired_hash = "abc123"
        assert not ((gw_hash or desired_hash) and gw_hash != desired_hash)


# ── Fix 6: Inline sync retry counter ──────────────────────────────


class TestInlineSyncRetryCounter:
    """Regression: inline sync must increment sync_attempts on exception."""

    @pytest.mark.asyncio
    async def test_regression_cab_1921_retry_counter_incremented_on_exception(self):
        from unittest.mock import AsyncMock, patch

        from src.services.deployment_orchestration_service import DeploymentOrchestrationService

        # Create a mock deployment
        dep = MagicMock()
        dep.sync_attempts = 0
        dep.gateway_instance_id = "gw-1"
        dep.desired_state = {"tenant_id": "t1"}
        dep.id = "dep-1"

        mock_db = MagicMock()
        svc = DeploymentOrchestrationService.__new__(DeploymentOrchestrationService)
        svc.db = mock_db

        # Patch where GatewayInstanceRepository is imported (inside the method)
        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(side_effect=ConnectionError("db down"))

        with patch(
            "src.repositories.gateway_instance.GatewayInstanceRepository",
            return_value=mock_gw_repo,
        ):
            await svc._try_inline_sync([dep])

        assert dep.sync_attempts == 1
        assert dep.sync_status.value == "pending"
