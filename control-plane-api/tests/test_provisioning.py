"""
Tests for Gateway Provisioning Service - CAB-800

Tests cover:
- provision_on_approval: success, retry on failure, all retries exhausted
- deprovision_on_revocation: success, failure, skip when no gateway_app_id
- _resolve_adapter: default fallback, gateway deployment resolution
- GatewayAdminService.provision_application: success, cleanup on association failure
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


def _mock_adapter(provision_result=None, deprovision_result=None):
    """Create a mock adapter with default AdapterResult returns."""
    adapter = AsyncMock()
    adapter.provision_application = AsyncMock(
        return_value=provision_result or AdapterResult(
            success=True, resource_id="wm-app-001", data={"app_id": "wm-app-001"}
        )
    )
    adapter.deprovision_application = AsyncMock(
        return_value=deprovision_result or AdapterResult(success=True, resource_id="wm-app-001")
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

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
            return_value=adapter,
        ), patch(
            "src.services.provisioning_service.asyncio.sleep",
            new_callable=AsyncMock,
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
        adapter.provision_application = AsyncMock(
            side_effect=RuntimeError("connection refused")
        )

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
            return_value=adapter,
        ), patch(
            "src.services.provisioning_service.asyncio.sleep",
            new_callable=AsyncMock,
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
        adapter.provision_application = AsyncMock(
            side_effect=[fail_result, success_result]
        )

        with patch(
            "src.services.provisioning_service._resolve_adapter",
            new_callable=AsyncMock,
            return_value=adapter,
        ), patch(
            "src.services.provisioning_service.asyncio.sleep",
            new_callable=AsyncMock,
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
        adapter.deprovision_application = AsyncMock(
            side_effect=RuntimeError("not found")
        )

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

        with patch(
            "src.services.provisioning_service.GatewayDeploymentRepository",
            create=True,
        ) as MockDeployRepo, patch(
            "src.services.provisioning_service.GatewayInstanceRepository",
            create=True,
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
            mock_deploy_repo.get_primary_for_api = AsyncMock(
                side_effect=Exception("DB error")
            )

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
        svc.create_application = AsyncMock(
            return_value={"id": "wm-123", "name": "test-app"}
        )

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
        svc._request.assert_awaited_once_with(
            "DELETE", "/applications/wm-123", auth_token=None
        )
