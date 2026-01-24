"""
Tests for Subscriptions Router - CAB-839

Target: 80%+ coverage on src/routers/subscriptions.py
Tests: 12 test cases covering CRUD, lifecycle, and authorization
"""

import pytest
from datetime import datetime, timedelta
from enum import Enum
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


# Mock SubscriptionStatus enum to match the actual model
class SubscriptionStatus(str, Enum):
    """Mock SubscriptionStatus for testing - mirrors src.models.subscription.SubscriptionStatus"""
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    EXPIRED = "expired"


class TestSubscriptionsRouter:
    """Test suite for Subscriptions Router endpoints."""

    # ============== Helper Methods ==============

    def _create_mock_subscription(self, data: dict) -> MagicMock:
        """Create a mock Subscription object from data dict."""
        mock = MagicMock()
        for key, value in data.items():
            setattr(mock, key, value)
        return mock

    # ============== Create Subscription Tests ==============

    def test_create_subscription_success(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test successful subscription creation returns API key."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db

        mock_sub = self._create_mock_subscription(sample_subscription_data)

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.APIKeyService") as MockKeyService, \
             patch("src.routers.subscriptions.emit_subscription_created", new_callable=AsyncMock):

            # Configure mocks
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_application_and_api = AsyncMock(return_value=None)
            mock_repo_instance.create = AsyncMock(return_value=mock_sub)

            MockKeyService.generate_key.return_value = (
                "stoa_sk_test1234567890abcdef12345678",
                "hashed_key_test_123",
                "stoa_sk_tes",
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/subscriptions",
                    json={
                        "application_id": "app-test-123",
                        "application_name": "Test Application",
                        "api_id": "api-weather-456",
                        "api_name": "Weather API",
                        "api_version": "1.0",
                        "tenant_id": "acme",
                        "plan_id": "basic",
                        "plan_name": "Basic Plan",
                    },
                )

            assert response.status_code == 201
            data = response.json()
            assert "api_key" in data
            assert data["api_key"].startswith("stoa_sk_")
            assert "subscription_id" in data
            assert data["api_key_prefix"] == "stoa_sk_tes"

    def test_create_subscription_duplicate_409(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test duplicate subscription returns 409 Conflict."""
        mock_existing = self._create_mock_subscription(sample_subscription_data)
        mock_existing.status = SubscriptionStatus.ACTIVE

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_application_and_api = AsyncMock(return_value=mock_existing)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/subscriptions",
                    json={
                        "application_id": "app-test-123",
                        "application_name": "Test Application",
                        "api_id": "api-weather-456",
                        "api_name": "Weather API",
                        "api_version": "1.0",
                        "tenant_id": "acme",
                    },
                )

            assert response.status_code == 409
            assert "already exists" in response.json()["detail"]

    # ============== List My Subscriptions Tests ==============

    def test_list_my_subscriptions(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test listing current user's subscriptions with pagination."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_subscriber = AsyncMock(return_value=([mock_sub], 1))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/subscriptions/my?page=1&page_size=20")

            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert data["total"] == 1
            assert data["page"] == 1
            assert data["page_size"] == 20

    # ============== Get Subscription Tests ==============

    def test_get_subscription_by_id(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test getting subscription details by ID."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/subscriptions/{sample_subscription_data['id']}")

            assert response.status_code == 200
            data = response.json()
            assert data["application_name"] == "Test Application"
            assert data["api_name"] == "Weather API"

    def test_get_subscription_404(self, app_with_tenant_admin, mock_db_session):
        """Test getting non-existent subscription returns 404."""
        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(f"/v1/subscriptions/{uuid4()}")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_get_subscription_403_wrong_tenant(
        self, app_with_other_tenant, mock_db_session, sample_subscription_data
    ):
        """Test user from different tenant cannot access subscription."""
        # Subscription belongs to 'acme' tenant
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.subscriber_id = "different-user-id"  # Not the current user
        mock_sub.tenant_id = "acme"  # Belongs to acme, user is from other-tenant

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_other_tenant) as client:
                response = client.get(f"/v1/subscriptions/{sample_subscription_data['id']}")

            assert response.status_code == 403
            assert "Access denied" in response.json()["detail"]

    # ============== Cancel Subscription Tests ==============

    def test_cancel_subscription_success(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data, mock_user_tenant_admin
    ):
        """Test subscriber can cancel their own subscription."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.subscriber_id = mock_user_tenant_admin.id
        mock_sub.status = SubscriptionStatus.ACTIVE

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)
            mock_repo_instance.update_status = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"/v1/subscriptions/{sample_subscription_data['id']}")

            assert response.status_code == 204

    def test_cancel_subscription_403_not_owner(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test non-owner cannot cancel subscription."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.subscriber_id = "different-user-id"  # Not the current user
        mock_sub.status = SubscriptionStatus.ACTIVE

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"/v1/subscriptions/{sample_subscription_data['id']}")

            assert response.status_code == 403
            assert "Access denied" in response.json()["detail"]

    # ============== Approve Subscription Tests ==============

    def test_approve_subscription_admin(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test admin can approve pending subscription (PENDING -> ACTIVE)."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.PENDING

        # Create updated mock for after approval
        mock_approved = self._create_mock_subscription(sample_subscription_data)
        mock_approved.status = SubscriptionStatus.ACTIVE

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.emit_subscription_approved", new_callable=AsyncMock):
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)
            mock_repo_instance.update_status = AsyncMock(return_value=mock_approved)
            mock_repo_instance.set_expiration = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/approve",
                    json={},
                )

            assert response.status_code == 200

    def test_approve_subscription_400_wrong_status(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test cannot approve subscription that is not PENDING."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE  # Already active

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/approve",
                    json={},
                )

            assert response.status_code == 400
            assert "Cannot approve subscription in active status" in response.json()["detail"]

    # ============== Revoke Subscription Tests ==============

    def test_revoke_subscription_with_reason(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test admin can revoke active subscription with reason."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE

        mock_revoked = self._create_mock_subscription(sample_subscription_data)
        mock_revoked.status = SubscriptionStatus.REVOKED

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.emit_subscription_revoked", new_callable=AsyncMock):
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)
            mock_repo_instance.update_status = AsyncMock(return_value=mock_revoked)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/revoke",
                    json={"reason": "Policy violation"},
                )

            assert response.status_code == 200

    # ============== Validate API Key Tests ==============

    def test_validate_api_key_success(self, app, mock_db_session, sample_subscription_data):
        """Test gateway can validate active subscription API key."""
        from src.database import get_db

        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE
        mock_sub.expires_at = None
        mock_sub.previous_key_expires_at = None

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.APIKeyService") as MockKeyService:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_api_key_hash = AsyncMock(return_value=mock_sub)
            mock_repo_instance.get_by_previous_key_hash = AsyncMock(return_value=None)

            MockKeyService.validate_format.return_value = True
            MockKeyService.hash_key.return_value = "hashed_key_test_123"

            with TestClient(app) as client:
                response = client.post(
                    "/v1/subscriptions/validate-key?api_key=stoa_sk_test1234567890abcdef12345678"
                )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            assert data["subscription_id"] == str(sample_subscription_data["id"])
            assert data["api_name"] == "Weather API"
            assert data["tenant_id"] == "acme"

        app.dependency_overrides.clear()

    # ============== Phase 2: Suspend/Reactivate Tests ==============

    def test_suspend_subscription_success(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test admin can suspend active subscription."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE

        mock_suspended = self._create_mock_subscription(sample_subscription_data)
        mock_suspended.status = SubscriptionStatus.SUSPENDED

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)
            mock_repo_instance.update_status = AsyncMock(return_value=mock_suspended)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/suspend"
                )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "suspended"

    def test_suspend_subscription_404(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test suspending non-existent subscription returns 404."""
        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(f"/v1/subscriptions/{uuid4()}/suspend")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_suspend_subscription_400_wrong_status(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test cannot suspend non-ACTIVE subscription."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.PENDING

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/suspend"
                )

            assert response.status_code == 400
            assert "Cannot suspend subscription" in response.json()["detail"]

    def test_reactivate_subscription_success(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test admin can reactivate suspended subscription."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.SUSPENDED

        mock_reactivated = self._create_mock_subscription(sample_subscription_data)
        mock_reactivated.status = SubscriptionStatus.ACTIVE

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)
            mock_repo_instance.update_status = AsyncMock(return_value=mock_reactivated)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/reactivate"
                )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "active"

    def test_reactivate_subscription_404(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test reactivating non-existent subscription returns 404."""
        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(f"/v1/subscriptions/{uuid4()}/reactivate")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_reactivate_subscription_400_wrong_status(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test cannot reactivate non-SUSPENDED subscription."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/reactivate"
                )

            assert response.status_code == 400
            assert "Cannot reactivate subscription" in response.json()["detail"]

    # ============== Phase 2: Rotate-Key Tests ==============

    def test_rotate_api_key_success(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data, mock_user_tenant_admin
    ):
        """Test API key rotation on ACTIVE subscription returns new key."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE
        mock_sub.subscriber_id = mock_user_tenant_admin.id
        mock_sub.previous_key_expires_at = None

        mock_rotated = self._create_mock_subscription(sample_subscription_data)
        mock_rotated.status = SubscriptionStatus.ACTIVE
        mock_rotated.rotation_count = 1
        mock_rotated.previous_key_expires_at = datetime.utcnow() + timedelta(hours=24)

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.APIKeyService") as MockKeyService, \
             patch("src.routers.subscriptions.email_service") as MockEmail, \
             patch("src.routers.subscriptions.emit_subscription_key_rotated", new_callable=AsyncMock):
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)
            mock_repo_instance.rotate_key = AsyncMock(return_value=mock_rotated)

            MockKeyService.generate_key.return_value = (
                "stoa_sk_new1234567890abcdef12345678",
                "new_hashed_key",
                "stoa_sk_new",
            )
            MockEmail.send_key_rotation_notification = AsyncMock()

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/rotate-key",
                    json={"grace_period_hours": 24}
                )

            assert response.status_code == 200
            data = response.json()
            assert data["new_api_key"].startswith("stoa_sk_")
            assert data["rotation_count"] == 1

    def test_rotate_api_key_404(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test rotating key on non-existent subscription returns 404."""
        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(f"/v1/subscriptions/{uuid4()}/rotate-key")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_rotate_api_key_400_wrong_status(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data, mock_user_tenant_admin
    ):
        """Test cannot rotate key on non-ACTIVE subscription."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.PENDING
        mock_sub.subscriber_id = mock_user_tenant_admin.id

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/rotate-key"
                )

            assert response.status_code == 400
            assert "Cannot rotate key" in response.json()["detail"]

    def test_rotate_api_key_400_grace_period_active(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data, mock_user_tenant_admin
    ):
        """Test cannot rotate key while grace period is active."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE
        mock_sub.subscriber_id = mock_user_tenant_admin.id
        mock_sub.previous_key_expires_at = datetime.utcnow() + timedelta(hours=12)

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/rotate-key"
                )

            assert response.status_code == 400
            assert "already in progress" in response.json()["detail"]

    def test_get_rotation_info_success(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data, mock_user_tenant_admin
    ):
        """Test getting rotation info with grace period details."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE
        mock_sub.subscriber_id = mock_user_tenant_admin.id
        mock_sub.previous_key_expires_at = None
        mock_sub.rotation_count = 2
        mock_sub.last_rotated_at = datetime.utcnow() - timedelta(days=7)

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_tenant_admin) as client:
                response = client.get(
                    f"/v1/subscriptions/{sample_subscription_data['id']}/rotation-info"
                )

            assert response.status_code == 200
            data = response.json()
            assert "has_active_grace_period" in data

    # ============== Phase 2: Validate-Key Error Tests ==============

    def test_validate_api_key_401_invalid_format(self, app, mock_db_session):
        """Test validation fails with invalid API key format."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        with patch("src.routers.subscriptions.APIKeyService") as MockKeyService:
            MockKeyService.validate_format.return_value = False

            with TestClient(app) as client:
                response = client.post(
                    "/v1/subscriptions/validate-key?api_key=invalid_key_format"
                )

            assert response.status_code == 401
            assert "Invalid API key format" in response.json()["detail"]

        app.dependency_overrides.clear()

    def test_validate_api_key_401_not_found(self, app, mock_db_session):
        """Test validation fails when API key not found."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.APIKeyService") as MockKeyService:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_api_key_hash = AsyncMock(return_value=None)
            mock_repo_instance.get_by_previous_key_hash = AsyncMock(return_value=None)

            MockKeyService.validate_format.return_value = True
            MockKeyService.hash_key.return_value = "unknown_hash"

            with TestClient(app) as client:
                response = client.post(
                    "/v1/subscriptions/validate-key?api_key=stoa_sk_unknown1234567890abcdef"
                )

            assert response.status_code == 401
            assert "API key not found" in response.json()["detail"]

        app.dependency_overrides.clear()

    def test_validate_api_key_403_suspended(self, app, mock_db_session, sample_subscription_data):
        """Test validation fails for suspended subscription."""
        from src.database import get_db

        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.SUSPENDED

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.APIKeyService") as MockKeyService:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_api_key_hash = AsyncMock(return_value=mock_sub)

            MockKeyService.validate_format.return_value = True
            MockKeyService.hash_key.return_value = "hashed_key_test_123"

            with TestClient(app) as client:
                response = client.post(
                    "/v1/subscriptions/validate-key?api_key=stoa_sk_test1234567890abcdef12345678"
                )

            assert response.status_code == 403
            assert "suspended" in response.json()["detail"]

        app.dependency_overrides.clear()

    # ============== Phase 2: Cancel Subscription 404 Test ==============

    def test_cancel_subscription_404(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Test cancelling non-existent subscription returns 404."""
        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=None)

            with TestClient(app_with_tenant_admin) as client:
                response = client.delete(f"/v1/subscriptions/{uuid4()}")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    # ============== Phase 3: CPI-Admin Cross-Tenant Access (Line 42) ==============

    def test_get_subscription_cpi_admin_cross_tenant(
        self, app_with_cpi_admin, mock_db_session, sample_subscription_data
    ):
        """Test CPI admin can access any tenant's subscription."""
        # Subscription belongs to 'acme' tenant but CPI admin can still access it
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.subscriber_id = "different-user-id"  # Not the current user
        mock_sub.tenant_id = "acme"

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_id = AsyncMock(return_value=mock_sub)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/subscriptions/{sample_subscription_data['id']}")

            # CPI admin should have access via _has_tenant_access returning True for cpi-admin role
            assert response.status_code == 200
            data = response.json()
            assert data["tenant_id"] == "acme"

    # ============== Phase 3: Create Subscription Failure Handling (Lines 108-113) ==============

    def test_create_subscription_webhook_failure(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test create succeeds but webhook emission fails gracefully."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.APIKeyService") as MockKeyService, \
             patch("src.routers.subscriptions.emit_subscription_created", new_callable=AsyncMock) as mock_emit:

            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_application_and_api = AsyncMock(return_value=None)
            mock_repo_instance.create = AsyncMock(return_value=mock_sub)

            MockKeyService.generate_key.return_value = (
                "stoa_sk_test1234567890abcdef12345678",
                "hashed_key_test_123",
                "stoa_sk_tes",
            )

            # Make webhook emit raise an exception (should be caught silently)
            mock_emit.side_effect = Exception("Webhook service unavailable")

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/subscriptions",
                    json={
                        "application_id": "app-test-123",
                        "application_name": "Test Application",
                        "api_id": "api-weather-456",
                        "api_name": "Weather API",
                        "api_version": "1.0",
                        "tenant_id": "acme",
                    },
                )

            # Should still succeed despite webhook failure
            assert response.status_code == 201
            assert "api_key" in response.json()

    def test_create_subscription_db_error(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test create fails on database error → 500."""
        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.APIKeyService") as MockKeyService:

            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_application_and_api = AsyncMock(return_value=None)
            mock_repo_instance.create = AsyncMock(side_effect=Exception("Database connection failed"))

            MockKeyService.generate_key.return_value = (
                "stoa_sk_test1234567890abcdef12345678",
                "hashed_key_test_123",
                "stoa_sk_tes",
            )

            with TestClient(app_with_tenant_admin) as client:
                response = client.post(
                    "/v1/subscriptions",
                    json={
                        "application_id": "app-test-123",
                        "application_name": "Test Application",
                        "api_id": "api-weather-456",
                        "api_name": "Weather API",
                        "api_version": "1.0",
                        "tenant_id": "acme",
                    },
                )

            assert response.status_code == 500
            assert "Failed to create subscription" in response.json()["detail"]

    # ============== Phase 3: Tenant/Pending Subscriptions (Lines 359-411) ==============

    def test_list_tenant_subscriptions_success(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test GET /tenant/{tenant_id} returns tenant's subscriptions."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_by_tenant = AsyncMock(return_value=([mock_sub], 1))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/subscriptions/tenant/acme?page=1&page_size=20")

            assert response.status_code == 200
            data = response.json()
            assert "items" in data
            assert data["total"] == 1
            assert len(data["items"]) == 1

    def test_list_tenant_subscriptions_403_wrong_tenant(
        self, app_with_other_tenant, mock_db_session
    ):
        """Test GET /tenant/{tenant_id} from other tenant → 403."""
        # User is from 'other-tenant', trying to access 'acme' tenant's subscriptions
        with TestClient(app_with_other_tenant) as client:
            response = client.get("/v1/subscriptions/tenant/acme")

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    def test_list_pending_subscriptions_success(
        self, app_with_tenant_admin, mock_db_session, sample_subscription_data
    ):
        """Test GET /tenant/{tenant_id}/pending returns pending only."""
        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.PENDING

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.list_pending = AsyncMock(return_value=([mock_sub], 1))

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/subscriptions/tenant/acme/pending")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 1
            assert data["items"][0]["status"] == "pending"

    # ============== Phase 3: Validate-Key Grace Period (Lines 617-658) ==============

    def test_validate_api_key_previous_key_valid(self, app, mock_db_session, sample_subscription_data):
        """Test POST /validate-key with previous key during grace period → 200."""
        from src.database import get_db

        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE
        mock_sub.expires_at = None
        mock_sub.previous_key_expires_at = datetime.utcnow() + timedelta(hours=12)  # Still in grace period

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.APIKeyService") as MockKeyService:
            mock_repo_instance = MockRepo.return_value
            # Current key lookup returns None (key was rotated)
            mock_repo_instance.get_by_api_key_hash = AsyncMock(return_value=None)
            # Previous key lookup returns the subscription (old key during grace period)
            mock_repo_instance.get_by_previous_key_hash = AsyncMock(return_value=mock_sub)

            MockKeyService.validate_format.return_value = True
            MockKeyService.hash_key.return_value = "old_hashed_key"

            with TestClient(app) as client:
                response = client.post(
                    "/v1/subscriptions/validate-key?api_key=stoa_sk_old1234567890abcdef12345678"
                )

            assert response.status_code == 200
            data = response.json()
            assert data["valid"] is True
            # Should have grace period warning since using old key
            assert data.get("using_previous_key") is True
            assert "warning" in data
            assert "key_expires_at" in data

        app.dependency_overrides.clear()

    def test_validate_api_key_subscription_expired(self, app, mock_db_session, sample_subscription_data):
        """Test POST /validate-key on expired subscription → 403."""
        from src.database import get_db

        mock_sub = self._create_mock_subscription(sample_subscription_data)
        mock_sub.status = SubscriptionStatus.ACTIVE
        mock_sub.expires_at = datetime.utcnow() - timedelta(days=1)  # Expired yesterday
        mock_sub.previous_key_expires_at = None

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        with patch("src.routers.subscriptions.SubscriptionRepository") as MockRepo, \
             patch("src.routers.subscriptions.APIKeyService") as MockKeyService:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_by_api_key_hash = AsyncMock(return_value=mock_sub)

            MockKeyService.validate_format.return_value = True
            MockKeyService.hash_key.return_value = "hashed_key_test_123"

            with TestClient(app) as client:
                response = client.post(
                    "/v1/subscriptions/validate-key?api_key=stoa_sk_test1234567890abcdef12345678"
                )

            assert response.status_code == 403
            assert "expired" in response.json()["detail"]

        app.dependency_overrides.clear()
