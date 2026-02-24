"""Tests for src/services/provisioning_service.py (CAB-1437 Phase 2).

Covers: _resolve_adapter, provision_on_approval (with retry logic),
deprovision_on_revocation, _push_rate_limit_policy, _cleanup_rate_limit_policy.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.services.provisioning_service import (
    _cleanup_rate_limit_policy,
    _push_rate_limit_policy,
    _resolve_adapter,
    deprovision_on_revocation,
    provision_on_approval,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_subscription(
    *,
    id=None,
    api_id: str = "api-1",
    tenant_id: str = "tenant-1",
    application_name: str = "My App",
    subscriber_email: str = "dev@example.com",
    consumer_id=None,
    plan_id=None,
    gateway_app_id: str | None = None,
    provisioning_status: str = "PENDING",
):
    sub = MagicMock()
    sub.id = id or uuid4()
    sub.api_id = api_id
    sub.tenant_id = tenant_id
    sub.application_name = application_name
    sub.subscriber_email = subscriber_email
    sub.consumer_id = consumer_id
    sub.plan_id = plan_id
    sub.gateway_app_id = gateway_app_id
    sub.provisioning_status = provisioning_status
    sub.provisioning_error = None
    sub.provisioned_at = None
    return sub


def _make_adapter_result(*, success: bool = True, error: str | None = None, resource_id: str | None = "app-123"):
    r = MagicMock()
    r.success = success
    r.error = error
    r.resource_id = resource_id
    return r


def _make_adapter() -> MagicMock:
    adapter = AsyncMock()
    adapter.provision_application = AsyncMock(return_value=_make_adapter_result())
    adapter.deprovision_application = AsyncMock(return_value=_make_adapter_result())
    adapter.upsert_policy = AsyncMock(return_value=_make_adapter_result())
    adapter.delete_policy = AsyncMock(return_value=_make_adapter_result())
    return adapter


def _make_consumer(*, id=None, external_id: str = "ext-consumer-1", keycloak_client_id: str = "kc-client"):
    c = MagicMock()
    c.id = id or uuid4()
    c.external_id = external_id
    c.keycloak_client_id = keycloak_client_id
    return c


def _make_plan(
    *,
    id=None,
    slug: str = "premium",
    rate_limit_per_second: int = 10,
    rate_limit_per_minute: int = 100,
    daily_request_limit: int = 10000,
    monthly_request_limit: int = 300000,
    burst_limit: int = 50,
):
    p = MagicMock()
    p.id = id or uuid4()
    p.slug = slug
    p.rate_limit_per_second = rate_limit_per_second
    p.rate_limit_per_minute = rate_limit_per_minute
    p.daily_request_limit = daily_request_limit
    p.monthly_request_limit = monthly_request_limit
    p.burst_limit = burst_limit
    return p


# ─────────────────────────────────────────────
# 1. TestResolveAdapter
# ─────────────────────────────────────────────


class TestResolveAdapter:
    """_resolve_adapter() — looks up deployment → gateway → AdapterRegistry.create()."""

    async def test_found_deployment_and_gateway_returns_adapter(self):
        db = _make_db()
        deployment = MagicMock()
        deployment.gateway_instance_id = "gw-1"

        gateway = MagicMock()
        gateway.gateway_type.value = "kong"
        gateway.base_url = "https://kong.example.com"
        gateway.auth_config = {"token": "secret"}

        mock_deploy_repo = MagicMock()
        mock_deploy_repo.get_primary_for_api = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=gateway)

        mock_adapter = MagicMock()

        with (
            patch("src.repositories.gateway_deployment.GatewayDeploymentRepository", return_value=mock_deploy_repo),
            patch("src.repositories.gateway_instance.GatewayInstanceRepository", return_value=mock_gw_repo),
            patch("src.services.provisioning_service.AdapterRegistry") as mock_registry,
        ):
            mock_registry.create.return_value = mock_adapter
            result = await _resolve_adapter(db, "api-1", "tenant-1")

        assert result is mock_adapter
        mock_registry.create.assert_called_once_with(
            "kong", config={"base_url": "https://kong.example.com", "auth_config": {"token": "secret"}}
        )

    async def test_no_deployment_returns_default(self):
        db = _make_db()
        mock_deploy_repo = MagicMock()
        mock_deploy_repo.get_primary_for_api = AsyncMock(return_value=None)

        with patch("src.repositories.gateway_deployment.GatewayDeploymentRepository", return_value=mock_deploy_repo):
            result = await _resolve_adapter(db, "api-1", "tenant-1")

        # Should return _default_adapter (module-level webmethods)
        from src.services.provisioning_service import _default_adapter

        assert result is _default_adapter

    async def test_no_gateway_returns_default(self):
        db = _make_db()
        deployment = MagicMock()
        deployment.gateway_instance_id = "gw-missing"

        mock_deploy_repo = MagicMock()
        mock_deploy_repo.get_primary_for_api = AsyncMock(return_value=deployment)

        mock_gw_repo = MagicMock()
        mock_gw_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch("src.repositories.gateway_deployment.GatewayDeploymentRepository", return_value=mock_deploy_repo),
            patch("src.repositories.gateway_instance.GatewayInstanceRepository", return_value=mock_gw_repo),
        ):
            result = await _resolve_adapter(db, "api-1", "tenant-1")

        from src.services.provisioning_service import _default_adapter

        assert result is _default_adapter

    async def test_exception_returns_default(self):
        db = _make_db()

        with patch(
            "src.repositories.gateway_deployment.GatewayDeploymentRepository",
            side_effect=RuntimeError("DB error"),
        ):
            result = await _resolve_adapter(db, "api-1", "tenant-1")

        from src.services.provisioning_service import _default_adapter

        assert result is _default_adapter


# ─────────────────────────────────────────────
# 2. TestProvisionOnApproval
# ─────────────────────────────────────────────


class TestProvisionOnApproval:
    """provision_on_approval() — retry loop, consumer/plan enrichment."""

    async def test_success_first_attempt(self):
        db = _make_db()
        sub = _make_subscription()
        adapter = _make_adapter()

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service._push_rate_limit_policy", new_callable=AsyncMock),
        ):
            await provision_on_approval(db, sub, "token", "corr-1")

        from src.models.subscription import ProvisioningStatus

        assert sub.provisioning_status == ProvisioningStatus.READY
        assert sub.gateway_app_id == "app-123"
        assert sub.provisioning_error is None
        adapter.provision_application.assert_called_once()

    async def test_success_on_retry(self):
        db = _make_db()
        sub = _make_subscription()
        adapter = _make_adapter()
        adapter.provision_application = AsyncMock(
            side_effect=[
                _make_adapter_result(success=False, error="Temporary error"),
                _make_adapter_result(success=True, resource_id="app-456"),
            ]
        )

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service._push_rate_limit_policy", new_callable=AsyncMock),
            patch("src.services.provisioning_service.asyncio.sleep", new_callable=AsyncMock),
        ):
            await provision_on_approval(db, sub, "token", "corr-1")

        from src.models.subscription import ProvisioningStatus

        assert sub.provisioning_status == ProvisioningStatus.READY
        assert sub.gateway_app_id == "app-456"
        assert adapter.provision_application.call_count == 2

    async def test_all_retries_exhausted(self):
        db = _make_db()
        sub = _make_subscription()
        adapter = _make_adapter()
        adapter.provision_application = AsyncMock(
            side_effect=RuntimeError("Gateway unreachable")
        )

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service.asyncio.sleep", new_callable=AsyncMock),
        ):
            await provision_on_approval(db, sub, "token", "corr-1")

        from src.models.subscription import ProvisioningStatus

        assert sub.provisioning_status == ProvisioningStatus.FAILED
        assert "Gateway unreachable" in sub.provisioning_error
        assert adapter.provision_application.call_count == 3

    async def test_consumer_enrichment(self):
        db = _make_db()
        consumer_id = uuid4()
        sub = _make_subscription(consumer_id=consumer_id)
        adapter = _make_adapter()
        consumer = _make_consumer(id=consumer_id)

        mock_consumer_repo = MagicMock()
        mock_consumer_repo.get_by_id = AsyncMock(return_value=consumer)

        captured_spec = {}

        async def capture_provision(spec, **kwargs):
            captured_spec.update(spec)
            return _make_adapter_result()

        adapter.provision_application = capture_provision

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service.ConsumerRepository", return_value=mock_consumer_repo),
            patch("src.services.provisioning_service._push_rate_limit_policy", new_callable=AsyncMock),
        ):
            await provision_on_approval(db, sub, "token", "corr-1")

        assert captured_spec.get("consumer_id") == str(consumer_id)
        assert captured_spec.get("consumer_external_id") == "ext-consumer-1"

    async def test_plan_enrichment(self):
        db = _make_db()
        plan_id = uuid4()
        sub = _make_subscription(plan_id=plan_id)
        adapter = _make_adapter()
        plan = _make_plan(id=plan_id)

        mock_plan_repo = MagicMock()
        mock_plan_repo.get_by_id = AsyncMock(return_value=plan)

        captured_spec = {}

        async def capture_provision(spec, **kwargs):
            captured_spec.update(spec)
            return _make_adapter_result()

        adapter.provision_application = capture_provision

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service.PlanRepository", return_value=mock_plan_repo),
            patch("src.services.provisioning_service._push_rate_limit_policy", new_callable=AsyncMock),
        ):
            await provision_on_approval(db, sub, "token", "corr-1")

        assert captured_spec.get("plan_slug") == "premium"
        assert captured_spec.get("rate_limit_per_minute") == 100

    async def test_consumer_load_failure_continues(self):
        db = _make_db()
        sub = _make_subscription(consumer_id=uuid4())
        adapter = _make_adapter()

        mock_consumer_repo = MagicMock()
        mock_consumer_repo.get_by_id = AsyncMock(side_effect=RuntimeError("DB error"))

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service.ConsumerRepository", return_value=mock_consumer_repo),
            patch("src.services.provisioning_service._push_rate_limit_policy", new_callable=AsyncMock),
        ):
            await provision_on_approval(db, sub, "token", "corr-1")

        from src.models.subscription import ProvisioningStatus

        # Should still succeed despite consumer load failure
        assert sub.provisioning_status == ProvisioningStatus.READY

    async def test_plan_load_failure_continues(self):
        db = _make_db()
        sub = _make_subscription(plan_id=uuid4())
        adapter = _make_adapter()

        mock_plan_repo = MagicMock()
        mock_plan_repo.get_by_id = AsyncMock(side_effect=RuntimeError("DB error"))

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service.PlanRepository", return_value=mock_plan_repo),
            patch("src.services.provisioning_service._push_rate_limit_policy", new_callable=AsyncMock),
        ):
            await provision_on_approval(db, sub, "token", "corr-1")

        from src.models.subscription import ProvisioningStatus

        assert sub.provisioning_status == ProvisioningStatus.READY

    async def test_rate_limit_policy_pushed_after_success(self):
        db = _make_db()
        plan = _make_plan()
        sub = _make_subscription(plan_id=plan.id)
        adapter = _make_adapter()

        mock_plan_repo = MagicMock()
        mock_plan_repo.get_by_id = AsyncMock(return_value=plan)

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service.PlanRepository", return_value=mock_plan_repo),
            patch("src.services.provisioning_service._push_rate_limit_policy", new_callable=AsyncMock) as mock_push,
        ):
            await provision_on_approval(db, sub, "token", "corr-1")

        mock_push.assert_called_once()


# ─────────────────────────────────────────────
# 3. TestDeprovisionOnRevocation
# ─────────────────────────────────────────────


class TestDeprovisionOnRevocation:
    """deprovision_on_revocation() — cleanup + deprovision."""

    async def test_success(self):
        db = _make_db()
        sub = _make_subscription(gateway_app_id="app-123")
        adapter = _make_adapter()

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service._cleanup_rate_limit_policy", new_callable=AsyncMock),
        ):
            await deprovision_on_revocation(db, sub, "token", "corr-1")

        from src.models.subscription import ProvisioningStatus

        assert sub.provisioning_status == ProvisioningStatus.DEPROVISIONED
        assert sub.gateway_app_id is None

    async def test_no_gateway_app_id_returns_early(self):
        db = _make_db()
        sub = _make_subscription(gateway_app_id=None)

        await deprovision_on_revocation(db, sub, "token", "corr-1")

        # No adapter calls, no status change
        db.commit.assert_not_called()

    async def test_adapter_failure_sets_failed(self):
        db = _make_db()
        sub = _make_subscription(gateway_app_id="app-123")
        adapter = _make_adapter()
        adapter.deprovision_application = AsyncMock(
            side_effect=RuntimeError("Gateway down")
        )

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service._cleanup_rate_limit_policy", new_callable=AsyncMock),
        ):
            await deprovision_on_revocation(db, sub, "token", "corr-1")

        from src.models.subscription import ProvisioningStatus

        assert sub.provisioning_status == ProvisioningStatus.FAILED
        assert "Deprovision failed" in sub.provisioning_error

    async def test_adapter_returns_failure_sets_failed(self):
        db = _make_db()
        sub = _make_subscription(gateway_app_id="app-123")
        adapter = _make_adapter()
        adapter.deprovision_application = AsyncMock(
            return_value=_make_adapter_result(success=False, error="Not found")
        )

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service._cleanup_rate_limit_policy", new_callable=AsyncMock),
        ):
            await deprovision_on_revocation(db, sub, "token", "corr-1")

        from src.models.subscription import ProvisioningStatus

        assert sub.provisioning_status == ProvisioningStatus.FAILED

    async def test_cleanup_rate_limit_called_before_deprovision(self):
        db = _make_db()
        sub = _make_subscription(gateway_app_id="app-123")
        adapter = _make_adapter()
        call_order = []

        async def track_cleanup(*args, **kwargs):
            call_order.append("cleanup")

        async def track_deprovision(*args, **kwargs):
            call_order.append("deprovision")
            return _make_adapter_result()

        adapter.deprovision_application = track_deprovision

        with (
            patch("src.services.provisioning_service._resolve_adapter", new_callable=AsyncMock, return_value=adapter),
            patch("src.services.provisioning_service._cleanup_rate_limit_policy", side_effect=track_cleanup),
        ):
            await deprovision_on_revocation(db, sub, "token", "corr-1")

        assert call_order == ["cleanup", "deprovision"]


# ─────────────────────────────────────────────
# 4. TestPushRateLimitPolicy
# ─────────────────────────────────────────────


class TestPushRateLimitPolicy:
    """_push_rate_limit_policy() — non-blocking rate-limit push."""

    async def test_pushes_policy_with_plan(self):
        adapter = _make_adapter()
        sub = _make_subscription()
        plan = _make_plan(rate_limit_per_minute=200)
        consumer = _make_consumer()

        await _push_rate_limit_policy(adapter, sub, plan, consumer, "token", "corr-1")

        adapter.upsert_policy.assert_called_once()
        spec = adapter.upsert_policy.call_args[0][0]
        assert spec["type"] == "rate_limit"
        assert spec["config"]["maxRequests"] == 200

    async def test_no_plan_returns_early(self):
        adapter = _make_adapter()
        sub = _make_subscription()

        await _push_rate_limit_policy(adapter, sub, None, None, "token", "corr-1")

        adapter.upsert_policy.assert_not_called()

    async def test_no_rate_limit_returns_early(self):
        adapter = _make_adapter()
        sub = _make_subscription()
        plan = MagicMock()
        plan.rate_limit_per_minute = None
        plan.rate_limit_per_second = None

        await _push_rate_limit_policy(adapter, sub, plan, None, "token", "corr-1")

        adapter.upsert_policy.assert_not_called()

    async def test_adapter_failure_does_not_raise(self):
        adapter = _make_adapter()
        adapter.upsert_policy = AsyncMock(side_effect=RuntimeError("Gateway error"))
        sub = _make_subscription()
        plan = _make_plan()

        # Should not raise
        await _push_rate_limit_policy(adapter, sub, plan, None, "token", "corr-1")

    async def test_adapter_returns_failure_does_not_raise(self):
        adapter = _make_adapter()
        adapter.upsert_policy = AsyncMock(
            return_value=_make_adapter_result(success=False, error="Policy rejected")
        )
        sub = _make_subscription()
        plan = _make_plan()

        # Should not raise
        await _push_rate_limit_policy(adapter, sub, plan, None, "token", "corr-1")


# ─────────────────────────────────────────────
# 5. TestCleanupRateLimitPolicy
# ─────────────────────────────────────────────


class TestCleanupRateLimitPolicy:
    """_cleanup_rate_limit_policy() — non-blocking rate-limit cleanup."""

    async def test_deletes_policy(self):
        adapter = _make_adapter()
        sub = _make_subscription()

        await _cleanup_rate_limit_policy(adapter, sub, "token", "corr-1")

        adapter.delete_policy.assert_called_once()
        policy_id = adapter.delete_policy.call_args[0][0]
        assert f"quota-{sub.id}" == policy_id

    async def test_adapter_failure_does_not_raise(self):
        adapter = _make_adapter()
        adapter.delete_policy = AsyncMock(side_effect=RuntimeError("Network error"))
        sub = _make_subscription()

        # Should not raise
        await _cleanup_rate_limit_policy(adapter, sub, "token", "corr-1")

    async def test_adapter_returns_failure_does_not_raise(self):
        adapter = _make_adapter()
        adapter.delete_policy = AsyncMock(
            return_value=_make_adapter_result(success=False, error="Not found")
        )
        sub = _make_subscription()

        # Should not raise
        await _cleanup_rate_limit_policy(adapter, sub, "token", "corr-1")
