"""Tests for Subscriptions Router — CAB-1436

Covers: /v1/subscriptions CRUD, key rotation, TTL extension, admin approve/revoke/suspend/reactivate,
        tenant list, validate-key endpoint.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from src.models.subscription import SubscriptionStatus

SUB_REPO_PATH = "src.routers.subscriptions.SubscriptionRepository"
PLAN_REPO_PATH = "src.routers.subscriptions.PlanRepository"
API_KEY_SVC_PATH = "src.routers.subscriptions.APIKeyService"
EMAIL_SVC_PATH = "src.routers.subscriptions.email_service"
KAFKA_SVC_PATH = "src.routers.subscriptions.kafka_service"
PROVISION_PATH = "src.routers.subscriptions.provision_on_approval"
DEPROVISION_PATH = "src.routers.subscriptions.deprovision_on_revocation"
EMIT_CREATED_PATH = "src.routers.subscriptions.emit_subscription_created"
EMIT_APPROVED_PATH = "src.routers.subscriptions.emit_subscription_approved"
EMIT_REVOKED_PATH = "src.routers.subscriptions.emit_subscription_revoked"
EMIT_ROTATED_PATH = "src.routers.subscriptions.emit_subscription_key_rotated"


def _mock_subscription(**overrides):
    """Build a MagicMock that mimics a Subscription ORM object."""
    mock = MagicMock()
    sid = uuid4()
    defaults = {
        "id": sid,
        "application_id": "app-1",
        "application_name": "Test App",
        "subscriber_id": "tenant-admin-user-id",
        "subscriber_email": "admin@acme.com",
        "api_id": "api-1",
        "api_name": "Test API",
        "api_version": "1.0",
        "tenant_id": "acme",
        "plan_id": str(uuid4()),
        "plan_name": "Basic",
        "api_key_hash": "hash123",
        "api_key_prefix": "stoa_sk_",
        "status": SubscriptionStatus.ACTIVE,
        "status_reason": None,
        "expires_at": None,
        "previous_key_expires_at": None,
        "previous_api_key_hash": None,
        "last_rotated_at": None,
        "rotation_count": 0,
        "ttl_extension_count": 0,
        "ttl_total_extended_days": 0,
        "approved_at": None,
        "revoked_at": None,
        "approved_by": None,
        "revoked_by": None,
        "provisioning_status": "none",
        "gateway_app_id": None,
        "provisioning_error": None,
        "provisioned_at": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _mock_sub_response(sub):
    """Mock SubscriptionResponse from a subscription mock."""
    from src.schemas.subscription import SubscriptionStatusEnum

    resp = MagicMock()
    resp.id = sub.id
    resp.application_id = sub.application_id
    resp.application_name = sub.application_name
    resp.subscriber_id = sub.subscriber_id
    resp.subscriber_email = sub.subscriber_email
    resp.api_id = sub.api_id
    resp.api_name = sub.api_name
    resp.api_version = sub.api_version
    resp.tenant_id = sub.tenant_id
    resp.plan_id = sub.plan_id
    resp.plan_name = sub.plan_name
    resp.api_key_prefix = sub.api_key_prefix
    resp.status = SubscriptionStatusEnum(sub.status.value)
    resp.status_reason = sub.status_reason
    resp.created_at = sub.created_at
    resp.updated_at = sub.updated_at
    resp.approved_at = sub.approved_at
    resp.expires_at = sub.expires_at
    resp.revoked_at = sub.revoked_at
    resp.approved_by = sub.approved_by
    resp.revoked_by = sub.revoked_by
    resp.provisioning_status = sub.provisioning_status
    resp.gateway_app_id = sub.gateway_app_id
    resp.provisioning_error = sub.provisioning_error
    resp.provisioned_at = sub.provisioned_at
    return resp


# ============== Create Subscription ==============


class TestCreateSubscription:
    """POST /v1/subscriptions"""

    def test_create_success_auto_approve(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.ACTIVE)
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_application_and_api = AsyncMock(return_value=None)
        mock_sub_repo.create = AsyncMock(return_value=sub)
        mock_sub_repo.update_status = AsyncMock(return_value=sub)

        mock_plan_repo = MagicMock()
        mock_plan = MagicMock()
        mock_plan.requires_approval = False
        mock_plan_repo.get_by_id = AsyncMock(return_value=mock_plan)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(PLAN_REPO_PATH, return_value=mock_plan_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
            patch(EMIT_CREATED_PATH, new=AsyncMock()),
            patch(EMIT_APPROVED_PATH, new=AsyncMock()),
            patch(PROVISION_PATH, new=AsyncMock()),
        ):
            MockKey.generate_key.return_value = ("stoa_sk_fullkey", "hash", "stoa_sk_")
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(
                    "/v1/subscriptions",
                    json={
                        "application_id": "app-1",
                        "application_name": "Test App",
                        "api_id": "api-1",
                        "api_name": "Test API",
                        "api_version": "1.0",
                        "tenant_id": "acme",
                    },
                )

        assert resp.status_code == 201
        data = resp.json()
        assert "api_key" in data
        assert "subscription_id" in data

    def test_create_409_existing_subscription(self, app_with_tenant_admin, mock_db_session):
        existing = _mock_subscription()
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_application_and_api = AsyncMock(return_value=existing)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
        ):
            MockKey.generate_key.return_value = ("stoa_sk_fullkey", "hash", "stoa_sk_")
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(
                    "/v1/subscriptions",
                    json={
                        "application_id": "app-1",
                        "application_name": "Test App",
                        "api_id": "api-1",
                        "api_name": "Test API",
                        "api_version": "1.0",
                        "tenant_id": "acme",
                    },
                )

        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_create_no_plan_auto_approves(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.ACTIVE, plan_id=None)
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_application_and_api = AsyncMock(return_value=None)
        mock_sub_repo.create = AsyncMock(return_value=sub)
        mock_sub_repo.update_status = AsyncMock(return_value=sub)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
            patch(EMIT_CREATED_PATH, new=AsyncMock()),
            patch(EMIT_APPROVED_PATH, new=AsyncMock()),
            patch(PROVISION_PATH, new=AsyncMock()),
        ):
            MockKey.generate_key.return_value = ("stoa_sk_fullkey", "hash", "stoa_sk_")
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(
                    "/v1/subscriptions",
                    json={
                        "application_id": "app-1",
                        "application_name": "Test App",
                        "api_id": "api-1",
                        "api_name": "Test API",
                        "api_version": "1.0",
                        "tenant_id": "acme",
                        "plan_id": None,
                    },
                )

        assert resp.status_code == 201


# ============== List My Subscriptions ==============


class TestListMySubscriptions:
    """GET /v1/subscriptions/my"""

    def test_list_my_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription()
        mock_sub_repo = MagicMock()
        mock_sub_repo.list_by_subscriber = AsyncMock(return_value=([sub], 1))

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch("src.routers.subscriptions.SubscriptionResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_sub_response(sub)
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/subscriptions/my")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_my_empty(self, app_with_tenant_admin, mock_db_session):
        mock_sub_repo = MagicMock()
        mock_sub_repo.list_by_subscriber = AsyncMock(return_value=([], 0))

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/subscriptions/my")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_my_with_status_filter(self, app_with_tenant_admin, mock_db_session):
        mock_sub_repo = MagicMock()
        mock_sub_repo.list_by_subscriber = AsyncMock(return_value=([], 0))

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/subscriptions/my?status=active")

        assert resp.status_code == 200
        mock_sub_repo.list_by_subscriber.assert_called_once()


# ============== Get Subscription ==============


class TestGetSubscription:
    """GET /v1/subscriptions/{subscription_id}"""

    def test_get_success_as_subscriber(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(subscriber_id="tenant-admin-user-id")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch("src.routers.subscriptions.SubscriptionResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_sub_response(sub)
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get(f"/v1/subscriptions/{sub.id}")

        assert resp.status_code == 200

    def test_get_404(self, app_with_tenant_admin, mock_db_session):
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/subscriptions/{uuid4()}")

        assert resp.status_code == 404

    def test_get_403_wrong_user(self, app_with_other_tenant, mock_db_session):
        sub = _mock_subscription(subscriber_id="tenant-admin-user-id", tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_other_tenant) as client:
            resp = client.get(f"/v1/subscriptions/{sub.id}")

        assert resp.status_code == 403


# ============== Cancel Subscription ==============


class TestCancelSubscription:
    """DELETE /v1/subscriptions/{subscription_id}"""

    def test_cancel_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(subscriber_id="tenant-admin-user-id", status=SubscriptionStatus.ACTIVE)
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)
        mock_sub_repo.update_status = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/subscriptions/{sub.id}")

        assert resp.status_code == 204

    def test_cancel_400_wrong_status(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(subscriber_id="tenant-admin-user-id", status=SubscriptionStatus.REVOKED)
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/subscriptions/{sub.id}")

        assert resp.status_code == 400

    def test_cancel_403_not_owner(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(subscriber_id="someone-else-id", status=SubscriptionStatus.ACTIVE)
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"/v1/subscriptions/{sub.id}")

        assert resp.status_code == 403


# ============== Rotate API Key ==============


class TestRotateApiKey:
    """POST /v1/subscriptions/{subscription_id}/rotate-key"""

    def test_rotate_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(
            subscriber_id="tenant-admin-user-id",
            status=SubscriptionStatus.ACTIVE,
            previous_key_expires_at=None,
        )
        rotated = _mock_subscription(
            subscriber_id="tenant-admin-user-id",
            status=SubscriptionStatus.ACTIVE,
            rotation_count=1,
            previous_key_expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)
        mock_sub_repo.rotate_key = AsyncMock(return_value=rotated)

        mock_email = MagicMock()
        mock_email.send_key_rotation_notification = AsyncMock()

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
            patch(EMAIL_SVC_PATH, mock_email),
            patch(EMIT_ROTATED_PATH, new_callable=lambda: lambda: AsyncMock()),
        ):
            MockKey.generate_key.return_value = ("stoa_sk_newkey", "new-hash", "stoa_sk_")
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(
                    f"/v1/subscriptions/{sub.id}/rotate-key",
                    json={"grace_period_hours": 24},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "new_api_key" in data
        assert data["rotation_count"] == 1

    def test_rotate_400_wrong_status(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(subscriber_id="tenant-admin-user-id", status=SubscriptionStatus.SUSPENDED)
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
        ):
            MockKey.generate_key.return_value = ("stoa_sk_newkey", "new-hash", "stoa_sk_")
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/subscriptions/{sub.id}/rotate-key", json={"grace_period_hours": 24})

        assert resp.status_code == 400

    def test_rotate_400_grace_period_active(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(
            subscriber_id="tenant-admin-user-id",
            status=SubscriptionStatus.ACTIVE,
            previous_key_expires_at=datetime.utcnow() + timedelta(hours=12),
        )
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
        ):
            MockKey.generate_key.return_value = ("stoa_sk_newkey", "new-hash", "stoa_sk_")
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/subscriptions/{sub.id}/rotate-key", json={"grace_period_hours": 24})

        assert resp.status_code == 400

    def test_rotate_403_not_owner(self, app_with_other_tenant, mock_db_session):
        sub = _mock_subscription(subscriber_id="tenant-admin-user-id", status=SubscriptionStatus.ACTIVE)
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
        ):
            MockKey.generate_key.return_value = ("stoa_sk_newkey", "new-hash", "stoa_sk_")
            with TestClient(app_with_other_tenant) as client:
                resp = client.post(f"/v1/subscriptions/{sub.id}/rotate-key", json={"grace_period_hours": 24})

        assert resp.status_code == 403


# ============== Rotation Info ==============


class TestGetRotationInfo:
    """GET /v1/subscriptions/{subscription_id}/rotation-info"""

    def test_rotation_info_success(self, app_with_tenant_admin, mock_db_session):
        from src.schemas.subscription import SubscriptionStatusEnum, SubscriptionWithRotationInfo

        sub = _mock_subscription(
            subscriber_id="tenant-admin-user-id",
            rotation_count=2,
            previous_key_expires_at=None,
            last_rotated_at=datetime.utcnow(),
        )
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        # Build a real SubscriptionWithRotationInfo to avoid FastAPI serialization issues
        rotation_info = SubscriptionWithRotationInfo(
            id=sub.id,
            application_id=sub.application_id,
            application_name=sub.application_name,
            subscriber_id=sub.subscriber_id,
            subscriber_email=sub.subscriber_email,
            api_id=sub.api_id,
            api_name=sub.api_name,
            api_version=sub.api_version,
            tenant_id=sub.tenant_id,
            plan_id=sub.plan_id,
            plan_name=sub.plan_name,
            api_key_prefix=sub.api_key_prefix,
            status=SubscriptionStatusEnum.ACTIVE,
            status_reason=None,
            created_at=sub.created_at,
            updated_at=sub.updated_at,
            approved_at=None,
            expires_at=None,
            revoked_at=None,
            approved_by=None,
            revoked_by=None,
            rotation_count=2,
            has_active_grace_period=False,
        )

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch("src.routers.subscriptions.SubscriptionWithRotationInfo") as MockResp,
        ):
            MockResp.model_validate.return_value = rotation_info
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get(f"/v1/subscriptions/{sub.id}/rotation-info")

        assert resp.status_code == 200

    def test_rotation_info_404(self, app_with_tenant_admin, mock_db_session):
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get(f"/v1/subscriptions/{uuid4()}/rotation-info")

        assert resp.status_code == 404


# ============== TTL Extension ==============


class TestExtendTTL:
    """PATCH /v1/subscriptions/{subscription_id}/ttl"""

    def test_extend_ttl_success(self, app_with_tenant_admin, mock_db_session):
        future_expires = datetime.utcnow() + timedelta(days=30)
        sub = _mock_subscription(
            subscriber_id="tenant-admin-user-id",
            status=SubscriptionStatus.ACTIVE,
            expires_at=future_expires,
            ttl_extension_count=0,
            ttl_total_extended_days=0,
        )
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        mock_kafka = MagicMock()
        mock_kafka.publish = AsyncMock()

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(KAFKA_SVC_PATH, mock_kafka),
            TestClient(app_with_tenant_admin) as client,
        ):
            resp = client.patch(
                f"/v1/subscriptions/{sub.id}/ttl",
                json={"extend_days": 7, "reason": "More time needed"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ttl_extension_count"] == 1

    def test_extend_ttl_409_not_active(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(
            subscriber_id="tenant-admin-user-id",
            status=SubscriptionStatus.SUSPENDED,
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.patch(
                f"/v1/subscriptions/{sub.id}/ttl",
                json={"extend_days": 7, "reason": "reason"},
            )

        assert resp.status_code == 409

    def test_extend_ttl_409_max_extensions_reached(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(
            subscriber_id="tenant-admin-user-id",
            status=SubscriptionStatus.ACTIVE,
            expires_at=datetime.utcnow() + timedelta(days=30),
            ttl_extension_count=2,
            ttl_total_extended_days=14,
        )
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.patch(
                f"/v1/subscriptions/{sub.id}/ttl",
                json={"extend_days": 7, "reason": "reason"},
            )

        assert resp.status_code == 409

    def test_extend_ttl_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        sub = _mock_subscription(tenant_id="acme", status=SubscriptionStatus.ACTIVE)
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_other_tenant) as client:
            resp = client.patch(
                f"/v1/subscriptions/{sub.id}/ttl",
                json={"extend_days": 7, "reason": "reason"},
            )

        assert resp.status_code == 403


# ============== List Tenant Subscriptions ==============


class TestListTenantSubscriptions:
    """GET /v1/subscriptions/tenant/{tenant_id}"""

    def test_list_tenant_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription()
        mock_sub_repo = MagicMock()
        mock_sub_repo.list_by_tenant = AsyncMock(return_value=([sub], 1))

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch("src.routers.subscriptions.SubscriptionResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_sub_response(sub)
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/subscriptions/tenant/acme")

        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_list_tenant_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        with TestClient(app_with_other_tenant) as client:
            resp = client.get("/v1/subscriptions/tenant/acme")

        assert resp.status_code == 403


# ============== List Pending Subscriptions ==============


class TestListPendingSubscriptions:
    """GET /v1/subscriptions/tenant/{tenant_id}/pending"""

    def test_list_pending_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.PENDING)
        mock_sub_repo = MagicMock()
        mock_sub_repo.list_pending = AsyncMock(return_value=([sub], 1))

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch("src.routers.subscriptions.SubscriptionResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_sub_response(sub)
            with TestClient(app_with_tenant_admin) as client:
                resp = client.get("/v1/subscriptions/tenant/acme/pending")

        assert resp.status_code == 200

    def test_list_pending_empty(self, app_with_tenant_admin, mock_db_session):
        mock_sub_repo = MagicMock()
        mock_sub_repo.list_pending = AsyncMock(return_value=([], 0))

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.get("/v1/subscriptions/tenant/acme/pending")

        assert resp.status_code == 200
        assert resp.json()["total"] == 0


# ============== Approve Subscription ==============


class TestApproveSubscription:
    """POST /v1/subscriptions/{subscription_id}/approve"""

    def test_approve_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.PENDING, tenant_id="acme")
        approved = _mock_subscription(status=SubscriptionStatus.ACTIVE, tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)
        mock_sub_repo.update_status = AsyncMock(return_value=approved)
        mock_sub_repo.set_expiration = AsyncMock()

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch("src.routers.subscriptions.SubscriptionResponse") as MockResp,
            patch(EMIT_APPROVED_PATH, new=AsyncMock()),
            patch(PROVISION_PATH, new=AsyncMock()),
        ):
            MockResp.model_validate.return_value = _mock_sub_response(approved)
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

        assert resp.status_code == 200

    def test_approve_400_not_pending(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.ACTIVE, tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

        assert resp.status_code == 400

    def test_approve_404(self, app_with_tenant_admin, mock_db_session):
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=None)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/subscriptions/{uuid4()}/approve", json={})

        assert resp.status_code == 404

    def test_approve_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.PENDING, tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_other_tenant) as client:
            resp = client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

        assert resp.status_code == 403


# ============== Revoke Subscription ==============


class TestRevokeSubscription:
    """POST /v1/subscriptions/{subscription_id}/revoke"""

    def test_revoke_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.ACTIVE, tenant_id="acme")
        revoked = _mock_subscription(status=SubscriptionStatus.REVOKED, tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)
        mock_sub_repo.update_status = AsyncMock(return_value=revoked)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch("src.routers.subscriptions.SubscriptionResponse") as MockResp,
            patch(EMIT_REVOKED_PATH, new=AsyncMock()),
            patch(DEPROVISION_PATH, new=AsyncMock()),
        ):
            MockResp.model_validate.return_value = _mock_sub_response(revoked)
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(
                    f"/v1/subscriptions/{sub.id}/revoke",
                    json={"reason": "Policy violation"},
                )

        assert resp.status_code == 200

    def test_revoke_400_already_revoked(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.REVOKED, tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/revoke",
                json={"reason": "already revoked"},
            )

        assert resp.status_code == 400


# ============== Suspend Subscription ==============


class TestSuspendSubscription:
    """POST /v1/subscriptions/{subscription_id}/suspend"""

    def test_suspend_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.ACTIVE, tenant_id="acme")
        suspended = _mock_subscription(status=SubscriptionStatus.SUSPENDED, tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)
        mock_sub_repo.update_status = AsyncMock(return_value=suspended)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch("src.routers.subscriptions.SubscriptionResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_sub_response(suspended)
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/subscriptions/{sub.id}/suspend")

        assert resp.status_code == 200

    def test_suspend_400_not_active(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.SUSPENDED, tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/subscriptions/{sub.id}/suspend")

        assert resp.status_code == 400


# ============== Reactivate Subscription ==============


class TestReactivateSubscription:
    """POST /v1/subscriptions/{subscription_id}/reactivate"""

    def test_reactivate_success(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.SUSPENDED, tenant_id="acme")
        reactivated = _mock_subscription(status=SubscriptionStatus.ACTIVE, tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)
        mock_sub_repo.update_status = AsyncMock(return_value=reactivated)

        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch("src.routers.subscriptions.SubscriptionResponse") as MockResp,
        ):
            MockResp.model_validate.return_value = _mock_sub_response(reactivated)
            with TestClient(app_with_tenant_admin) as client:
                resp = client.post(f"/v1/subscriptions/{sub.id}/reactivate")

        assert resp.status_code == 200

    def test_reactivate_400_not_suspended(self, app_with_tenant_admin, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.ACTIVE, tenant_id="acme")
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_id = AsyncMock(return_value=sub)

        with patch(SUB_REPO_PATH, return_value=mock_sub_repo), TestClient(app_with_tenant_admin) as client:
            resp = client.post(f"/v1/subscriptions/{sub.id}/reactivate")

        assert resp.status_code == 400


# ============== Validate API Key ==============


class TestValidateApiKey:
    """POST /v1/subscriptions/validate-key (no auth required)"""

    def _get_no_auth_client(self, app, mock_db_session):
        """Create a client with only db override (no auth override)."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db
        return app

    def test_validate_key_success(self, app, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.ACTIVE, expires_at=None)

        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_api_key_hash = AsyncMock(return_value=sub)
        mock_sub_repo.get_by_previous_key_hash = AsyncMock(return_value=None)

        self._get_no_auth_client(app, mock_db_session)
        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
        ):
            MockKey.validate_format.return_value = True
            MockKey.hash_key.return_value = "hash123"
            with TestClient(app) as client:
                resp = client.post("/v1/subscriptions/validate-key?api_key=stoa_sk_validkey123")

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True

    def test_validate_key_401_invalid_format(self, app, mock_db_session):
        self._get_no_auth_client(app, mock_db_session)
        with patch(API_KEY_SVC_PATH) as MockKey:
            MockKey.validate_format.return_value = False
            with TestClient(app) as client:
                resp = client.post("/v1/subscriptions/validate-key?api_key=badformat")

        assert resp.status_code == 401
        assert "Invalid API key format" in resp.json()["detail"]

    def test_validate_key_401_not_found(self, app, mock_db_session):
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_api_key_hash = AsyncMock(return_value=None)
        mock_sub_repo.get_by_previous_key_hash = AsyncMock(return_value=None)

        self._get_no_auth_client(app, mock_db_session)
        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
        ):
            MockKey.validate_format.return_value = True
            MockKey.hash_key.return_value = "hash-not-found"
            with TestClient(app) as client:
                resp = client.post("/v1/subscriptions/validate-key?api_key=stoa_sk_validkey123")

        assert resp.status_code == 401

    def test_validate_key_403_not_active(self, app, mock_db_session):
        sub = _mock_subscription(status=SubscriptionStatus.REVOKED)
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_api_key_hash = AsyncMock(return_value=sub)
        mock_sub_repo.get_by_previous_key_hash = AsyncMock(return_value=None)

        self._get_no_auth_client(app, mock_db_session)
        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
        ):
            MockKey.validate_format.return_value = True
            MockKey.hash_key.return_value = "hash123"
            with TestClient(app) as client:
                resp = client.post("/v1/subscriptions/validate-key?api_key=stoa_sk_validkey123")

        assert resp.status_code == 403

    def test_validate_key_success_previous_key_grace_period(self, app, mock_db_session):
        sub = _mock_subscription(
            status=SubscriptionStatus.ACTIVE,
            previous_key_expires_at=datetime.utcnow() + timedelta(hours=12),
        )
        mock_sub_repo = MagicMock()
        mock_sub_repo.get_by_api_key_hash = AsyncMock(return_value=None)
        mock_sub_repo.get_by_previous_key_hash = AsyncMock(return_value=sub)

        self._get_no_auth_client(app, mock_db_session)
        with (
            patch(SUB_REPO_PATH, return_value=mock_sub_repo),
            patch(API_KEY_SVC_PATH) as MockKey,
        ):
            MockKey.validate_format.return_value = True
            MockKey.hash_key.return_value = "old-hash"
            with TestClient(app) as client:
                resp = client.post("/v1/subscriptions/validate-key?api_key=stoa_sk_oldkey123")

        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data.get("using_previous_key") is True
