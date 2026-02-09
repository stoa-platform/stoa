"""
Tests for Gateway Provisioning Service - CAB-800, CAB-1121 Phase 3

Tests cover:
- provision_on_approval: success, retry on failure, all retries exhausted
- provision_on_approval: consumer/plan enrichment, rate-limit policy push (CAB-1121)
- deprovision_on_revocation: success, failure, skip when no gateway_app_id, policy cleanup
- _push_rate_limit_policy: success, no plan, no quotas, failure
- _cleanup_rate_limit_policy: success, failure
- _resolve_adapter: default fallback, gateway deployment resolution
- GatewayAdminService.provision_application: success, cleanup on association failure
- STOA adapter: provision_application, deprovision_application
- webMethods adapter: idempotent provision_application
- Mappers: map_app_spec_to_route, map_quota_to_policy
"""

import pytest
from datetime import datetime
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.adapters.gateway_adapter_interface import AdapterResult


class SubscriptionStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"


class ProvisioningStatus(str, Enum):
    NONE = "none"
    PENDING = "pending"
    PROVISIONING = "provisioning"
    READY = "ready"
    FAILED = "failed"
    DEPROVISIONING = "deprovisioning"
    DEPROVISIONED = "deprovisioned"


def _make_subscription(**overrides):
    """Create a mock subscription with default values."""
    defaults = {
        "id": uuid4(),
        "application_id": "app-test-123",
        "application_name": "Test App",
        "subscriber_id": "user-1",
        "subscriber_email": "dev@acme.com",
        "api_id": "api-weather-456",
        "api_name": "Weather API",
        "api_version": "1.0",
        "tenant_id": "acme",
        "consumer_id": None,
        "plan_id": "basic",
        "plan_name": "Basic Plan",
        "api_key_hash": "hashed",
        "api_key_prefix": "stoa_sk_",
        "status": SubscriptionStatus.ACTIVE,
        "provisioning_status": ProvisioningStatus.NONE,
        "gateway_app_id": None,
        "provisioning_error": None,
        "provisioned_at": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "approved_at": datetime.utcnow(),
        "expires_at": None,
        "revoked_at": None,
        "approved_by": "admin-1",
        "revoked_by": None,
        "status_reason": None,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_consumer(**overrides):
    """Create a mock consumer with default values."""
    defaults = {
        "id": uuid4(),
        "external_id": "ext-consumer-001",
        "name": "Acme Consumer",
        "email": "consumer@acme.com",
        "company": "Acme Corp",
        "tenant_id": "acme",
        "keycloak_client_id": "kc-client-acme-001",
        "keycloak_user_id": None,
        "status": "active",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_plan(**overrides):
    """Create a mock plan with default values."""
    defaults = {
        "id": uuid4(),
        "slug": "gold",
        "name": "Gold Plan",
        "tenant_id": "acme",
        "rate_limit_per_second": None,
        "rate_limit_per_minute": 600,
        "daily_request_limit": 50000,
        "monthly_request_limit": 1000000,
        "burst_limit": 50,
        "requires_approval": True,
        "status": "active",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _mock_adapter(provision_result=None, deprovision_result=None, upsert_policy_result=None, delete_policy_result=None):
    """Create a mock adapter with default AdapterResult returns."""
    adapter = AsyncMock()
    adapter.provision_application = AsyncMock(
        return_value=provision_result
        or AdapterResult(success=True, resource_id="wm-app-001", data={"app_id": "wm-app-001"})
    )
    adapter.deprovision_application = AsyncMock(
        return_value=deprovision_result or AdapterResult(success=True, resource_id="wm-app-001")
    )
    adapter.upsert_policy = AsyncMock(
        return_value=upsert_policy_result or AdapterResult(success=True, resource_id="quota-001")
    )
    adapter.delete_policy = AsyncMock(
        return_value=delete_policy_result or AdapterResult(success=True, resource_id="quota-001")
    )
    return adapter


class TestProvisionOnApproval:
    """Tests for provisioning_service.provision_on_approval"""

    @pytest.mark.asyncio
    async def test_provision_success(self):
        """Successful provisioning sets status READY and stores gateway_app_id."""
        sub = _make_subscription()
        db = AsyncMock()

        adapter = _mock_adapter()

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
            return_value=adapter,
        ):
            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-123")

        assert sub.provisioning_status == ProvisioningStatus.READY
        assert sub.gateway_app_id == "wm-app-001"
        assert sub.provisioned_at is not None
        assert sub.provisioning_error is None
        assert db.commit.await_count >= 2  # PROVISIONING + READY

    @pytest.mark.asyncio
    async def test_provision_retries_then_succeeds(self):
        """Provisioning retries on failure and succeeds on second attempt."""
        sub = _make_subscription()
        db = AsyncMock()

        success_result = AdapterResult(success=True, resource_id="wm-app-002", data={})
        adapter = AsyncMock()
        adapter.provision_application = AsyncMock(
            side_effect=[
                RuntimeError("timeout"),
                success_result,
            ]
        )

        with (
            patch(
                "src.services.provisioning_service._resolve_adapter",
                new_callable=AsyncMock,
                return_value=adapter,
            ),
            patch(
                "src.services.provisioning_service.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-456")

        assert sub.provisioning_status == ProvisioningStatus.READY
        assert sub.gateway_app_id == "wm-app-002"
        assert adapter.provision_application.await_count == 2

    @pytest.mark.asyncio
    async def test_provision_all_retries_exhausted(self):
        """All retries fail sets status FAILED with error message."""
        sub = _make_subscription()
        db = AsyncMock()

        adapter = AsyncMock()
        adapter.provision_application = AsyncMock(side_effect=RuntimeError("connection refused"))

        with (
            patch(
                "src.services.provisioning_service._resolve_adapter",
                new_callable=AsyncMock,
                return_value=adapter,
            ),
            patch(
                "src.services.provisioning_service.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-789")

        assert sub.provisioning_status == ProvisioningStatus.FAILED
        assert "connection refused" in sub.provisioning_error
        assert adapter.provision_application.await_count == 3

    @pytest.mark.asyncio
    async def test_provision_adapter_returns_failure(self):
        """AdapterResult with success=False triggers retry."""
        sub = _make_subscription()
        db = AsyncMock()

        fail_result = AdapterResult(success=False, error="gateway 503")
        success_result = AdapterResult(success=True, resource_id="wm-app-003", data={})
        adapter = AsyncMock()
        adapter.provision_application = AsyncMock(side_effect=[fail_result, success_result])

        with (
            patch(
                "src.services.provisioning_service._resolve_adapter",
                new_callable=AsyncMock,
                return_value=adapter,
            ),
            patch(
                "src.services.provisioning_service.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-800")

        # First call returns failure (AdapterResult.success=False) which raises RuntimeError
        # Second call succeeds
        assert sub.provisioning_status == ProvisioningStatus.READY
        assert sub.gateway_app_id == "wm-app-003"


class TestDeprovisionOnRevocation:
    """Tests for provisioning_service.deprovision_on_revocation"""

    @pytest.mark.asyncio
    async def test_deprovision_success(self):
        """Successful deprovision sets status DEPROVISIONED."""
        sub = _make_subscription(
            gateway_app_id="wm-app-001",
            provisioning_status=ProvisioningStatus.READY,
        )
        db = AsyncMock()

        adapter = _mock_adapter()

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
            return_value=adapter,
        ):
            from src.services.provisioning_service import deprovision_on_revocation

            await deprovision_on_revocation(db, sub, "jwt-token", "corr-100")

        assert sub.provisioning_status == ProvisioningStatus.DEPROVISIONED
        assert sub.gateway_app_id is None

    @pytest.mark.asyncio
    async def test_deprovision_skip_when_no_app_id(self):
        """Skip deprovision when no gateway_app_id is set."""
        sub = _make_subscription(gateway_app_id=None)
        db = AsyncMock()

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
        ) as mock_resolve:
            from src.services.provisioning_service import deprovision_on_revocation

            await deprovision_on_revocation(db, sub, "jwt-token", "corr-200")

        mock_resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_deprovision_failure(self):
        """Failed deprovision sets status FAILED."""
        sub = _make_subscription(
            gateway_app_id="wm-app-999",
            provisioning_status=ProvisioningStatus.READY,
        )
        db = AsyncMock()

        adapter = AsyncMock()
        adapter.deprovision_application = AsyncMock(side_effect=RuntimeError("not found"))

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
            return_value=adapter,
        ):
            from src.services.provisioning_service import deprovision_on_revocation

            await deprovision_on_revocation(db, sub, "jwt-token", "corr-300")

        assert sub.provisioning_status == ProvisioningStatus.FAILED
        assert "not found" in sub.provisioning_error

    @pytest.mark.asyncio
    async def test_deprovision_adapter_failure_result(self):
        """AdapterResult with success=False sets status FAILED."""
        sub = _make_subscription(
            gateway_app_id="wm-app-500",
            provisioning_status=ProvisioningStatus.READY,
        )
        db = AsyncMock()

        fail_result = AdapterResult(success=False, error="gateway rejected")
        adapter = _mock_adapter(deprovision_result=fail_result)

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
            return_value=adapter,
        ):
            from src.services.provisioning_service import deprovision_on_revocation

            await deprovision_on_revocation(db, sub, "jwt-token", "corr-400")

        assert sub.provisioning_status == ProvisioningStatus.FAILED
        assert "gateway rejected" in sub.provisioning_error


class TestResolveAdapter:
    """Tests for _resolve_adapter helper."""

    @pytest.mark.asyncio
    async def test_resolve_returns_default_when_no_deployment(self):
        """Falls back to default adapter when no gateway deployment exists."""
        db = AsyncMock()

        with (
            patch(
                "src.services.provisioning_service.GatewayDeploymentRepository",
                create=True,
            ) as MockDeployRepo,
            patch(
                "src.services.provisioning_service.GatewayInstanceRepository",
                create=True,
            ),
        ):
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_primary_for_api = AsyncMock(return_value=None)

            from src.services.provisioning_service import _resolve_adapter, _default_adapter

            adapter = await _resolve_adapter(db, "api-123", "acme")
            assert adapter is _default_adapter

    @pytest.mark.asyncio
    async def test_resolve_returns_default_on_exception(self):
        """Falls back to default adapter when resolution fails."""
        db = AsyncMock()

        with patch(
            "src.services.provisioning_service.GatewayDeploymentRepository",
            create=True,
        ) as MockDeployRepo:
            mock_deploy_repo = MockDeployRepo.return_value
            mock_deploy_repo.get_primary_for_api = AsyncMock(side_effect=Exception("DB error"))

            from src.services.provisioning_service import _resolve_adapter, _default_adapter

            adapter = await _resolve_adapter(db, "api-123", "acme")
            assert adapter is _default_adapter


class TestGatewayAdminServiceProvisioning:
    """Tests for GatewayAdminService.provision_application and deprovision_application"""

    @pytest.mark.asyncio
    async def test_provision_application_creates_and_associates(self):
        """provision_application creates app then associates with API."""
        from src.services.gateway_service import GatewayAdminService

        svc = GatewayAdminService()
        svc._request = AsyncMock(
            side_effect=[
                # First call: POST /applications
                {"id": "wm-123", "name": "test-app"},
                # Second call: PUT /applications/{id}/apis
                {},
            ]
        )
        svc.create_application = AsyncMock(return_value={"id": "wm-123", "name": "test-app"})

        result = await svc.provision_application(
            subscription_id="sub-001",
            application_name="My App",
            api_id="api-100",
            tenant_id="acme",
            subscriber_email="dev@acme.com",
            correlation_id="corr-x",
        )

        assert result["app_id"] == "wm-123"
        svc.create_application.assert_awaited_once()
        svc._request.assert_awaited_once()  # PUT association call

    @pytest.mark.asyncio
    async def test_deprovision_application_deletes(self):
        """deprovision_application calls DELETE."""
        from src.services.gateway_service import GatewayAdminService

        svc = GatewayAdminService()
        svc._request = AsyncMock(return_value={})

        result = await svc.deprovision_application(
            app_id="wm-123",
            correlation_id="corr-y",
        )

        assert result is True
        svc._request.assert_awaited_once_with("DELETE", "/applications/wm-123", auth_token=None)


# ──────────────────────────────────────────────────────────────
# CAB-1121 Phase 3 — Consumer/Plan enrichment + policy push
# ──────────────────────────────────────────────────────────────


class TestProvisionWithConsumerPlanEnrichment:
    """Tests for consumer/plan context enrichment in provision_on_approval."""

    @pytest.mark.asyncio
    async def test_provision_enriches_app_spec_with_consumer_and_plan(self):
        """app_spec includes consumer and plan fields when both are present."""
        consumer = _make_consumer()
        plan = _make_plan()
        sub = _make_subscription(consumer_id=consumer.id, plan_id=str(plan.id))
        db = AsyncMock()

        captured_spec = {}
        adapter = _mock_adapter()

        async def capture_app_spec(spec, auth_token=None):
            captured_spec.update(spec)
            return AdapterResult(success=True, resource_id="route-001")

        adapter.provision_application = AsyncMock(side_effect=capture_app_spec)

        with (
            patch(
                "src.services.provisioning_service._resolve_adapter",
                new_callable=AsyncMock,
                return_value=adapter,
            ),
            patch(
                "src.services.provisioning_service.ConsumerRepository",
            ) as MockConsumerRepo,
            patch(
                "src.services.provisioning_service.PlanRepository",
            ) as MockPlanRepo,
        ):
            mock_consumer_repo = MockConsumerRepo.return_value
            mock_consumer_repo.get_by_id = AsyncMock(return_value=consumer)
            mock_plan_repo = MockPlanRepo.return_value
            mock_plan_repo.get_by_id = AsyncMock(return_value=plan)

            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-enrich")

        assert captured_spec["consumer_id"] == str(consumer.id)
        assert captured_spec["consumer_external_id"] == "ext-consumer-001"
        assert captured_spec["keycloak_client_id"] == "kc-client-acme-001"
        assert captured_spec["plan_slug"] == "gold"
        assert captured_spec["rate_limit_per_minute"] == 600
        assert captured_spec["daily_request_limit"] == 50000
        assert sub.provisioning_status == ProvisioningStatus.READY

    @pytest.mark.asyncio
    async def test_provision_works_without_consumer(self):
        """Provisioning succeeds even without consumer_id set."""
        plan = _make_plan()
        sub = _make_subscription(consumer_id=None, plan_id=str(plan.id))
        db = AsyncMock()

        adapter = _mock_adapter()

        with (
            patch(
                "src.services.provisioning_service._resolve_adapter",
                new_callable=AsyncMock,
                return_value=adapter,
            ),
            patch(
                "src.services.provisioning_service.PlanRepository",
            ) as MockPlanRepo,
        ):
            mock_plan_repo = MockPlanRepo.return_value
            mock_plan_repo.get_by_id = AsyncMock(return_value=plan)

            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-no-consumer")

        assert sub.provisioning_status == ProvisioningStatus.READY

    @pytest.mark.asyncio
    async def test_provision_works_without_plan(self):
        """Provisioning succeeds even without plan_id set."""
        sub = _make_subscription(consumer_id=None, plan_id=None)
        db = AsyncMock()

        adapter = _mock_adapter()

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
            return_value=adapter,
        ):
            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-no-plan")

        assert sub.provisioning_status == ProvisioningStatus.READY

    @pytest.mark.asyncio
    async def test_provision_continues_on_consumer_load_failure(self):
        """Consumer load failure is non-blocking — provisioning continues."""
        sub = _make_subscription(consumer_id=uuid4())
        db = AsyncMock()

        adapter = _mock_adapter()

        with (
            patch(
                "src.services.provisioning_service._resolve_adapter",
                new_callable=AsyncMock,
                return_value=adapter,
            ),
            patch(
                "src.services.provisioning_service.ConsumerRepository",
            ) as MockConsumerRepo,
        ):
            mock_consumer_repo = MockConsumerRepo.return_value
            mock_consumer_repo.get_by_id = AsyncMock(side_effect=Exception("DB error"))

            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-consumer-fail")

        assert sub.provisioning_status == ProvisioningStatus.READY


class TestPushRateLimitPolicy:
    """Tests for _push_rate_limit_policy helper."""

    @pytest.mark.asyncio
    async def test_push_policy_success(self):
        """Rate-limit policy is pushed when plan has rate_limit_per_minute."""
        plan = _make_plan(rate_limit_per_minute=600)
        consumer = _make_consumer()
        sub = _make_subscription()
        adapter = _mock_adapter()

        from src.services.provisioning_service import _push_rate_limit_policy

        await _push_rate_limit_policy(adapter, sub, plan, consumer, "jwt", "corr-1")

        adapter.upsert_policy.assert_awaited_once()
        policy_arg = adapter.upsert_policy.call_args[0][0]
        assert policy_arg["id"] == f"quota-{sub.id}"
        assert policy_arg["type"] == "rate_limit"
        assert policy_arg["config"]["maxRequests"] == 600
        assert policy_arg["name"] == "rate-limit-ext-consumer-001-gold"

    @pytest.mark.asyncio
    async def test_push_policy_skips_when_no_plan(self):
        """No policy push when plan is None."""
        sub = _make_subscription()
        adapter = _mock_adapter()

        from src.services.provisioning_service import _push_rate_limit_policy

        await _push_rate_limit_policy(adapter, sub, None, None, "jwt", "corr-2")

        adapter.upsert_policy.assert_not_called()

    @pytest.mark.asyncio
    async def test_push_policy_skips_when_no_quotas(self):
        """No policy push when plan has no rate limits."""
        plan = _make_plan(rate_limit_per_minute=None, rate_limit_per_second=None)
        sub = _make_subscription()
        adapter = _mock_adapter()

        from src.services.provisioning_service import _push_rate_limit_policy

        await _push_rate_limit_policy(adapter, sub, plan, None, "jwt", "corr-3")

        adapter.upsert_policy.assert_not_called()

    @pytest.mark.asyncio
    async def test_push_policy_non_blocking_on_failure(self):
        """Policy push failure does not raise."""
        plan = _make_plan(rate_limit_per_minute=100)
        sub = _make_subscription()
        adapter = _mock_adapter(upsert_policy_result=AdapterResult(success=False, error="gateway error"))

        from src.services.provisioning_service import _push_rate_limit_policy

        # Should not raise
        await _push_rate_limit_policy(adapter, sub, plan, None, "jwt", "corr-4")

    @pytest.mark.asyncio
    async def test_push_policy_non_blocking_on_exception(self):
        """Policy push exception does not raise."""
        plan = _make_plan(rate_limit_per_minute=100)
        sub = _make_subscription()
        adapter = AsyncMock()
        adapter.upsert_policy = AsyncMock(side_effect=Exception("network error"))

        from src.services.provisioning_service import _push_rate_limit_policy

        # Should not raise
        await _push_rate_limit_policy(adapter, sub, plan, None, "jwt", "corr-5")


class TestCleanupRateLimitPolicy:
    """Tests for _cleanup_rate_limit_policy helper."""

    @pytest.mark.asyncio
    async def test_cleanup_policy_success(self):
        """Rate-limit policy is deleted on deprovision."""
        sub = _make_subscription()
        adapter = _mock_adapter()

        from src.services.provisioning_service import _cleanup_rate_limit_policy

        await _cleanup_rate_limit_policy(adapter, sub, "jwt", "corr-cleanup")

        adapter.delete_policy.assert_awaited_once_with(f"quota-{sub.id}", auth_token="jwt")

    @pytest.mark.asyncio
    async def test_cleanup_policy_non_blocking_on_failure(self):
        """Policy cleanup failure does not raise."""
        sub = _make_subscription()
        adapter = _mock_adapter(delete_policy_result=AdapterResult(success=False, error="not found"))

        from src.services.provisioning_service import _cleanup_rate_limit_policy

        # Should not raise
        await _cleanup_rate_limit_policy(adapter, sub, "jwt", "corr-cleanup-fail")


class TestDeprovisionWithPolicyCleanup:
    """Tests for deprovision_on_revocation with rate-limit policy cleanup."""

    @pytest.mark.asyncio
    async def test_deprovision_cleans_up_policy(self):
        """Deprovision calls delete_policy before deprovision_application."""
        sub = _make_subscription(
            gateway_app_id="wm-app-001",
            provisioning_status=ProvisioningStatus.READY,
        )
        db = AsyncMock()
        adapter = _mock_adapter()

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
            return_value=adapter,
        ):
            from src.services.provisioning_service import deprovision_on_revocation

            await deprovision_on_revocation(db, sub, "jwt-token", "corr-deprov")

        # Both delete_policy and deprovision_application should be called
        adapter.delete_policy.assert_awaited_once()
        adapter.deprovision_application.assert_awaited_once()
        assert sub.provisioning_status == ProvisioningStatus.DEPROVISIONED


class TestStoaAdapterProvision:
    """Tests for StoaGatewayAdapter.provision_application (CAB-1121 Phase 3)."""

    @pytest.mark.asyncio
    async def test_provision_calls_sync_api_and_upsert_policy(self):
        """provision_application registers route and pushes rate-limit policy."""
        from src.adapters.stoa.adapter import StoaGatewayAdapter

        adapter = StoaGatewayAdapter(config={"base_url": "http://gw:8080"})

        # Mock the internal methods
        adapter.sync_api = AsyncMock(return_value=AdapterResult(success=True, resource_id="route-abc"))
        adapter.upsert_policy = AsyncMock(return_value=AdapterResult(success=True, resource_id="quota-sub-1"))

        app_spec = {
            "subscription_id": "sub-1",
            "application_name": "Test App",
            "api_id": "api-123",
            "tenant_id": "acme",
            "rate_limit_per_minute": 600,
            "plan_slug": "gold",
            "consumer_external_id": "ext-001",
        }

        result = await adapter.provision_application(app_spec)

        assert result.success is True
        assert result.resource_id == "route-abc"
        adapter.sync_api.assert_awaited_once()
        adapter.upsert_policy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provision_without_quotas_skips_policy(self):
        """provision_application skips policy push when no quotas in app_spec."""
        from src.adapters.stoa.adapter import StoaGatewayAdapter

        adapter = StoaGatewayAdapter(config={"base_url": "http://gw:8080"})
        adapter.sync_api = AsyncMock(return_value=AdapterResult(success=True, resource_id="route-xyz"))
        adapter.upsert_policy = AsyncMock()

        app_spec = {
            "subscription_id": "sub-2",
            "application_name": "No Quota App",
            "api_id": "api-456",
            "tenant_id": "acme",
        }

        result = await adapter.provision_application(app_spec)

        assert result.success is True
        adapter.upsert_policy.assert_not_called()

    @pytest.mark.asyncio
    async def test_provision_fails_when_sync_api_fails(self):
        """provision_application returns failure when sync_api fails."""
        from src.adapters.stoa.adapter import StoaGatewayAdapter

        adapter = StoaGatewayAdapter(config={"base_url": "http://gw:8080"})
        adapter.sync_api = AsyncMock(return_value=AdapterResult(success=False, error="HTTP 500"))

        result = await adapter.provision_application({"subscription_id": "s1", "tenant_id": "t"})

        assert result.success is False
        assert "sync_api failed" in result.error

    @pytest.mark.asyncio
    async def test_deprovision_returns_success(self):
        """deprovision_application always returns success (route kept)."""
        from src.adapters.stoa.adapter import StoaGatewayAdapter

        adapter = StoaGatewayAdapter()
        result = await adapter.deprovision_application("route-abc")

        assert result.success is True
        assert result.resource_id == "route-abc"


class TestWebMethodsIdempotentProvision:
    """Tests for webMethods adapter idempotent provision_application (CAB-1121 Phase 3)."""

    @pytest.mark.asyncio
    async def test_provision_returns_existing_app(self):
        """provision_application returns existing app when name matches."""
        from src.adapters.webmethods.adapter import WebMethodsGatewayAdapter

        adapter = WebMethodsGatewayAdapter.__new__(WebMethodsGatewayAdapter)
        adapter._config = {}
        adapter._svc = AsyncMock()

        # list_applications returns existing app
        adapter.list_applications = AsyncMock(return_value=[{"id": "existing-app-001", "name": "Test App"}])

        app_spec = {
            "subscription_id": "sub-1",
            "application_name": "Test App",
            "api_id": "api-123",
            "tenant_id": "acme",
        }

        result = await adapter.provision_application(app_spec)

        assert result.success is True
        assert result.resource_id == "existing-app-001"
        # Should NOT call provision_application on the service
        adapter._svc.provision_application.assert_not_called()

    @pytest.mark.asyncio
    async def test_provision_creates_when_no_existing(self):
        """provision_application creates new app when no match found."""
        from src.adapters.webmethods.adapter import WebMethodsGatewayAdapter

        adapter = WebMethodsGatewayAdapter.__new__(WebMethodsGatewayAdapter)
        adapter._config = {}
        adapter._svc = AsyncMock()
        adapter._svc.provision_application = AsyncMock(return_value={"app_id": "new-app-002"})

        # list_applications returns empty
        adapter.list_applications = AsyncMock(return_value=[])

        app_spec = {
            "subscription_id": "sub-2",
            "application_name": "New App",
            "api_id": "api-456",
            "tenant_id": "acme",
        }

        result = await adapter.provision_application(app_spec)

        assert result.success is True
        assert result.resource_id == "new-app-002"
        adapter._svc.provision_application.assert_awaited_once()


class TestMappers:
    """Tests for stoa mapper functions (CAB-1121 Phase 3)."""

    def test_map_app_spec_to_route(self):
        """map_app_spec_to_route converts enriched app_spec to sync_api format."""
        from src.adapters.stoa.mappers import map_app_spec_to_route

        app_spec = {
            "api_id": "api-123",
            "tenant_id": "acme",
            "application_name": "Weather App",
            "backend_url": "https://api.weather.com",
        }

        route = map_app_spec_to_route(app_spec)

        assert route["api_catalog_id"] == "api-123"
        assert route["api_name"] == "Weather App"
        assert route["tenant_id"] == "acme"
        assert route["backend_url"] == "https://api.weather.com"
        assert route["activated"] is True

    def test_map_quota_to_policy_with_per_minute(self):
        """map_quota_to_policy builds rate-limit policy from per-minute quota."""
        from src.adapters.stoa.mappers import map_quota_to_policy

        app_spec = {
            "rate_limit_per_minute": 600,
            "consumer_external_id": "ext-001",
            "plan_slug": "gold",
            "api_id": "api-123",
        }

        policy = map_quota_to_policy(app_spec, "sub-001")

        assert policy is not None
        assert policy["id"] == "quota-sub-001"
        assert policy["name"] == "rate-limit-ext-001-gold"
        assert policy["type"] == "rate_limit"
        assert policy["config"]["maxRequests"] == 600
        assert policy["config"]["intervalSeconds"] == 60

    def test_map_quota_to_policy_with_per_second(self):
        """map_quota_to_policy converts per-second to per-minute."""
        from src.adapters.stoa.mappers import map_quota_to_policy

        app_spec = {
            "rate_limit_per_second": 10,
            "rate_limit_per_minute": None,
            "api_id": "api-456",
        }

        policy = map_quota_to_policy(app_spec, "sub-002")

        assert policy is not None
        assert policy["config"]["maxRequests"] == 600  # 10 * 60

    def test_map_quota_to_policy_returns_none_when_no_quotas(self):
        """map_quota_to_policy returns None when no rate limits defined."""
        from src.adapters.stoa.mappers import map_quota_to_policy

        app_spec = {"api_id": "api-789"}

        policy = map_quota_to_policy(app_spec, "sub-003")

        assert policy is None
