"""Subscription Workflow Audit Tests

Comprehensive verification of the subscription lifecycle covering:
- Phase 1: State machine transitions (valid + invalid)
- Phase 2: RBAC multi-tenant isolation (4 roles × 17 endpoints)
- Phase 3: Audit trail (Kafka events + webhook emissions)
- Phase 4: Gateway provisioning (approve→READY, revoke→DEPROVISIONED)

Each test documents which audit finding (L1-L10) it addresses.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.models.subscription import ProvisioningStatus, SubscriptionStatus

# ---------------------------------------------------------------------------
# Patch paths (same as test_subscriptions_router.py)
# ---------------------------------------------------------------------------
SUB_REPO = "src.routers.subscriptions.SubscriptionRepository"
PLAN_REPO = "src.routers.subscriptions.PlanRepository"
API_KEY_SVC = "src.routers.subscriptions.APIKeyService"
PORTAL_APP_REPO = "src.routers.subscriptions.PortalApplicationRepository"
EMAIL_SVC = "src.routers.subscriptions.email_service"
KAFKA_SVC = "src.routers.subscriptions.kafka_service"
PROVISION = "src.routers.subscriptions.provision_on_approval"
DEPROVISION = "src.routers.subscriptions.deprovision_on_revocation"
EMIT_CREATED = "src.routers.subscriptions.emit_subscription_created"
EMIT_APPROVED = "src.routers.subscriptions.emit_subscription_approved"
EMIT_REVOKED = "src.routers.subscriptions.emit_subscription_revoked"
EMIT_REJECTED = "src.routers.subscriptions.emit_subscription_rejected"
EMIT_ROTATED = "src.routers.subscriptions.emit_subscription_key_rotated"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_sub(**overrides) -> MagicMock:
    """Build a MagicMock mimicking a Subscription ORM row."""
    m = MagicMock()
    sid = overrides.pop("id", uuid4())
    defaults = {
        "id": sid,
        "application_id": "00000000-0000-4000-8000-000000000001",
        "application_name": "Audit App",
        "subscriber_id": "tenant-admin-user-id",
        "subscriber_email": "admin@acme.com",
        "api_id": "api-audit-1",
        "api_name": "Audit API",
        "api_version": "1.0",
        "tenant_id": "acme",
        "consumer_id": None,
        "plan_id": str(uuid4()),
        "plan_name": "Basic",
        "oauth_client_id": "kc-client-audit",
        "api_key_hash": "hash_audit",
        "api_key_prefix": "stoa_sk_",
        "status": SubscriptionStatus.PENDING,
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
        "rejected_by": None,
        "rejected_at": None,
        "provisioning_status": ProvisioningStatus.NONE,
        "gateway_app_id": None,
        "provisioning_error": None,
        "provisioned_at": None,
        "environment": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _patch_all():
    """Return a dict of common patches for subscription router tests."""
    return {
        "sub_repo": patch(SUB_REPO),
        "plan_repo": patch(PLAN_REPO),
        "portal_app_repo": patch(PORTAL_APP_REPO),
        "api_key_svc": patch(API_KEY_SVC),
        "email_svc": patch(EMAIL_SVC),
        "kafka_svc": patch(KAFKA_SVC),
        "provision": patch(PROVISION, new_callable=AsyncMock),
        "deprovision": patch(DEPROVISION, new_callable=AsyncMock),
        "emit_created": patch(EMIT_CREATED, new_callable=AsyncMock),
        "emit_approved": patch(EMIT_APPROVED, new_callable=AsyncMock),
        "emit_revoked": patch(EMIT_REVOKED, new_callable=AsyncMock),
        "emit_rejected": patch(EMIT_REJECTED, new_callable=AsyncMock),
        "emit_rotated": patch(EMIT_ROTATED, new_callable=AsyncMock),
    }


# ============================================================================
# PHASE 1 — STATE MACHINE TRANSITIONS
# ============================================================================


class TestPhase1StateMachine:
    """Verify every valid and invalid subscription status transition.

    Addresses audit finding: complete state machine coverage.
    """

    # --- Valid transitions ---

    def test_pending_to_active_via_approve(self, app_with_tenant_admin):
        """PENDING → ACTIVE (approve endpoint)."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_approved"],
            patches["provision"],
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            repo_inst.set_expiration = AsyncMock(return_value=sub)

            approved_sub = _make_sub(
                id=sub.id,
                status=SubscriptionStatus.ACTIVE,
                approved_at=datetime.utcnow(),
                approved_by="tenant-admin-user-id",
            )
            repo_inst.update_status = AsyncMock(return_value=approved_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "active"

            # Verify update_status called with correct transition
            repo_inst.update_status.assert_called_once()
            call_args = repo_inst.update_status.call_args
            assert call_args[1].get("new_status", call_args[0][1]) == SubscriptionStatus.ACTIVE

    def test_pending_to_rejected(self, app_with_tenant_admin):
        """PENDING → REJECTED (reject endpoint)."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_rejected"],
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)

            rejected_sub = _make_sub(
                id=sub.id,
                status=SubscriptionStatus.REJECTED,
                rejected_at=datetime.utcnow(),
                rejected_by="tenant-admin-user-id",
                status_reason="Policy violation",
            )
            repo_inst.update_status = AsyncMock(return_value=rejected_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/reject",
                json={"reason": "Policy violation"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "rejected"

    def test_active_to_suspended(self, app_with_tenant_admin):
        """ACTIVE → SUSPENDED (suspend endpoint)."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE)
        patches = _patch_all()
        with patches["sub_repo"] as mock_repo_cls:
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)

            suspended_sub = _make_sub(id=sub.id, status=SubscriptionStatus.SUSPENDED)
            repo_inst.update_status = AsyncMock(return_value=suspended_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(f"/v1/subscriptions/{sub.id}/suspend")

            assert resp.status_code == 200
            assert resp.json()["status"] == "suspended"

    def test_suspended_to_active_via_reactivate(self, app_with_tenant_admin):
        """SUSPENDED → ACTIVE (reactivate endpoint)."""
        sub = _make_sub(status=SubscriptionStatus.SUSPENDED)
        patches = _patch_all()
        with patches["sub_repo"] as mock_repo_cls:
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)

            reactivated_sub = _make_sub(id=sub.id, status=SubscriptionStatus.ACTIVE)
            repo_inst.update_status = AsyncMock(return_value=reactivated_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(f"/v1/subscriptions/{sub.id}/reactivate")

            assert resp.status_code == 200
            assert resp.json()["status"] == "active"

    def test_active_to_revoked(self, app_with_tenant_admin):
        """ACTIVE → REVOKED (revoke endpoint)."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_revoked"],
            patches["deprovision"],
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)

            revoked_sub = _make_sub(
                id=sub.id,
                status=SubscriptionStatus.REVOKED,
                revoked_at=datetime.utcnow(),
                revoked_by="tenant-admin-user-id",
                status_reason="TOS violation",
            )
            repo_inst.update_status = AsyncMock(return_value=revoked_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/revoke",
                json={"reason": "TOS violation"},
            )

            assert resp.status_code == 200
            assert resp.json()["status"] == "revoked"

    def test_pending_to_revoked_via_cancel(self, app_with_tenant_admin):
        """PENDING → REVOKED (cancel by subscriber)."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with patches["sub_repo"] as mock_repo_cls:
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            repo_inst.update_status = AsyncMock(return_value=sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.delete(f"/v1/subscriptions/{sub.id}")

            assert resp.status_code == 204

    # --- Invalid transitions (must return 400) ---

    @pytest.mark.parametrize(
        "initial_status,endpoint,method,payload",
        [
            (SubscriptionStatus.ACTIVE, "approve", "post", {}),
            (SubscriptionStatus.SUSPENDED, "approve", "post", {}),
            (SubscriptionStatus.REVOKED, "approve", "post", {}),
            (SubscriptionStatus.REJECTED, "approve", "post", {}),
            (SubscriptionStatus.EXPIRED, "approve", "post", {}),
            (SubscriptionStatus.ACTIVE, "reject", "post", {"reason": "test"}),
            (SubscriptionStatus.SUSPENDED, "reject", "post", {"reason": "test"}),
            (SubscriptionStatus.REVOKED, "reject", "post", {"reason": "test"}),
            (SubscriptionStatus.PENDING, "suspend", "post", None),
            (SubscriptionStatus.REVOKED, "suspend", "post", None),
            (SubscriptionStatus.EXPIRED, "suspend", "post", None),
            (SubscriptionStatus.PENDING, "reactivate", "post", None),
            (SubscriptionStatus.ACTIVE, "reactivate", "post", None),
            (SubscriptionStatus.REVOKED, "reactivate", "post", None),
            (SubscriptionStatus.REVOKED, "revoke", "post", {"reason": "double revoke"}),
            (SubscriptionStatus.REVOKED, "cancel", "delete", None),
            (SubscriptionStatus.EXPIRED, "cancel", "delete", None),
            (SubscriptionStatus.SUSPENDED, "cancel", "delete", None),
        ],
        ids=lambda x: str(x) if not isinstance(x, dict) else "payload",
    )
    def test_invalid_transitions_return_400(
        self, app_with_tenant_admin, initial_status, endpoint, method, payload
    ):
        """Invalid state transitions must be blocked with HTTP 400."""
        sub = _make_sub(status=initial_status)
        patches = _patch_all()
        with patches["sub_repo"] as mock_repo_cls:
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_tenant_admin)

            if endpoint == "cancel":
                url = f"/v1/subscriptions/{sub.id}"
            else:
                url = f"/v1/subscriptions/{sub.id}/{endpoint}"

            if method == "post":
                resp = client.post(url, json=payload or {})
            else:
                resp = client.delete(url)

            assert resp.status_code == 400, (
                f"Expected 400 for {initial_status.value}→{endpoint}, "
                f"got {resp.status_code}: {resp.json()}"
            )

    # --- Audit fields verification ---

    def test_approve_sets_audit_fields(self, app_with_tenant_admin):
        """Approval must set approved_at, approved_by with actor identity."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_approved"],
            patches["provision"],
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            repo_inst.set_expiration = AsyncMock(return_value=sub)

            approved_sub = _make_sub(id=sub.id, status=SubscriptionStatus.ACTIVE)
            repo_inst.update_status = AsyncMock(return_value=approved_sub)

            client = TestClient(app_with_tenant_admin)
            client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

            call_args = repo_inst.update_status.call_args
            assert call_args[1].get("actor_id") == "tenant-admin-user-id"

    def test_reject_sets_audit_fields(self, app_with_tenant_admin):
        """Rejection must pass actor_id and reason to update_status."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_rejected"],
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            rejected_sub = _make_sub(id=sub.id, status=SubscriptionStatus.REJECTED)
            repo_inst.update_status = AsyncMock(return_value=rejected_sub)

            client = TestClient(app_with_tenant_admin)
            client.post(
                f"/v1/subscriptions/{sub.id}/reject",
                json={"reason": "Audit test"},
            )

            call_args = repo_inst.update_status.call_args
            assert call_args[1].get("actor_id") == "tenant-admin-user-id"
            assert call_args[1].get("reason") == "Audit test"

    def test_revoke_sets_audit_fields(self, app_with_tenant_admin):
        """Revocation must pass actor_id and reason to update_status."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_revoked"],
            patches["deprovision"],
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            revoked_sub = _make_sub(id=sub.id, status=SubscriptionStatus.REVOKED)
            repo_inst.update_status = AsyncMock(return_value=revoked_sub)

            client = TestClient(app_with_tenant_admin)
            client.post(
                f"/v1/subscriptions/{sub.id}/revoke",
                json={"reason": "Security breach"},
            )

            call_args = repo_inst.update_status.call_args
            assert call_args[1].get("actor_id") == "tenant-admin-user-id"
            assert call_args[1].get("reason") == "Security breach"


# ============================================================================
# PHASE 2 — RBAC MULTI-TENANT ISOLATION
# ============================================================================


class TestPhase2RBAC:
    """Verify RBAC enforcement for all roles across subscription endpoints.

    Addresses audit findings L3 (viewer role not tested).
    """

    # --- Viewer role: read-only, cannot perform admin actions ---

    def test_viewer_cannot_approve(self, app_with_viewer):
        """Viewer must be blocked from approving (FIXED — _has_tenant_admin_access)."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        with patch(SUB_REPO) as mock_repo_cls:
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_viewer)
            resp = client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

            assert resp.status_code == 403

    def test_viewer_cannot_reject(self, app_with_viewer):
        """Viewer must be blocked from rejecting (FIXED)."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_viewer)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/reject",
                json={"reason": "viewer test"},
            )

            assert resp.status_code == 403

    def test_viewer_cannot_revoke(self, app_with_viewer):
        """Viewer must be blocked from revoking (FIXED)."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE)
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_viewer)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/revoke",
                json={"reason": "viewer test"},
            )

            assert resp.status_code == 403

    def test_viewer_cannot_suspend(self, app_with_viewer):
        """Viewer must be blocked from suspending (FIXED)."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE)
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_viewer)
            resp = client.post(f"/v1/subscriptions/{sub.id}/suspend")

            assert resp.status_code == 403

    def test_viewer_can_read_own_subscriptions(self, app_with_viewer):
        """Viewer must be able to list own subscriptions."""
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.list_by_subscriber = AsyncMock(return_value=([], 0))

            client = TestClient(app_with_viewer)
            resp = client.get("/v1/subscriptions/my")

            assert resp.status_code == 200

    # --- Cross-tenant isolation ---

    def test_other_tenant_cannot_approve(self, app_with_other_tenant):
        """Tenant admin from tenant B cannot approve tenant A subscriptions."""
        sub = _make_sub(status=SubscriptionStatus.PENDING, tenant_id="acme")
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_other_tenant)
            resp = client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

            assert resp.status_code == 403

    def test_other_tenant_cannot_revoke(self, app_with_other_tenant):
        """Tenant admin from tenant B cannot revoke tenant A subscriptions."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE, tenant_id="acme")
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_other_tenant)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/revoke",
                json={"reason": "cross-tenant test"},
            )

            assert resp.status_code == 403

    def test_other_tenant_cannot_reject(self, app_with_other_tenant):
        """Tenant admin from tenant B cannot reject tenant A subscriptions."""
        sub = _make_sub(status=SubscriptionStatus.PENDING, tenant_id="acme")
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_other_tenant)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/reject",
                json={"reason": "cross-tenant test"},
            )

            assert resp.status_code == 403

    def test_other_tenant_cannot_suspend(self, app_with_other_tenant):
        """Tenant admin from tenant B cannot suspend tenant A subscriptions."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE, tenant_id="acme")
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_other_tenant)
            resp = client.post(f"/v1/subscriptions/{sub.id}/suspend")

            assert resp.status_code == 403

    def test_other_tenant_cannot_list_tenant_subs(self, app_with_other_tenant):
        """Tenant admin from tenant B cannot list tenant A subscriptions."""
        client = TestClient(app_with_other_tenant)
        resp = client.get("/v1/subscriptions/tenant/acme")

        assert resp.status_code == 403

    def test_other_tenant_cannot_list_pending(self, app_with_other_tenant):
        """Tenant admin from tenant B cannot list tenant A pending subscriptions."""
        client = TestClient(app_with_other_tenant)
        resp = client.get("/v1/subscriptions/tenant/acme/pending")

        assert resp.status_code == 403

    def test_other_tenant_cannot_get_stats(self, app_with_other_tenant):
        """Tenant admin from tenant B cannot get tenant A stats."""
        client = TestClient(app_with_other_tenant)
        resp = client.get("/v1/subscriptions/tenant/acme/stats")

        assert resp.status_code == 403

    def test_other_tenant_cannot_get_subscription(self, app_with_other_tenant):
        """Tenant admin from tenant B cannot read tenant A subscription details."""
        sub = _make_sub(tenant_id="acme", subscriber_id="someone-else")
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_other_tenant)
            resp = client.get(f"/v1/subscriptions/{sub.id}")

            assert resp.status_code == 403

    # --- CPI-admin cross-tenant access ---

    def test_cpi_admin_can_approve_any_tenant(self, app_with_cpi_admin):
        """CPI-admin can approve subscriptions in any tenant."""
        sub = _make_sub(status=SubscriptionStatus.PENDING, tenant_id="other-tenant")
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_approved"],
            patches["provision"],
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            repo_inst.set_expiration = AsyncMock(return_value=sub)

            approved_sub = _make_sub(id=sub.id, status=SubscriptionStatus.ACTIVE, tenant_id="other-tenant")
            repo_inst.update_status = AsyncMock(return_value=approved_sub)

            client = TestClient(app_with_cpi_admin)
            resp = client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

            assert resp.status_code == 200

    def test_cpi_admin_can_list_any_tenant(self, app_with_cpi_admin):
        """CPI-admin can list subscriptions for any tenant."""
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.list_by_tenant = AsyncMock(return_value=([], 0))

            client = TestClient(app_with_cpi_admin)
            resp = client.get("/v1/subscriptions/tenant/any-tenant-id")

            assert resp.status_code == 200

    # --- Non-owner subscriber cannot cancel another's subscription ---

    def test_non_owner_cannot_cancel(self, app_with_other_tenant):
        """Subscriber from other tenant cannot cancel someone else's subscription."""
        sub = _make_sub(
            status=SubscriptionStatus.ACTIVE,
            subscriber_id="original-subscriber",
            tenant_id="acme",
        )
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_other_tenant)
            resp = client.delete(f"/v1/subscriptions/{sub.id}")

            assert resp.status_code == 403

    # --- Bulk action cross-tenant ---

    def test_bulk_action_rejects_cross_tenant(self, app_with_other_tenant):
        """Bulk approve fails for subscriptions in a different tenant."""
        sub = _make_sub(status=SubscriptionStatus.PENDING, tenant_id="acme")
        with patch(SUB_REPO) as mock_repo_cls:
            mock_inst = mock_repo_cls.return_value
            mock_inst.get_by_id = AsyncMock(return_value=sub)

            client = TestClient(app_with_other_tenant)
            resp = client.post(
                "/v1/subscriptions/bulk",
                json={"ids": [str(sub.id)], "action": "approve"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["succeeded"] == 0
            assert len(data["failed"]) == 1
            assert "Access denied" in data["failed"][0]["error"]


# ============================================================================
# PHASE 3 — AUDIT TRAIL VERIFICATION (KAFKA + WEBHOOKS)
# ============================================================================


class TestPhase3AuditTrail:
    """Verify that every subscription action emits the correct audit events.

    Addresses audit findings L1 (Kafka events not verified) and L8 (missing events).
    """

    def test_approve_emits_webhook_L1(self, app_with_tenant_admin):
        """Approval MUST call emit_subscription_approved (L1)."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_approved"] as mock_emit,
            patches["provision"],
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            repo_inst.set_expiration = AsyncMock(return_value=sub)
            approved_sub = _make_sub(id=sub.id, status=SubscriptionStatus.ACTIVE)
            repo_inst.update_status = AsyncMock(return_value=approved_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

            assert resp.status_code == 200
            mock_emit.assert_called_once()

    def test_reject_emits_webhook_L1(self, app_with_tenant_admin):
        """Rejection MUST call emit_subscription_rejected (L1)."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_rejected"] as mock_emit,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            rejected_sub = _make_sub(id=sub.id, status=SubscriptionStatus.REJECTED)
            repo_inst.update_status = AsyncMock(return_value=rejected_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/reject",
                json={"reason": "Audit L1"},
            )

            assert resp.status_code == 200
            mock_emit.assert_called_once()

    def test_revoke_emits_webhook_L1(self, app_with_tenant_admin):
        """Revocation MUST call emit_subscription_revoked (L1)."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_revoked"] as mock_emit,
            patches["deprovision"],
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            revoked_sub = _make_sub(id=sub.id, status=SubscriptionStatus.REVOKED)
            repo_inst.update_status = AsyncMock(return_value=revoked_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/revoke",
                json={"reason": "Audit L1"},
            )

            assert resp.status_code == 200
            mock_emit.assert_called_once()

    def test_create_emits_webhook_L1(self, app_with_tenant_admin):
        """Creation MUST call emit_subscription_created (L1)."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["portal_app_repo"] as mock_app_repo_cls,
            patches["plan_repo"] as mock_plan_cls,
            patches["emit_created"] as mock_emit_created,
            patches["emit_approved"],
            patches["provision"],
        ):
            # Portal app returns valid app with keycloak_client_id
            mock_app = MagicMock()
            mock_app.keycloak_client_id = "kc-client-test"
            mock_app_repo_cls.return_value.get_by_id = AsyncMock(return_value=mock_app)

            # Plan lookup → no plan = auto-approve
            mock_plan_cls.return_value.get_by_id = AsyncMock(return_value=None)

            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_application_and_api = AsyncMock(return_value=None)
            repo_inst.create = AsyncMock(return_value=sub)

            auto_approved = _make_sub(id=sub.id, status=SubscriptionStatus.ACTIVE)
            repo_inst.update_status = AsyncMock(return_value=auto_approved)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions",
                json={
                    "application_id": sub.application_id,
                    "application_name": sub.application_name,
                    "api_id": sub.api_id,
                    "api_name": sub.api_name,
                    "api_version": sub.api_version,
                    "tenant_id": sub.tenant_id,
                },
            )

            assert resp.status_code == 201
            mock_emit_created.assert_called_once()

    def test_bulk_approve_emits_per_subscription_L1(self, app_with_tenant_admin):
        """Bulk approve must emit webhook for EACH approved subscription (L1)."""
        subs = [_make_sub(status=SubscriptionStatus.PENDING) for _ in range(3)]
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_approved"] as mock_emit,
            patches["provision"],
        ):
            repo_inst = mock_repo_cls.return_value

            async def get_by_id_side_effect(sid):
                for s in subs:
                    if s.id == sid:
                        return s
                return None

            repo_inst.get_by_id = AsyncMock(side_effect=get_by_id_side_effect)
            repo_inst.update_status = AsyncMock(
                side_effect=[
                    _make_sub(id=s.id, status=SubscriptionStatus.ACTIVE) for s in subs
                ]
            )

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions/bulk",
                json={
                    "ids": [str(s.id) for s in subs],
                    "action": "approve",
                },
            )

            assert resp.status_code == 200
            assert resp.json()["succeeded"] == 3
            assert mock_emit.call_count == 3

    def test_suspend_does_not_emit_webhook_L8(self, app_with_tenant_admin):
        """Suspend currently does NOT emit a webhook — documenting gap L8."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_approved"] as mock_approved,
            patches["emit_revoked"] as mock_revoked,
            patches["emit_rejected"] as mock_rejected,
            patches["emit_created"] as mock_created,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            suspended = _make_sub(id=sub.id, status=SubscriptionStatus.SUSPENDED)
            repo_inst.update_status = AsyncMock(return_value=suspended)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(f"/v1/subscriptions/{sub.id}/suspend")

            assert resp.status_code == 200
            # Document L8: no webhook emitted for suspend
            mock_approved.assert_not_called()
            mock_revoked.assert_not_called()
            mock_rejected.assert_not_called()
            mock_created.assert_not_called()

    def test_reactivate_does_not_emit_webhook_L8(self, app_with_tenant_admin):
        """Reactivate currently does NOT emit a webhook — documenting gap L8."""
        sub = _make_sub(status=SubscriptionStatus.SUSPENDED)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_approved"] as mock_approved,
            patches["emit_revoked"] as mock_revoked,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            reactivated = _make_sub(id=sub.id, status=SubscriptionStatus.ACTIVE)
            repo_inst.update_status = AsyncMock(return_value=reactivated)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(f"/v1/subscriptions/{sub.id}/reactivate")

            assert resp.status_code == 200
            # Document L8: no webhook for reactivation
            mock_approved.assert_not_called()
            mock_revoked.assert_not_called()

    def test_ttl_extend_emits_kafka_event(self, app_with_tenant_admin):
        """TTL extension must publish to RESOURCE_LIFECYCLE topic."""
        expires = datetime.utcnow() + timedelta(days=30)
        sub = _make_sub(status=SubscriptionStatus.ACTIVE, expires_at=expires)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["kafka_svc"] as mock_kafka_cls,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)

            mock_kafka = mock_kafka_cls
            mock_kafka.publish = AsyncMock()

            client = TestClient(app_with_tenant_admin)
            resp = client.patch(
                f"/v1/subscriptions/{sub.id}/ttl",
                json={"extend_days": 7, "reason": "Audit test"},
            )

            assert resp.status_code == 200
            mock_kafka.publish.assert_called_once()
            call_kwargs = mock_kafka.publish.call_args[1]
            assert call_kwargs["event_type"] == "resource-ttl-extended"
            assert call_kwargs["payload"]["extend_days"] == 7


# ============================================================================
# PHASE 4 — GATEWAY PROVISIONING VERIFICATION
# ============================================================================


class TestPhase4GatewayProvisioning:
    """Verify gateway provisioning is triggered on approve and deprovision on revoke.

    Addresses audit findings L2 (deprovision never tested) and L5 (provisioning not verified).
    """

    def test_approve_triggers_provisioning_L5(self, app_with_tenant_admin):
        """Approval MUST spawn provision_on_approval async task (L5)."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_approved"],
            patches["provision"] as mock_provision,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            repo_inst.set_expiration = AsyncMock(return_value=sub)
            approved_sub = _make_sub(id=sub.id, status=SubscriptionStatus.ACTIVE)
            repo_inst.update_status = AsyncMock(return_value=approved_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(f"/v1/subscriptions/{sub.id}/approve", json={})

            assert resp.status_code == 200
            mock_provision.assert_called_once()
            # Verify correct subscription passed
            call_args = mock_provision.call_args[0]
            assert call_args[1].id == approved_sub.id

    def test_revoke_triggers_deprovisioning_L2(self, app_with_tenant_admin):
        """Revocation MUST spawn deprovision_on_revocation async task (L2)."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_revoked"],
            patches["deprovision"] as mock_deprovision,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            revoked_sub = _make_sub(id=sub.id, status=SubscriptionStatus.REVOKED)
            repo_inst.update_status = AsyncMock(return_value=revoked_sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/revoke",
                json={"reason": "Audit L2"},
            )

            assert resp.status_code == 200
            mock_deprovision.assert_called_once()

    def test_bulk_approve_triggers_provisioning_per_sub(self, app_with_tenant_admin):
        """Bulk approve must trigger provisioning for EACH subscription."""
        subs = [_make_sub(status=SubscriptionStatus.PENDING) for _ in range(2)]
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_approved"],
            patches["provision"] as mock_provision,
        ):
            repo_inst = mock_repo_cls.return_value

            async def get_by_id_side_effect(sid):
                for s in subs:
                    if s.id == sid:
                        return s
                return None

            repo_inst.get_by_id = AsyncMock(side_effect=get_by_id_side_effect)
            repo_inst.update_status = AsyncMock(
                side_effect=[
                    _make_sub(id=s.id, status=SubscriptionStatus.ACTIVE) for s in subs
                ]
            )

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions/bulk",
                json={
                    "ids": [str(s.id) for s in subs],
                    "action": "approve",
                },
            )

            assert resp.status_code == 200
            assert mock_provision.call_count == 2

    def test_suspend_does_not_deprovision(self, app_with_tenant_admin):
        """Suspend must NOT trigger deprovisioning (gateway route stays)."""
        sub = _make_sub(status=SubscriptionStatus.ACTIVE)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["deprovision"] as mock_deprovision,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            suspended = _make_sub(id=sub.id, status=SubscriptionStatus.SUSPENDED)
            repo_inst.update_status = AsyncMock(return_value=suspended)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(f"/v1/subscriptions/{sub.id}/suspend")

            assert resp.status_code == 200
            mock_deprovision.assert_not_called()

    def test_auto_approve_triggers_provisioning(self, app_with_tenant_admin):
        """Auto-approved subscriptions (no plan) must also trigger provisioning."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["portal_app_repo"] as mock_app_repo_cls,
            patches["plan_repo"] as mock_plan_cls,
            patches["emit_created"],
            patches["emit_approved"],
            patches["provision"] as mock_provision,
        ):
            mock_app = MagicMock()
            mock_app.keycloak_client_id = "kc-client-auto"
            mock_app_repo_cls.return_value.get_by_id = AsyncMock(return_value=mock_app)

            mock_plan_cls.return_value.get_by_id = AsyncMock(return_value=None)

            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_application_and_api = AsyncMock(return_value=None)
            repo_inst.create = AsyncMock(return_value=sub)

            auto_approved = _make_sub(id=sub.id, status=SubscriptionStatus.ACTIVE)
            repo_inst.update_status = AsyncMock(return_value=auto_approved)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions",
                json={
                    "application_id": sub.application_id,
                    "application_name": sub.application_name,
                    "api_id": sub.api_id,
                    "api_name": sub.api_name,
                    "api_version": sub.api_version,
                    "tenant_id": sub.tenant_id,
                },
            )

            assert resp.status_code == 201
            mock_provision.assert_called_once()

    def test_reject_does_not_provision_or_deprovision(self, app_with_tenant_admin):
        """Rejection must NOT trigger any gateway provisioning."""
        sub = _make_sub(status=SubscriptionStatus.PENDING)
        patches = _patch_all()
        with (
            patches["sub_repo"] as mock_repo_cls,
            patches["emit_rejected"],
            patches["provision"] as mock_provision,
            patches["deprovision"] as mock_deprovision,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_id = AsyncMock(return_value=sub)
            rejected = _make_sub(id=sub.id, status=SubscriptionStatus.REJECTED)
            repo_inst.update_status = AsyncMock(return_value=rejected)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                f"/v1/subscriptions/{sub.id}/reject",
                json={"reason": "No provision"},
            )

            assert resp.status_code == 200
            mock_provision.assert_not_called()
            mock_deprovision.assert_not_called()


# ============================================================================
# PHASE 1 SUPPLEMENT — VALIDATE ENDPOINTS (Gateway internal)
# ============================================================================


class TestPhase1ValidateEndpoints:
    """Verify validation endpoints respect subscription status and expiration."""

    def test_validate_key_active_subscription(self, app_with_tenant_admin):
        """Active subscription with valid key returns valid=true."""
        sub = _make_sub(
            status=SubscriptionStatus.ACTIVE,
            api_key_hash="valid_hash",
        )
        with (
            patch(SUB_REPO) as mock_repo_cls,
            patch(API_KEY_SVC) as mock_key_svc,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_api_key_hash = AsyncMock(return_value=sub)
            repo_inst.get_by_previous_key_hash = AsyncMock(return_value=None)

            mock_key_svc.validate_format.return_value = True
            mock_key_svc.hash_key.return_value = "valid_hash"

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions/validate-key",
                json={"api_key": "stoa_sk_test1234567890123456"},
            )

            assert resp.status_code == 200
            assert resp.json()["valid"] is True

    def test_validate_key_suspended_returns_403(self, app_with_tenant_admin):
        """Suspended subscription must return 403 on key validation."""
        sub = _make_sub(
            status=SubscriptionStatus.SUSPENDED,
            api_key_hash="suspended_hash",
        )
        with (
            patch(SUB_REPO) as mock_repo_cls,
            patch(API_KEY_SVC) as mock_key_svc,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_api_key_hash = AsyncMock(return_value=sub)

            mock_key_svc.validate_format.return_value = True
            mock_key_svc.hash_key.return_value = "suspended_hash"

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions/validate-key",
                json={"api_key": "stoa_sk_test1234567890123456"},
            )

            assert resp.status_code == 403

    def test_validate_key_expired_returns_403(self, app_with_tenant_admin):
        """Expired subscription must return 403 on key validation."""
        sub = _make_sub(
            status=SubscriptionStatus.ACTIVE,
            api_key_hash="expired_hash",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        with (
            patch(SUB_REPO) as mock_repo_cls,
            patch(API_KEY_SVC) as mock_key_svc,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_api_key_hash = AsyncMock(return_value=sub)

            mock_key_svc.validate_format.return_value = True
            mock_key_svc.hash_key.return_value = "expired_hash"

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions/validate-key",
                json={"api_key": "stoa_sk_test1234567890123456"},
            )

            assert resp.status_code == 403

    def test_validate_oauth_active_subscription(self, app_with_tenant_admin):
        """Active OAuth subscription validates successfully."""
        sub = _make_sub(
            status=SubscriptionStatus.ACTIVE,
            oauth_client_id="kc-client-oauth",
        )
        with (
            patch(SUB_REPO) as mock_repo_cls,
            patch(PORTAL_APP_REPO) as mock_app_repo_cls,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_oauth_client_and_api = AsyncMock(return_value=sub)

            mock_app = MagicMock()
            mock_app.security_profile = MagicMock(value="oauth2_public")
            mock_app_repo_cls.return_value.get_by_id = AsyncMock(return_value=mock_app)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions/validate-subscription",
                json={"oauth_client_id": "kc-client-oauth", "api_id": "api-1"},
            )

            assert resp.status_code == 200
            assert resp.json()["valid"] is True

    def test_validate_oauth_expired_returns_403(self, app_with_tenant_admin):
        """Expired OAuth subscription must return 403."""
        sub = _make_sub(
            status=SubscriptionStatus.ACTIVE,
            oauth_client_id="kc-client-expired",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        with patch(SUB_REPO) as mock_repo_cls:
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_oauth_client_and_api = AsyncMock(return_value=sub)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions/validate-subscription",
                json={"oauth_client_id": "kc-client-expired", "api_id": "api-1"},
            )

            assert resp.status_code == 403

    def test_validate_oauth_not_found_returns_404(self, app_with_tenant_admin):
        """Non-existent OAuth subscription must return 404."""
        with patch(SUB_REPO) as mock_repo_cls:
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_oauth_client_and_api = AsyncMock(return_value=None)

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions/validate-subscription",
                json={"oauth_client_id": "unknown", "api_id": "api-1"},
            )

            assert resp.status_code == 404

    def test_validate_key_grace_period(self, app_with_tenant_admin):
        """During grace period, previous key must validate with warning."""
        sub = _make_sub(
            status=SubscriptionStatus.ACTIVE,
            previous_api_key_hash="old_hash",
            previous_key_expires_at=datetime.utcnow() + timedelta(hours=12),
        )
        with (
            patch(SUB_REPO) as mock_repo_cls,
            patch(API_KEY_SVC) as mock_key_svc,
        ):
            repo_inst = mock_repo_cls.return_value
            repo_inst.get_by_api_key_hash = AsyncMock(return_value=None)
            repo_inst.get_by_previous_key_hash = AsyncMock(return_value=sub)

            mock_key_svc.validate_format.return_value = True
            mock_key_svc.hash_key.return_value = "old_hash"

            client = TestClient(app_with_tenant_admin)
            resp = client.post(
                "/v1/subscriptions/validate-key",
                json={"api_key": "stoa_sk_test1234567890123456"},
            )

            assert resp.status_code == 200
            data = resp.json()
            assert data["valid"] is True
            assert data["using_previous_key"] is True
            assert "warning" in data
