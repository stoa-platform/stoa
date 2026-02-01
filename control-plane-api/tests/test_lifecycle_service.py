"""Tests for Tenant Lifecycle Service -- CAB-409"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.lifecycle.models import (
    TenantLifecycleState,
    NotificationType,
    TRIAL_DURATION_DAYS,
    WARNING_THRESHOLD_DAYS,
    EXTENSION_DAYS,
    MAX_EXTENSIONS,
)
from src.lifecycle.service import TenantLifecycleService, LifecycleError, TenantNotFoundError
from src.models.tenant import TenantStatus


@pytest.fixture
def mock_tenant():
    tenant = MagicMock()
    tenant.id = "test-tenant-001"
    tenant.name = "Test Corp"
    tenant.settings = {"owner_email": "admin@test.com"}
    tenant.created_at = datetime.now(timezone.utc) - timedelta(days=5)
    tenant.trial_expires_at = datetime.now(timezone.utc) + timedelta(days=9)
    tenant.lifecycle_state = TenantLifecycleState.ACTIVE
    tenant.trial_extended_count = 0
    tenant.lifecycle_changed_at = datetime.now(timezone.utc)
    tenant.status = TenantStatus.ACTIVE.value
    return tenant


@pytest.fixture
def lifecycle_service():
    db = AsyncMock()
    notif = AsyncMock()
    cleanup = AsyncMock()
    return TenantLifecycleService(db, notif, cleanup)


class TestLifecycleStates:
    @pytest.mark.asyncio
    async def test_active_tenant_status(self, lifecycle_service, mock_tenant):
        lifecycle_service._get_tenant = AsyncMock(return_value=mock_tenant)
        status = await lifecycle_service.get_status("test-tenant-001")
        assert status.state == TenantLifecycleState.ACTIVE
        assert status.days_left > 0
        assert status.can_extend is True
        assert status.is_read_only is False

    @pytest.mark.asyncio
    async def test_extend_trial_success(self, lifecycle_service, mock_tenant):
        lifecycle_service._get_tenant = AsyncMock(return_value=mock_tenant)
        lifecycle_service.db.commit = AsyncMock()
        result = await lifecycle_service.extend_trial("test-tenant-001", reason="Need more time")
        assert result.extensions_remaining == MAX_EXTENSIONS - 1
        assert mock_tenant.trial_extended_count == 1

    @pytest.mark.asyncio
    async def test_extend_trial_already_extended(self, lifecycle_service, mock_tenant):
        mock_tenant.trial_extended_count = MAX_EXTENSIONS
        lifecycle_service._get_tenant = AsyncMock(return_value=mock_tenant)
        with pytest.raises(LifecycleError, match="Extension limit reached"):
            await lifecycle_service.extend_trial("test-tenant-001")

    @pytest.mark.asyncio
    async def test_extend_trial_expired_tenant(self, lifecycle_service, mock_tenant):
        mock_tenant.lifecycle_state = TenantLifecycleState.EXPIRED
        lifecycle_service._get_tenant = AsyncMock(return_value=mock_tenant)
        with pytest.raises(LifecycleError, match="Cannot extend"):
            await lifecycle_service.extend_trial("test-tenant-001")

    @pytest.mark.asyncio
    async def test_upgrade_success(self, lifecycle_service, mock_tenant):
        lifecycle_service._get_tenant = AsyncMock(return_value=mock_tenant)
        lifecycle_service.db.commit = AsyncMock()
        result = await lifecycle_service.upgrade_tenant("test-tenant-001", "enterprise")
        assert result.new_state == TenantLifecycleState.CONVERTED
        assert mock_tenant.lifecycle_state == TenantLifecycleState.CONVERTED

    @pytest.mark.asyncio
    async def test_upgrade_deleted_tenant_fails(self, lifecycle_service, mock_tenant):
        mock_tenant.lifecycle_state = TenantLifecycleState.DELETED
        lifecycle_service._get_tenant = AsyncMock(return_value=mock_tenant)
        with pytest.raises(LifecycleError, match="Cannot upgrade a deleted tenant"):
            await lifecycle_service.upgrade_tenant("test-tenant-001", "enterprise")


class TestStatusInvariant:
    """COUNCIL #4: Verify status/lifecycle_state invariant is enforced."""

    @pytest.mark.asyncio
    async def test_expired_sets_suspended(self, lifecycle_service, mock_tenant):
        lifecycle_service._get_tenant = AsyncMock(return_value=mock_tenant)
        lifecycle_service.db.commit = AsyncMock()

        # Simulate tenant in WARNING state with expired trial
        mock_tenant.lifecycle_state = TenantLifecycleState.WARNING
        mock_tenant.trial_expires_at = datetime.now(timezone.utc) - timedelta(days=1)

        # Manually transition to EXPIRED
        await lifecycle_service._transition(mock_tenant, TenantLifecycleState.EXPIRED, "cron")
        assert mock_tenant.status == TenantStatus.SUSPENDED.value

    @pytest.mark.asyncio
    async def test_deleted_sets_archived(self, lifecycle_service, mock_tenant):
        mock_tenant.lifecycle_state = TenantLifecycleState.EXPIRED
        await lifecycle_service._transition(mock_tenant, TenantLifecycleState.DELETED, "cron")
        assert mock_tenant.status == TenantStatus.ARCHIVED.value

    @pytest.mark.asyncio
    async def test_converted_keeps_active(self, lifecycle_service, mock_tenant):
        await lifecycle_service._transition(mock_tenant, TenantLifecycleState.CONVERTED, "self-service")
        assert mock_tenant.status == TenantStatus.ACTIVE.value


class TestNotificationSchedule:
    def test_all_notification_types_have_templates(self):
        from src.lifecycle.notifications import TEMPLATES
        for ntype in NotificationType:
            assert ntype in TEMPLATES, f"Missing template for {ntype.value}"
            assert "subject" in TEMPLATES[ntype]
            assert "body" in TEMPLATES[ntype]

    def test_templates_have_placeholders(self):
        from src.lifecycle.notifications import TEMPLATES
        for ntype, template in TEMPLATES.items():
            assert "{tenant_name}" in template["body"], f"{ntype}: missing tenant_name"
            assert "{portal_url}" in template["body"], f"{ntype}: missing portal_url"
