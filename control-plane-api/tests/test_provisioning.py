"""
Tests for Gateway Provisioning Service - CAB-800

Tests cover:
- provision_on_approval: success, retry on failure, all retries exhausted
- deprovision_on_revocation: success, failure, skip when no gateway_app_id
- GatewayAdminService.provision_application: success, cleanup on association failure
"""

import pytest
from datetime import datetime
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


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


class TestProvisionOnApproval:
    """Tests for provisioning_service.provision_on_approval"""

    @pytest.mark.asyncio
    async def test_provision_success(self):
        """Successful provisioning sets status READY and stores gateway_app_id."""
        sub = _make_subscription()
        db = AsyncMock()

        mock_result = {"app_id": "wm-app-001", "application": {"name": "test"}}

        with patch(
            "src.services.provisioning_service.gateway_service"
        ) as mock_gw:
            mock_gw.provision_application = AsyncMock(return_value=mock_result)

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

        mock_result = {"app_id": "wm-app-002", "application": {}}

        with patch(
            "src.services.provisioning_service.gateway_service"
        ) as mock_gw, patch(
            "src.services.provisioning_service.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            mock_gw.provision_application = AsyncMock(
                side_effect=[RuntimeError("timeout"), mock_result]
            )

            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-456")

        assert sub.provisioning_status == ProvisioningStatus.READY
        assert sub.gateway_app_id == "wm-app-002"
        assert mock_gw.provision_application.await_count == 2

    @pytest.mark.asyncio
    async def test_provision_all_retries_exhausted(self):
        """All retries fail sets status FAILED with error message."""
        sub = _make_subscription()
        db = AsyncMock()

        with patch(
            "src.services.provisioning_service.gateway_service"
        ) as mock_gw, patch(
            "src.services.provisioning_service.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            mock_gw.provision_application = AsyncMock(
                side_effect=RuntimeError("connection refused")
            )

            from src.services.provisioning_service import provision_on_approval

            await provision_on_approval(db, sub, "jwt-token", "corr-789")

        assert sub.provisioning_status == ProvisioningStatus.FAILED
        assert "connection refused" in sub.provisioning_error
        assert mock_gw.provision_application.await_count == 3


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

        with patch(
            "src.services.provisioning_service.gateway_service"
        ) as mock_gw:
            mock_gw.deprovision_application = AsyncMock(return_value=True)

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
            "src.services.provisioning_service.gateway_service"
        ) as mock_gw:
            from src.services.provisioning_service import deprovision_on_revocation

            await deprovision_on_revocation(db, sub, "jwt-token", "corr-200")

        mock_gw.deprovision_application.assert_not_called()

    @pytest.mark.asyncio
    async def test_deprovision_failure(self):
        """Failed deprovision sets status FAILED."""
        sub = _make_subscription(
            gateway_app_id="wm-app-999",
            provisioning_status=ProvisioningStatus.READY,
        )
        db = AsyncMock()

        with patch(
            "src.services.provisioning_service.gateway_service"
        ) as mock_gw:
            mock_gw.deprovision_application = AsyncMock(
                side_effect=RuntimeError("not found")
            )

            from src.services.provisioning_service import deprovision_on_revocation

            await deprovision_on_revocation(db, sub, "jwt-token", "corr-300")

        assert sub.provisioning_status == ProvisioningStatus.FAILED
        assert "not found" in sub.provisioning_error


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
