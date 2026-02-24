"""Tests for Demo Router — CAB-1304

Covers:
- GET  /v1/demo/status — check demo tenant state (cpi-admin only)
- POST /v1/demo/seed   — seed demo tenant (idempotent, cpi-admin only)
- POST /v1/demo/reset  — reset demo tenant (delete + re-seed, cpi-admin only)

All endpoints require cpi-admin role. Tenant-admin and unauthenticated are rejected.
"""

from unittest.mock import AsyncMock, patch

CHECK_PATH = "scripts.seed_demo_tenant.check_demo_state"
SEED_PATH = "scripts.seed_demo_tenant.seed_demo_tenant"
DELETE_PATH = "scripts.seed_demo_tenant.delete_demo_data"


def _demo_counts(exists: bool = True) -> dict:
    """Return demo state counts dict."""
    if not exists:
        return {
            "tenants": 0,
            "mcp_servers": 0,
            "mcp_server_tools": 0,
            "consumers": 0,
            "mcp_server_subscriptions": 0,
            "api_catalog": 0,
        }
    return {
        "tenants": 1,
        "mcp_servers": 3,
        "mcp_server_tools": 7,
        "consumers": 3,
        "mcp_server_subscriptions": 6,
        "api_catalog": 3,
    }


def _seed_summary() -> dict:
    """Return seed result summary."""
    return {
        "tenant": 1,
        "servers": 3,
        "tools": 7,
        "consumers": 3,
        "subscriptions": 6,
        "catalog": 3,
    }


# ---------------------------------------------------------------------------
# GET /v1/demo/status
# ---------------------------------------------------------------------------


class TestGetDemoStatus:
    """GET /v1/demo/status"""

    def test_status_exists(self, client_as_cpi_admin):
        """Returns demo tenant status with counts when tenant exists."""
        with patch(CHECK_PATH, new_callable=AsyncMock, return_value=_demo_counts(True)):
            resp = client_as_cpi_admin.get("/v1/demo/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is True
        assert data["tenants"] == 1
        assert data["mcp_servers"] == 3
        assert data["tools"] == 7
        assert data["consumers"] == 3
        assert data["subscriptions"] == 6
        assert data["catalog_apis"] == 3

    def test_status_not_exists(self, client_as_cpi_admin):
        """Returns exists=false when no demo tenant."""
        with patch(CHECK_PATH, new_callable=AsyncMock, return_value=_demo_counts(False)):
            resp = client_as_cpi_admin.get("/v1/demo/status")

        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["tenants"] == 0

    def test_status_requires_cpi_admin(self, client_as_tenant_admin):
        """Tenant-admin is rejected (requires cpi-admin)."""
        resp = client_as_tenant_admin.get("/v1/demo/status")
        assert resp.status_code == 403

    def test_status_unauthenticated(self, client):
        """Unauthenticated request is rejected."""
        resp = client.get("/v1/demo/status")
        assert resp.status_code in (401, 403, 422)


# ---------------------------------------------------------------------------
# POST /v1/demo/seed
# ---------------------------------------------------------------------------


class TestSeedDemo:
    """POST /v1/demo/seed"""

    def test_seed_creates_demo(self, client_as_cpi_admin):
        """Seeds demo tenant when none exists."""
        with (
            patch(CHECK_PATH, new_callable=AsyncMock, return_value=_demo_counts(False)),
            patch(SEED_PATH, new_callable=AsyncMock, return_value=_seed_summary()),
        ):
            resp = client_as_cpi_admin.post("/v1/demo/seed")

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "seeded"
        assert data["tenant_created"] == 1
        assert data["servers_created"] == 3
        assert data["tools_created"] == 7
        assert data["consumers_created"] == 3
        assert data["subscriptions_created"] == 6
        assert data["catalog_apis_created"] == 3
        assert "successfully" in data["message"]

    def test_seed_skips_if_exists(self, client_as_cpi_admin):
        """Skips seeding when demo tenant already exists."""
        with patch(CHECK_PATH, new_callable=AsyncMock, return_value=_demo_counts(True)):
            resp = client_as_cpi_admin.post("/v1/demo/seed")

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "skipped"
        assert "already exists" in data["message"]

    def test_seed_error_returns_500(self, client_as_cpi_admin):
        """Seed failure returns 500 with detail."""
        with (
            patch(CHECK_PATH, new_callable=AsyncMock, return_value=_demo_counts(False)),
            patch(SEED_PATH, new_callable=AsyncMock, side_effect=RuntimeError("DB connection failed")),
        ):
            resp = client_as_cpi_admin.post("/v1/demo/seed")

        assert resp.status_code == 500
        assert "Seed failed" in resp.json()["detail"]

    def test_seed_requires_cpi_admin(self, client_as_tenant_admin):
        """Tenant-admin is rejected."""
        resp = client_as_tenant_admin.post("/v1/demo/seed")
        assert resp.status_code == 403

    def test_seed_unauthenticated(self, client):
        """Unauthenticated request is rejected."""
        resp = client.post("/v1/demo/seed")
        assert resp.status_code in (401, 403, 422)


# ---------------------------------------------------------------------------
# POST /v1/demo/reset
# ---------------------------------------------------------------------------


class TestResetDemo:
    """POST /v1/demo/reset"""

    def test_reset_deletes_and_reseeds(self, client_as_cpi_admin):
        """Reset deletes existing data and re-seeds."""
        with (
            patch(DELETE_PATH, new_callable=AsyncMock, return_value=42),
            patch(SEED_PATH, new_callable=AsyncMock, return_value=_seed_summary()),
        ):
            resp = client_as_cpi_admin.post("/v1/demo/reset")

        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "reset"
        assert data["tenant_created"] == 1
        assert data["servers_created"] == 3
        assert "deleted 42 rows" in data["message"]

    def test_reset_error_returns_500(self, client_as_cpi_admin):
        """Reset failure returns 500 with detail."""
        with patch(DELETE_PATH, new_callable=AsyncMock, side_effect=RuntimeError("FK violation")):
            resp = client_as_cpi_admin.post("/v1/demo/reset")

        assert resp.status_code == 500
        assert "Reset failed" in resp.json()["detail"]

    def test_reset_requires_cpi_admin(self, client_as_tenant_admin):
        """Tenant-admin is rejected."""
        resp = client_as_tenant_admin.post("/v1/demo/reset")
        assert resp.status_code == 403

    def test_reset_unauthenticated(self, client):
        """Unauthenticated request is rejected."""
        resp = client.post("/v1/demo/reset")
        assert resp.status_code in (401, 403, 422)
