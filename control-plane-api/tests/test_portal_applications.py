"""
Tests for Portal Applications Router - CAB-1116 Phase 2B

Target: Coverage of src/routers/portal_applications.py
Tests: 15 test cases covering CRUD, ownership checks, pagination, and secret regeneration.
"""


from fastapi.testclient import TestClient


def _clear_applications():
    """Reset in-memory applications storage between tests."""
    import src.routers.portal_applications as pa_mod

    pa_mod._applications.clear()


def _seed_application(user_id="tenant-admin-user-id"):
    """Seed a test application and return its ID."""
    import src.routers.portal_applications as pa_mod

    app_id = "test-app-001"
    pa_mod._applications[app_id] = {
        "id": app_id,
        "name": "test-app",
        "display_name": "Test Application",
        "description": "A test app",
        "client_id": "app-abc123",
        "client_secret_hash": "hashed",
        "tenant_id": "acme",
        "owner_id": user_id,
        "status": "active",
        "redirect_uris": ["https://example.com/callback"],
        "api_subscriptions": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    return app_id


class TestPortalApplicationsRouter:
    """Test suite for Portal Applications Router."""

    # ============== List Applications ==============

    def test_list_applications_empty(self, app_with_tenant_admin):
        """List returns empty when no applications exist."""
        _clear_applications()
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    def test_list_applications_with_data(self, app_with_tenant_admin):
        """List returns user's applications."""
        _clear_applications()
        _seed_application()
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == "test-app-001"

    def test_list_applications_pagination(self, app_with_tenant_admin):
        """Pagination parameters are respected."""
        _clear_applications()
        _seed_application()
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications?page=1&page_size=10")

        assert response.status_code == 200
        data = response.json()
        assert data["pageSize"] == 10

    def test_list_applications_filter_status(self, app_with_tenant_admin):
        """Filter by status works."""
        _clear_applications()
        _seed_application()
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications?status=active")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    def test_list_applications_filter_status_no_match(self, app_with_tenant_admin):
        """Filter by non-matching status returns empty."""
        _clear_applications()
        _seed_application()
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications?status=suspended")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    def test_list_applications_other_user_sees_nothing(self, app_with_other_tenant):
        """User from different tenant/ID sees no applications."""
        _clear_applications()
        _seed_application()  # owned by tenant-admin-user-id
        with TestClient(app_with_other_tenant) as client:
            response = client.get("/v1/applications")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    # ============== Get Application ==============

    def test_get_application_success(self, app_with_tenant_admin):
        """Get application by ID."""
        _clear_applications()
        app_id = _seed_application()
        with TestClient(app_with_tenant_admin) as client:
            response = client.get(f"/v1/applications/{app_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == app_id
        assert data["name"] == "test-app"

    def test_get_application_404(self, app_with_tenant_admin):
        """Get non-existent application returns 404."""
        _clear_applications()
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/applications/nonexistent")

        assert response.status_code == 404

    def test_get_application_403_not_owner(self, app_with_other_tenant):
        """Get application owned by another user returns 403."""
        _clear_applications()
        app_id = _seed_application()
        with TestClient(app_with_other_tenant) as client:
            response = client.get(f"/v1/applications/{app_id}")

        assert response.status_code == 403

    # ============== Create Application ==============

    def test_create_application_success(self, app_with_tenant_admin):
        """Create application returns client_secret."""
        _clear_applications()
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(
                "/v1/applications",
                json={
                    "name": "new-app",
                    "display_name": "New Application",
                    "description": "Created in test",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "new-app"
        assert "client_id" in data
        assert data["client_secret"] is not None  # Only returned on create
        assert data["status"] == "active"

    # ============== Update Application ==============

    def test_update_application_success(self, app_with_tenant_admin):
        """Update application fields."""
        _clear_applications()
        app_id = _seed_application()
        with TestClient(app_with_tenant_admin) as client:
            response = client.patch(
                f"/v1/applications/{app_id}",
                json={"display_name": "Updated Name"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "Updated Name"

    def test_update_application_403_not_owner(self, app_with_other_tenant):
        """Update application by non-owner returns 403."""
        _clear_applications()
        app_id = _seed_application()
        with TestClient(app_with_other_tenant) as client:
            response = client.patch(
                f"/v1/applications/{app_id}",
                json={"display_name": "Hacked"},
            )

        assert response.status_code == 403

    # ============== Delete Application ==============

    def test_delete_application_success(self, app_with_tenant_admin):
        """Delete application owned by user."""
        _clear_applications()
        app_id = _seed_application()
        with TestClient(app_with_tenant_admin) as client:
            response = client.delete(f"/v1/applications/{app_id}")

        assert response.status_code == 200
        assert response.json()["message"] == "Application deleted"

    def test_delete_application_404(self, app_with_tenant_admin):
        """Delete non-existent application returns 404."""
        _clear_applications()
        with TestClient(app_with_tenant_admin) as client:
            response = client.delete("/v1/applications/nonexistent")

        assert response.status_code == 404

    def test_delete_application_403_not_owner(self, app_with_other_tenant):
        """Delete application by non-owner returns 403."""
        _clear_applications()
        app_id = _seed_application()
        with TestClient(app_with_other_tenant) as client:
            response = client.delete(f"/v1/applications/{app_id}")

        assert response.status_code == 403

    # ============== Regenerate Secret ==============

    def test_regenerate_secret_success(self, app_with_tenant_admin):
        """Regenerate secret returns new client secret."""
        _clear_applications()
        app_id = _seed_application()
        with TestClient(app_with_tenant_admin) as client:
            response = client.post(f"/v1/applications/{app_id}/regenerate-secret")

        assert response.status_code == 200
        data = response.json()
        assert "clientSecret" in data
        assert len(data["clientSecret"]) > 10

    def test_regenerate_secret_404(self, app_with_tenant_admin):
        """Regenerate secret for non-existent app returns 404."""
        _clear_applications()
        with TestClient(app_with_tenant_admin) as client:
            response = client.post("/v1/applications/nonexistent/regenerate-secret")

        assert response.status_code == 404

    def test_regenerate_secret_403_not_owner(self, app_with_other_tenant):
        """Regenerate secret by non-owner returns 403."""
        _clear_applications()
        app_id = _seed_application()
        with TestClient(app_with_other_tenant) as client:
            response = client.post(f"/v1/applications/{app_id}/regenerate-secret")

        assert response.status_code == 403
