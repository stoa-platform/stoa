"""
Tests for TenantProvisioningService — CAB-1315.

Target: saga-based provisioning + deprovisioning.
Tests: 18 test cases covering happy path, failure modes, best-effort steps.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.tenant import TenantProvisioningStatus, TenantStatus


def _make_mock_tenant(
    tenant_id="acme",
    name="ACME Corp",
    status="active",
    provisioning_status="pending",
    provisioning_attempts=0,
    kc_group_id=None,
    provisioning_error=None,
):
    """Create a mock Tenant ORM object for service tests."""
    tenant = MagicMock()
    tenant.id = tenant_id
    tenant.name = name
    tenant.status = status
    tenant.provisioning_status = provisioning_status
    tenant.provisioning_started_at = None
    tenant.provisioning_attempts = provisioning_attempts
    tenant.kc_group_id = kc_group_id
    tenant.provisioning_error = provisioning_error
    return tenant


@pytest.fixture
def mock_db():
    """Mock DB session for provisioning service (mimics get_db generator)."""
    from sqlalchemy.ext.asyncio import AsyncSession

    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_tenant_repo():
    repo = MagicMock()
    return repo


class TestProvisionTenant:
    """Test provision_tenant saga."""

    @pytest.mark.asyncio
    async def test_provision_happy_path(self, mock_db, mock_tenant_repo):
        """All steps succeed → status READY."""
        tenant = _make_mock_tenant()
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch("src.services.tenant_provisioning_service.kafka_service") as mock_kafka,
            patch(
                "src.services.tenant_provisioning_service._seed_default_rate_limit_policy",
                new_callable=AsyncMock,
            ) as mock_seed,
        ):
            mock_kc.setup_tenant_group = AsyncMock(return_value="group-123")
            mock_kc.create_user = AsyncMock(return_value="user-123")
            mock_kc.add_user_to_tenant = AsyncMock()
            mock_kafka.publish = AsyncMock()

            from src.services.tenant_provisioning_service import provision_tenant

            await provision_tenant("acme", "admin@acme.com", "ACME Corp", "corr-1")

        # Verify status set to READY
        assert tenant.provisioning_status == TenantProvisioningStatus.READY.value
        assert tenant.kc_group_id == "group-123"
        assert tenant.provisioning_attempts == 1

        # Verify KC calls
        mock_kc.setup_tenant_group.assert_awaited_once_with("acme", "ACME Corp")
        mock_kc.create_user.assert_awaited_once()
        mock_kc.add_user_to_tenant.assert_awaited_once()

        # Verify Kafka events (3 total)
        assert mock_kafka.publish.await_count == 3

        # Verify policy seed
        mock_seed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_provision_kc_group_failure_sets_failed(self, mock_db, mock_tenant_repo):
        """KC group creation fails after retries → status FAILED."""
        tenant = _make_mock_tenant()
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch(
                "src.services.tenant_provisioning_service._retry_kc_group",
                new_callable=AsyncMock,
                side_effect=Exception("KC unavailable"),
            ),
            patch("src.services.tenant_provisioning_service.kafka_service"),
        ):
            from src.services.tenant_provisioning_service import provision_tenant

            await provision_tenant("acme", "admin@acme.com", "ACME Corp", "corr-1")

        assert tenant.provisioning_status == TenantProvisioningStatus.FAILED.value
        assert "KC group creation failed" in tenant.provisioning_error

    @pytest.mark.asyncio
    async def test_provision_user_creation_failure_continues(self, mock_db, mock_tenant_repo):
        """Admin user creation fails → saga continues to READY (best-effort)."""
        tenant = _make_mock_tenant()
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch("src.services.tenant_provisioning_service.kafka_service") as mock_kafka,
            patch(
                "src.services.tenant_provisioning_service._seed_default_rate_limit_policy",
                new_callable=AsyncMock,
            ),
        ):
            mock_kc.setup_tenant_group = AsyncMock(return_value="group-123")
            mock_kc.create_user = AsyncMock(side_effect=Exception("User creation failed"))
            mock_kc.add_user_to_tenant = AsyncMock()
            mock_kafka.publish = AsyncMock()

            from src.services.tenant_provisioning_service import provision_tenant

            await provision_tenant("acme", "admin@acme.com", "ACME Corp", "corr-1")

        # Should still reach READY
        assert tenant.provisioning_status == TenantProvisioningStatus.READY.value

    @pytest.mark.asyncio
    async def test_provision_add_user_to_tenant_failure_continues(self, mock_db, mock_tenant_repo):
        """Add user to tenant fails → saga continues to READY."""
        tenant = _make_mock_tenant()
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch("src.services.tenant_provisioning_service.kafka_service") as mock_kafka,
            patch(
                "src.services.tenant_provisioning_service._seed_default_rate_limit_policy",
                new_callable=AsyncMock,
            ),
        ):
            mock_kc.setup_tenant_group = AsyncMock(return_value="group-123")
            mock_kc.create_user = AsyncMock(return_value="user-123")
            mock_kc.add_user_to_tenant = AsyncMock(side_effect=Exception("Add failed"))
            mock_kafka.publish = AsyncMock()

            from src.services.tenant_provisioning_service import provision_tenant

            await provision_tenant("acme", "admin@acme.com", "ACME Corp", "corr-1")

        assert tenant.provisioning_status == TenantProvisioningStatus.READY.value

    @pytest.mark.asyncio
    async def test_provision_policy_seed_failure_continues(self, mock_db, mock_tenant_repo):
        """Policy seed fails → saga continues to READY."""
        tenant = _make_mock_tenant()
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch("src.services.tenant_provisioning_service.kafka_service") as mock_kafka,
            patch(
                "src.services.tenant_provisioning_service._seed_default_rate_limit_policy",
                new_callable=AsyncMock,
                side_effect=Exception("Policy seed error"),
            ),
        ):
            mock_kc.setup_tenant_group = AsyncMock(return_value="group-123")
            mock_kc.create_user = AsyncMock(return_value="user-123")
            mock_kc.add_user_to_tenant = AsyncMock()
            mock_kafka.publish = AsyncMock()

            from src.services.tenant_provisioning_service import provision_tenant

            await provision_tenant("acme", "admin@acme.com", "ACME Corp", "corr-1")

        assert tenant.provisioning_status == TenantProvisioningStatus.READY.value

    @pytest.mark.asyncio
    async def test_provision_kafka_failure_continues(self, mock_db, mock_tenant_repo):
        """Kafka events fail → saga continues to READY."""
        tenant = _make_mock_tenant()
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch("src.services.tenant_provisioning_service.kafka_service") as mock_kafka,
            patch(
                "src.services.tenant_provisioning_service._seed_default_rate_limit_policy",
                new_callable=AsyncMock,
            ),
        ):
            mock_kc.setup_tenant_group = AsyncMock(return_value="group-123")
            mock_kc.create_user = AsyncMock(return_value="user-123")
            mock_kc.add_user_to_tenant = AsyncMock()
            mock_kafka.publish = AsyncMock(side_effect=Exception("Kafka down"))

            from src.services.tenant_provisioning_service import provision_tenant

            await provision_tenant("acme", "admin@acme.com", "ACME Corp", "corr-1")

        assert tenant.provisioning_status == TenantProvisioningStatus.READY.value

    @pytest.mark.asyncio
    async def test_provision_tenant_not_found(self, mock_db, mock_tenant_repo):
        """Tenant not found → early return, no error."""
        mock_tenant_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
        ):
            from src.services.tenant_provisioning_service import provision_tenant

            await provision_tenant("missing", "a@b.com", "Missing", "corr-1")

        # Should not raise, just return early

    @pytest.mark.asyncio
    async def test_provision_increments_attempts(self, mock_db, mock_tenant_repo):
        """Provisioning attempts counter is incremented."""
        tenant = _make_mock_tenant(provisioning_attempts=2)
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch("src.services.tenant_provisioning_service.kafka_service") as mock_kafka,
            patch(
                "src.services.tenant_provisioning_service._seed_default_rate_limit_policy",
                new_callable=AsyncMock,
            ),
        ):
            mock_kc.setup_tenant_group = AsyncMock(return_value="group-123")
            mock_kc.create_user = AsyncMock(return_value="user-123")
            mock_kc.add_user_to_tenant = AsyncMock()
            mock_kafka.publish = AsyncMock()

            from src.services.tenant_provisioning_service import provision_tenant

            await provision_tenant("acme", "admin@acme.com", "ACME Corp", "corr-1")

        assert tenant.provisioning_attempts == 3


class TestRetryKcGroup:
    """Test _retry_kc_group retry logic."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_first_attempt(self):
        """KC group creation succeeds on first try."""
        with patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc:
            mock_kc.setup_tenant_group = AsyncMock(return_value="group-abc")

            from src.services.tenant_provisioning_service import _retry_kc_group

            result = await _retry_kc_group("acme", "ACME")

        assert result == "group-abc"
        assert mock_kc.setup_tenant_group.await_count == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_second_attempt(self):
        """KC group creation fails once, succeeds on retry."""
        with (
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch(
                "src.services.tenant_provisioning_service.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            mock_kc.setup_tenant_group = AsyncMock(side_effect=[Exception("Timeout"), "group-abc"])

            from src.services.tenant_provisioning_service import _retry_kc_group

            result = await _retry_kc_group("acme", "ACME")

        assert result == "group-abc"
        assert mock_kc.setup_tenant_group.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        """All retries fail → raises last error."""
        with (
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch(
                "src.services.tenant_provisioning_service.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            mock_kc.setup_tenant_group = AsyncMock(side_effect=Exception("KC down"))

            from src.services.tenant_provisioning_service import _retry_kc_group

            with pytest.raises(Exception, match="KC down"):
                await _retry_kc_group("acme", "ACME")

        assert mock_kc.setup_tenant_group.await_count == 3


class TestSeedDefaultRateLimitPolicy:
    """Test _seed_default_rate_limit_policy."""

    @pytest.mark.asyncio
    async def test_seed_creates_policy(self, mock_db):
        """Policy seed creates a GatewayPolicy with correct config."""
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock()

        with patch(
            "src.services.tenant_provisioning_service.GatewayPolicyRepository",
            return_value=mock_repo,
        ):
            from src.services.tenant_provisioning_service import (
                _seed_default_rate_limit_policy,
            )

            await _seed_default_rate_limit_policy(mock_db, "acme")

        mock_repo.create.assert_awaited_once()
        created_policy = mock_repo.create.call_args[0][0]
        assert created_policy.tenant_id == "acme"
        assert created_policy.name == "default-rate-limit-acme"
        assert created_policy.config["maxRequests"] == 100
        assert created_policy.config["intervalSeconds"] == 60
        assert created_policy.enabled is True


class TestDeprovisionTenant:
    """Test deprovision_tenant reverse saga."""

    @pytest.mark.asyncio
    async def test_deprovision_happy_path(self, mock_db, mock_tenant_repo):
        """All deprovision steps succeed → tenant archived."""
        tenant = _make_mock_tenant(status="active")
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        mock_policy = MagicMock()
        mock_policy.enabled = True
        mock_policy_repo = MagicMock()
        mock_policy_repo.list_all = AsyncMock(return_value=[mock_policy])

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch(
                "src.services.tenant_provisioning_service.GatewayPolicyRepository",
                return_value=mock_policy_repo,
            ),
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch("src.services.tenant_provisioning_service.kafka_service") as mock_kafka,
        ):
            mock_kc.delete_tenant_group = AsyncMock()
            mock_kafka.publish = AsyncMock()

            from src.services.tenant_provisioning_service import deprovision_tenant

            await deprovision_tenant("acme", "user-1", "corr-1")

        assert tenant.status == TenantStatus.ARCHIVED.value
        assert mock_policy.enabled is False
        mock_kc.delete_tenant_group.assert_awaited_once_with("acme")
        # 3 kafka events: deprovisioning-started, namespace-cleanup, deprovisioned
        assert mock_kafka.publish.await_count == 3

    @pytest.mark.asyncio
    async def test_deprovision_tenant_not_found(self, mock_db, mock_tenant_repo):
        """Tenant not found → early return."""
        mock_tenant_repo.get_by_id = AsyncMock(return_value=None)

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
        ):
            from src.services.tenant_provisioning_service import deprovision_tenant

            await deprovision_tenant("missing", "user-1", "corr-1")

    @pytest.mark.asyncio
    async def test_deprovision_kc_failure_continues(self, mock_db, mock_tenant_repo):
        """KC group deletion fails → saga continues, tenant still archived."""
        tenant = _make_mock_tenant()
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        mock_policy_repo = MagicMock()
        mock_policy_repo.list_all = AsyncMock(return_value=[])

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch(
                "src.services.tenant_provisioning_service.GatewayPolicyRepository",
                return_value=mock_policy_repo,
            ),
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch("src.services.tenant_provisioning_service.kafka_service") as mock_kafka,
        ):
            mock_kc.delete_tenant_group = AsyncMock(side_effect=Exception("KC down"))
            mock_kafka.publish = AsyncMock()

            from src.services.tenant_provisioning_service import deprovision_tenant

            await deprovision_tenant("acme", "user-1", "corr-1")

        assert tenant.status == TenantStatus.ARCHIVED.value

    @pytest.mark.asyncio
    async def test_deprovision_policy_disable_failure_continues(self, mock_db, mock_tenant_repo):
        """Policy disable fails → saga continues, tenant still archived."""
        tenant = _make_mock_tenant()
        mock_tenant_repo.get_by_id = AsyncMock(return_value=tenant)

        mock_policy_repo = MagicMock()
        mock_policy_repo.list_all = AsyncMock(side_effect=Exception("DB error"))

        with (
            patch(
                "src.services.tenant_provisioning_service.get_db",
                return_value=_async_gen(mock_db),
            ),
            patch(
                "src.services.tenant_provisioning_service.TenantRepository",
                return_value=mock_tenant_repo,
            ),
            patch(
                "src.services.tenant_provisioning_service.GatewayPolicyRepository",
                return_value=mock_policy_repo,
            ),
            patch("src.services.tenant_provisioning_service.keycloak_service") as mock_kc,
            patch("src.services.tenant_provisioning_service.kafka_service") as mock_kafka,
        ):
            mock_kc.delete_tenant_group = AsyncMock()
            mock_kafka.publish = AsyncMock()

            from src.services.tenant_provisioning_service import deprovision_tenant

            await deprovision_tenant("acme", "user-1", "corr-1")

        assert tenant.status == TenantStatus.ARCHIVED.value


# ============== Helper ==============


async def _async_gen(value):
    """Create an async generator that yields a single value (mimics get_db)."""
    yield value
