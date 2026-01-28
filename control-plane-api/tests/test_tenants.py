# SPDX-License-Identifier: Apache-2.0
# Copyright 2024-2026 CAB Ingénierie / Christophe ABOULICAM
"""
Tests for Tenants Router - CAB-839

Target: 80%+ coverage on src/routers/tenants.py
Tests: 10 test cases covering CRUD, RBAC, and multi-tenant isolation
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from fastapi.testclient import TestClient


class TestTenantsRouter:
    """Test suite for Tenants Router endpoints."""

    # ============== List Tenants Tests ==============

    def test_list_tenants_cpi_admin_sees_all(
        self, app_with_cpi_admin, mock_db_session, sample_tenant_data
    ):
        """Test CPI Admin can see all tenants."""
        tenant_tree = [
            {"name": "acme", "type": "tree"},
            {"name": "beta-corp", "type": "tree"},
        ]

        with patch("src.routers.tenants.git_service") as mock_git:
            mock_git._project = MagicMock()
            mock_git._project.repository_tree.return_value = tenant_tree
            mock_git.get_tenant = AsyncMock(return_value=sample_tenant_data)
            mock_git.list_apis = AsyncMock(return_value=[{"id": "api-1"}])

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/tenants")

            assert response.status_code == 200
            data = response.json()
            # CPI admin should see multiple tenants
            assert isinstance(data, list)
            assert len(data) >= 1

    def test_list_tenants_tenant_admin_sees_own(
        self, app_with_tenant_admin, mock_db_session, sample_tenant_data
    ):
        """Test Tenant Admin can only see their own tenant."""
        with patch("src.routers.tenants.git_service") as mock_git:
            mock_git.get_tenant = AsyncMock(return_value=sample_tenant_data)
            mock_git.list_apis = AsyncMock(return_value=[])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/tenants")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            # Tenant admin sees only their own tenant
            assert len(data) == 1
            assert data[0]["id"] == "acme"

    # ============== Get Tenant Tests ==============

    def test_get_tenant_success(
        self, app_with_tenant_admin, mock_db_session, sample_tenant_data
    ):
        """Test getting tenant details by ID."""
        with patch("src.routers.tenants.git_service") as mock_git:
            mock_git.get_tenant = AsyncMock(return_value=sample_tenant_data)
            mock_git.list_apis = AsyncMock(return_value=[{"id": "api-1"}, {"id": "api-2"}])

            with TestClient(app_with_tenant_admin) as client:
                response = client.get("/v1/tenants/acme")

            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "acme"
            assert data["display_name"] == "ACME Corporation"
            assert data["api_count"] == 2

    def test_get_tenant_404(self, app_with_cpi_admin, mock_db_session):
        """Test getting non-existent tenant returns 404."""
        with patch("src.routers.tenants.git_service") as mock_git:
            mock_git.get_tenant = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/tenants/nonexistent")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_get_tenant_403_wrong_tenant(self, app_with_other_tenant, mock_db_session):
        """Test user from different tenant cannot access another tenant."""
        # User is from 'other-tenant', trying to access 'acme'
        with TestClient(app_with_other_tenant) as client:
            response = client.get("/v1/tenants/acme")

        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    # ============== Create Tenant Tests ==============

    def test_create_tenant_cpi_admin(self, app_with_cpi_admin, mock_db_session):
        """Test CPI Admin can create a new tenant."""
        with patch("src.routers.tenants.git_service") as mock_git, \
             patch("src.routers.tenants.keycloak_service") as mock_keycloak, \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_git.create_tenant_structure = AsyncMock(return_value=True)
            mock_keycloak.setup_tenant_group = AsyncMock(return_value=True)
            mock_kafka.publish = AsyncMock(return_value=True)
            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/v1/tenants",
                    json={
                        "name": "New Tenant",
                        "display_name": "New Tenant Corp",
                        "description": "A new test tenant",
                        "owner_email": "owner@newtenant.com",
                    },
                )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "New Tenant"
            assert data["display_name"] == "New Tenant Corp"
            assert data["status"] == "active"

    def test_create_tenant_403_not_admin(self, app_with_tenant_admin, mock_db_session):
        """Test non-admin cannot create tenant."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/tenants",
                json={
                    "name": "Unauthorized Tenant",
                    "display_name": "Should Fail",
                    "description": "This should be denied",
                    "owner_email": "fail@example.com",
                },
            )

        assert response.status_code == 403

    # ============== Update Tenant Tests ==============

    def test_update_tenant_success(
        self, app_with_cpi_admin, mock_db_session, sample_tenant_data
    ):
        """Test CPI Admin can update tenant."""
        updated_data = sample_tenant_data.copy()
        updated_data["display_name"] = "Updated ACME Corp"

        with patch("src.routers.tenants.git_service") as mock_git, \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_git.get_tenant = AsyncMock(return_value=sample_tenant_data)
            mock_git.list_apis = AsyncMock(return_value=[])
            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    "/v1/tenants/acme",
                    json={"display_name": "Updated ACME Corp"},
                )

            assert response.status_code == 200
            data = response.json()
            assert data["display_name"] == "Updated ACME Corp"

    # ============== Delete Tenant Tests ==============

    def test_delete_tenant_400_has_apis(
        self, app_with_cpi_admin, mock_db_session, sample_tenant_data
    ):
        """Test cannot delete tenant that has APIs (safety check)."""
        with patch("src.routers.tenants.git_service") as mock_git:
            mock_git.get_tenant = AsyncMock(return_value=sample_tenant_data)
            mock_git.list_apis = AsyncMock(return_value=[
                {"id": "api-1", "name": "Weather API"},
                {"id": "api-2", "name": "Payment API"},
            ])

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete("/v1/tenants/acme")

            assert response.status_code == 400
            assert "Cannot delete tenant with" in response.json()["detail"]
            assert "APIs" in response.json()["detail"]

    def test_delete_tenant_success(
        self, app_with_cpi_admin, mock_db_session, sample_tenant_data
    ):
        """Test CPI Admin can delete empty tenant."""
        with patch("src.routers.tenants.git_service") as mock_git, \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_git.get_tenant = AsyncMock(return_value=sample_tenant_data)
            mock_git.list_apis = AsyncMock(return_value=[])  # No APIs
            mock_kafka.publish = AsyncMock(return_value=True)
            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete("/v1/tenants/acme")

            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Tenant deleted"
            assert data["id"] == "acme"

    # ============== Phase 2: Error Handling Tests ==============

    def test_list_tenants_git_error_returns_empty(
        self, app_with_cpi_admin
    ):
        """Test list tenants returns empty list when git service fails."""
        with patch("src.routers.tenants.git_service") as mock_git:
            mock_git._project = MagicMock()
            mock_git._project.repository_tree.side_effect = Exception("GitLab connection failed")

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/tenants")

            assert response.status_code == 200
            data = response.json()
            assert data == []  # Returns empty list on error

    def test_get_tenant_k8s_format(
        self, app_with_cpi_admin
    ):
        """Test getting tenant with Kubernetes-style data format."""
        k8s_tenant_data = {
            "metadata": {
                "name": "acme",
                "displayName": "ACME Corporation",
                "description": "Test tenant in K8s format",
            },
            "spec": {
                "status": "active",
                "contact": {
                    "email": "admin@acme.com"
                },
                "created_at": "2025-01-01T00:00:00Z"
            }
        }

        with patch("src.routers.tenants.git_service") as mock_git:
            mock_git.get_tenant = AsyncMock(return_value=k8s_tenant_data)
            mock_git.list_apis = AsyncMock(return_value=["api1", "api2"])

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/tenants/acme")

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "acme"
            assert data["display_name"] == "ACME Corporation"
            assert data["owner_email"] == "admin@acme.com"
            assert data["api_count"] == 2

    def test_update_tenant_404(
        self, app_with_cpi_admin
    ):
        """Test updating non-existent tenant returns 404."""
        with patch("src.routers.tenants.git_service") as mock_git:
            mock_git.get_tenant = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    "/v1/tenants/nonexistent",
                    json={"display_name": "Updated Name"}
                )

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    def test_delete_tenant_404(
        self, app_with_cpi_admin
    ):
        """Test deleting non-existent tenant returns 404."""
        with patch("src.routers.tenants.git_service") as mock_git:
            mock_git.get_tenant = AsyncMock(return_value=None)

            with TestClient(app_with_cpi_admin) as client:
                response = client.delete("/v1/tenants/nonexistent")

            assert response.status_code == 404
            assert "not found" in response.json()["detail"]

    # ============== Phase 3: Keycloak Failure Handling (Lines 185-188) ==============

    def test_create_tenant_keycloak_failure(self, app_with_cpi_admin, mock_db_session):
        """Test POST / succeeds even if Keycloak setup fails."""
        with patch("src.routers.tenants.git_service") as mock_git, \
             patch("src.routers.tenants.keycloak_service") as mock_keycloak, \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_git.create_tenant_structure = AsyncMock(return_value=True)
            # Keycloak fails but should not block tenant creation
            mock_keycloak.setup_tenant_group = AsyncMock(side_effect=Exception("Keycloak unavailable"))
            mock_kafka.publish = AsyncMock(return_value=True)
            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                response = client.post(
                    "/v1/tenants",
                    json={
                        "name": "New Tenant",
                        "display_name": "New Tenant Corp",
                        "description": "A new test tenant",
                        "owner_email": "owner@newtenant.com",
                    },
                )

            # Should still succeed despite Keycloak failure
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "New Tenant"
            assert data["status"] == "active"

    # ============== Phase 3: Update No-op (Lines 248-250) ==============

    def test_update_tenant_no_changes(
        self, app_with_cpi_admin, sample_tenant_data
    ):
        """Test PUT /{id} with no changes returns current data (no-op)."""
        with patch("src.routers.tenants.git_service") as mock_git, \
             patch("src.routers.tenants.kafka_service") as mock_kafka:

            mock_git.get_tenant = AsyncMock(return_value=sample_tenant_data)
            mock_git.list_apis = AsyncMock(return_value=[])
            # emit_audit_event should NOT be called for no-op update
            mock_kafka.emit_audit_event = AsyncMock(return_value=True)

            with TestClient(app_with_cpi_admin) as client:
                # Send empty update (all fields None)
                response = client.put(
                    "/v1/tenants/acme",
                    json={}  # No changes
                )

            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "acme"
            # Verify audit event was NOT called (no-op path doesn't call it)
            assert not mock_kafka.emit_audit_event.called

    # ============== Phase 3: Git Error on Update (Lines 274-276) ==============

    def test_update_tenant_git_error(
        self, app_with_cpi_admin
    ):
        """Test PUT /{id} when GitLab fails → 500 with detail."""
        with patch("src.routers.tenants.git_service") as mock_git:
            # get_tenant succeeds but then something fails during update
            mock_git.get_tenant = AsyncMock(side_effect=Exception("GitLab connection timeout"))

            with TestClient(app_with_cpi_admin) as client:
                response = client.put(
                    "/v1/tenants/acme",
                    json={"display_name": "Updated Name"}
                )

            assert response.status_code == 500
            assert "Failed to update tenant" in response.json()["detail"]
