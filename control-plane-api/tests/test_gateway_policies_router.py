"""Tests for Gateway Policies Router — CAB-1436

Covers: /v1/admin/policies (CRUD + bindings)
- Create, list, get, update, delete policies
- Create, delete, list bindings
- RBAC (cpi-admin, tenant-admin)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

POLICY_REPO = "src.routers.gateway_policies.GatewayPolicyRepository"
BINDING_REPO = "src.routers.gateway_policies.GatewayPolicyBindingRepository"
KAFKA_SVC = "src.routers.gateway_policies.kafka_service"
BASE = "/v1/admin/policies"

POLICY_ID = uuid4()
BINDING_ID = uuid4()


def _mock_policy(**overrides):
    """Create a mock GatewayPolicy."""
    mock = MagicMock()
    defaults = {
        "id": POLICY_ID,
        "name": "rate-limit-gold",
        "description": "Gold tier rate limiting",
        "policy_type": MagicMock(value="rate_limit"),
        "tenant_id": "acme",
        "scope": MagicMock(value="api"),
        "config": {"requests_per_minute": 1000},
        "priority": 10,
        "enabled": True,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
        "bindings": [],
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


API_CATALOG_ID = uuid4()
GW_INSTANCE_ID = uuid4()


def _mock_binding(**overrides):
    """Create a mock GatewayPolicyBinding."""
    mock = MagicMock()
    defaults = {
        "id": BINDING_ID,
        "policy_id": POLICY_ID,
        "api_catalog_id": API_CATALOG_ID,
        "gateway_instance_id": GW_INSTANCE_ID,
        "tenant_id": "acme",
        "enabled": True,
        "created_at": "2026-01-01T00:00:00",
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


class TestCreatePolicy:
    """Tests for POST /v1/admin/policies."""

    def test_create_success(self, app_with_cpi_admin, mock_db_session):
        policy = _mock_policy()
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=policy)
        mock_kafka = MagicMock()
        mock_kafka.emit_policy_created = AsyncMock(return_value="evt-1")

        with (
            patch(POLICY_REPO, return_value=mock_repo),
            patch(KAFKA_SVC, mock_kafka),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                BASE,
                json={
                    "name": "rate-limit-gold",
                    "description": "Gold tier",
                    "policy_type": "rate_limit",
                    "tenant_id": "acme",
                    "scope": "api",
                    "config": {"requests_per_minute": 1000},
                    "priority": 10,
                    "enabled": True,
                },
            )

        assert resp.status_code == 201
        assert resp.json()["name"] == "rate-limit-gold"
        mock_kafka.emit_policy_created.assert_called_once()

    def test_create_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        with TestClient(app_with_no_tenant_user) as client:
            resp = client.post(BASE, json={"name": "x", "policy_type": "rate_limit", "scope": "api"})

        assert resp.status_code == 403


class TestListPolicies:
    """Tests for GET /v1/admin/policies."""

    def test_list_success(self, app_with_cpi_admin, mock_db_session):
        policy = _mock_policy()
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=[policy])

        with patch(POLICY_REPO, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.get(BASE)

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_with_filters(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.list_all = AsyncMock(return_value=[])

        with patch(POLICY_REPO, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"{BASE}?tenant_id=acme&policy_type=rate_limit")

        assert resp.status_code == 200


class TestGetPolicy:
    """Tests for GET /v1/admin/policies/{policy_id}."""

    def test_get_success(self, app_with_cpi_admin, mock_db_session):
        policy = _mock_policy()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=policy)

        with patch(POLICY_REPO, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"{BASE}/{POLICY_ID}")

        assert resp.status_code == 200
        assert resp.json()["name"] == "rate-limit-gold"

    def test_get_404(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(POLICY_REPO, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"{BASE}/{uuid4()}")

        assert resp.status_code == 404


class TestUpdatePolicy:
    """Tests for PUT /v1/admin/policies/{policy_id}."""

    def test_update_success(self, app_with_cpi_admin, mock_db_session):
        policy = _mock_policy()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=policy)
        mock_repo.update = AsyncMock(return_value=policy)
        mock_kafka = MagicMock()
        mock_kafka.emit_policy_updated = AsyncMock(return_value="evt-2")

        with (
            patch(POLICY_REPO, return_value=mock_repo),
            patch(KAFKA_SVC, mock_kafka),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.put(
                f"{BASE}/{POLICY_ID}",
                json={
                    "name": "updated-policy",
                    "description": "Updated",
                    "config": {"requests_per_minute": 2000},
                    "priority": 5,
                    "enabled": False,
                },
            )

        assert resp.status_code == 200
        mock_kafka.emit_policy_updated.assert_called_once()

    def test_update_404(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(POLICY_REPO, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.put(f"{BASE}/{uuid4()}", json={"name": "x"})

        assert resp.status_code == 404


class TestDeletePolicy:
    """Tests for DELETE /v1/admin/policies/{policy_id}."""

    def test_delete_success(self, app_with_cpi_admin, mock_db_session):
        policy = _mock_policy()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=policy)
        mock_repo.delete = AsyncMock()
        mock_kafka = MagicMock()
        mock_kafka.emit_policy_deleted = AsyncMock(return_value="evt-3")

        with (
            patch(POLICY_REPO, return_value=mock_repo),
            patch(KAFKA_SVC, mock_kafka),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.delete(f"{BASE}/{POLICY_ID}")

        assert resp.status_code == 204
        mock_kafka.emit_policy_deleted.assert_called_once()

    def test_delete_404(self, app_with_cpi_admin, mock_db_session):
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=None)

        with patch(POLICY_REPO, return_value=mock_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.delete(f"{BASE}/{uuid4()}")

        assert resp.status_code == 404

    def test_delete_403_tenant_admin(self, app_with_tenant_admin, mock_db_session):
        """Only cpi-admin can delete policies."""
        with TestClient(app_with_tenant_admin) as client:
            resp = client.delete(f"{BASE}/{POLICY_ID}")

        assert resp.status_code == 403


class TestCreateBinding:
    """Tests for POST /v1/admin/policies/bindings."""

    def test_create_binding_success(self, app_with_cpi_admin, mock_db_session):
        policy = _mock_policy()
        binding = _mock_binding()
        mock_policy_repo = MagicMock()
        mock_policy_repo.get_by_id = AsyncMock(return_value=policy)
        mock_binding_repo = MagicMock()
        mock_binding_repo.create = AsyncMock(return_value=binding)
        mock_kafka = MagicMock()
        mock_kafka.emit_policy_binding_created = AsyncMock(return_value="evt-4")

        with (
            patch(POLICY_REPO, return_value=mock_policy_repo),
            patch(BINDING_REPO, return_value=mock_binding_repo),
            patch(KAFKA_SVC, mock_kafka),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                f"{BASE}/bindings",
                json={
                    "policy_id": str(POLICY_ID),
                    "api_catalog_id": str(API_CATALOG_ID),
                    "gateway_instance_id": str(GW_INSTANCE_ID),
                    "tenant_id": "acme",
                    "enabled": True,
                },
            )

        assert resp.status_code == 201
        mock_kafka.emit_policy_binding_created.assert_called_once()

    def test_create_binding_policy_not_found(self, app_with_cpi_admin, mock_db_session):
        mock_policy_repo = MagicMock()
        mock_policy_repo.get_by_id = AsyncMock(return_value=None)

        with patch(POLICY_REPO, return_value=mock_policy_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.post(
                f"{BASE}/bindings",
                json={
                    "policy_id": str(uuid4()),
                    "api_catalog_id": str(uuid4()),
                },
            )

        assert resp.status_code == 404


class TestDeleteBinding:
    """Tests for DELETE /v1/admin/policies/bindings/{binding_id}."""

    def test_delete_binding_success(self, app_with_cpi_admin, mock_db_session):
        binding = _mock_binding()
        mock_binding_repo = MagicMock()
        mock_binding_repo.get_by_id = AsyncMock(return_value=binding)
        mock_binding_repo.delete = AsyncMock()
        mock_kafka = MagicMock()
        mock_kafka.emit_policy_binding_deleted = AsyncMock(return_value="evt-5")

        with (
            patch(BINDING_REPO, return_value=mock_binding_repo),
            patch(KAFKA_SVC, mock_kafka),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.delete(f"{BASE}/bindings/{BINDING_ID}")

        assert resp.status_code == 204
        mock_kafka.emit_policy_binding_deleted.assert_called_once()

    def test_delete_binding_404(self, app_with_cpi_admin, mock_db_session):
        mock_binding_repo = MagicMock()
        mock_binding_repo.get_by_id = AsyncMock(return_value=None)

        with patch(BINDING_REPO, return_value=mock_binding_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.delete(f"{BASE}/bindings/{uuid4()}")

        assert resp.status_code == 404


class TestListBindings:
    """Tests for GET /v1/admin/policies/{policy_id}/bindings."""

    def test_list_bindings_success(self, app_with_cpi_admin, mock_db_session):
        policy = _mock_policy()
        binding = _mock_binding()
        mock_policy_repo = MagicMock()
        mock_policy_repo.get_by_id = AsyncMock(return_value=policy)
        mock_binding_repo = MagicMock()
        mock_binding_repo.list_by_policy = AsyncMock(return_value=[binding])

        with (
            patch(POLICY_REPO, return_value=mock_policy_repo),
            patch(BINDING_REPO, return_value=mock_binding_repo),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.get(f"{BASE}/{POLICY_ID}/bindings")

        assert resp.status_code == 200

    def test_list_bindings_policy_not_found(self, app_with_cpi_admin, mock_db_session):
        mock_policy_repo = MagicMock()
        mock_policy_repo.get_by_id = AsyncMock(return_value=None)

        with patch(POLICY_REPO, return_value=mock_policy_repo), TestClient(app_with_cpi_admin) as client:
            resp = client.get(f"{BASE}/{uuid4()}/bindings")

        assert resp.status_code == 404


class TestKafkaResilience:
    """Kafka failures must not break policy CRUD responses."""

    def test_create_succeeds_when_kafka_fails(self, app_with_cpi_admin, mock_db_session):
        policy = _mock_policy()
        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(return_value=policy)
        mock_kafka = MagicMock()
        mock_kafka.emit_policy_created = AsyncMock(side_effect=RuntimeError("Kafka down"))

        with (
            patch(POLICY_REPO, return_value=mock_repo),
            patch(KAFKA_SVC, mock_kafka),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                BASE,
                json={
                    "name": "rate-limit-gold",
                    "policy_type": "rate_limit",
                    "tenant_id": "acme",
                    "scope": "api",
                    "config": {},
                },
            )

        assert resp.status_code == 201

    def test_delete_succeeds_when_kafka_fails(self, app_with_cpi_admin, mock_db_session):
        policy = _mock_policy()
        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=policy)
        mock_repo.delete = AsyncMock()
        mock_kafka = MagicMock()
        mock_kafka.emit_policy_deleted = AsyncMock(side_effect=RuntimeError("Kafka down"))

        with (
            patch(POLICY_REPO, return_value=mock_repo),
            patch(KAFKA_SVC, mock_kafka),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.delete(f"{BASE}/{POLICY_ID}")

        assert resp.status_code == 204
