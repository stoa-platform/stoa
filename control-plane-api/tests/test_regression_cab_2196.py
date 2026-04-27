"""Regression tests for CAB-2196 (archived tenant blocks recreate even after failed bootstrap)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.models.tenant import Tenant


def _archived_tenant(tenant_id, kc_group_id, provisioning_status="failed"):
    t = MagicMock(spec=Tenant)
    t.id = tenant_id
    t.name = "Whatever"
    t.description = ""
    t.status = "archived"
    t.provisioning_status = provisioning_status
    t.kc_group_id = kc_group_id
    t.settings = {"owner_email": "x@x.com"}
    t.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    t.updated_at = datetime(2025, 1, 1, tzinfo=UTC)
    return t


PAYLOAD = {
    "name": "demo-gitops",
    "display_name": "Demo GitOps",
    "description": "x",
    "owner_email": "owner@x.com",
}


class TestRegressionCab2196:
    def test_regression_cab_2196_recreate_when_archived_and_kc_group_id_null(
        self, app_with_cpi_admin, mock_db_session
    ):
        # Tenant row archived after a failed bootstrap (never got a KC group).
        # Re-applying the same name must succeed: the old row is purged and a
        # fresh row is created. Without this gate, POST /v1/tenants 409s and
        # the ID is permanently locked. Surfaced by CAB-2195.
        archived = _archived_tenant("demo-gitops", kc_group_id=None)
        created = MagicMock(spec=Tenant)
        created.id = "demo-gitops"
        created.name = "Demo GitOps"
        created.description = "x"
        created.status = "active"
        created.provisioning_status = "pending"
        created.settings = {"owner_email": "owner@x.com"}
        created.created_at = datetime(2025, 1, 1, tzinfo=UTC)
        created.updated_at = datetime(2025, 1, 1, tzinfo=UTC)

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=archived)
        mock_repo.delete = AsyncMock()
        mock_repo.create = AsyncMock(return_value=created)

        with (
            patch("src.routers.tenants.TenantRepository", return_value=mock_repo),
            patch("src.routers.tenants.provision_tenant", new_callable=AsyncMock),
            patch("src.routers.tenants.kafka_service") as mock_kafka,
        ):
            mock_kafka.publish = AsyncMock(return_value=True)
            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post("/v1/tenants", json=PAYLOAD)

        assert response.status_code == 200, response.text
        mock_repo.delete.assert_awaited_once_with(archived)
        mock_repo.create.assert_awaited_once()
        # Audit event for the recreate must be emitted in addition to the
        # normal "create" event.
        actions = [c.kwargs.get("action") for c in mock_kafka.emit_audit_event.await_args_list]
        assert "recreate-from-failed-bootstrap" in actions

    def test_regression_cab_2196_archived_with_kc_group_id_still_409(
        self, app_with_cpi_admin, mock_db_session
    ):
        # Archived row that DID successfully provision (has a kc_group_id) is
        # a real decommissioned tenant — re-using the ID is a compliance
        # concern and must remain blocked.
        archived = _archived_tenant(
            "ex-tenant", kc_group_id="aaaa-bbbb-cccc", provisioning_status="ready"
        )

        mock_repo = MagicMock()
        mock_repo.get_by_id = AsyncMock(return_value=archived)
        mock_repo.delete = AsyncMock()
        mock_repo.create = AsyncMock()

        with (
            patch("src.routers.tenants.TenantRepository", return_value=mock_repo),
            TestClient(app_with_cpi_admin) as client,
        ):
            response = client.post(
                "/v1/tenants",
                json={**PAYLOAD, "name": "ex-tenant"},
            )

        assert response.status_code == 409
        assert "already exists" in response.json()["detail"]
        mock_repo.delete.assert_not_called()
        mock_repo.create.assert_not_called()
