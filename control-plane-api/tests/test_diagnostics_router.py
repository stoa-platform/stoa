"""Tests for Diagnostics Router — CAB-1436

Covers: /v1/admin/diagnostics (run, connectivity, history)
Router-level tests (distinct from test_diagnostic.py which tests the service).

Note: The diagnostics router uses `user: dict = Depends(require_role(...))` and calls
`user.get("tenant_id", "")`. Since require_role returns a User object, tests must
patch require_role to return a dict to match the router's actual usage.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


SVC_PATH = "src.routers.diagnostics.DiagnosticService"
REQUIRE_ROLE_PATH = "src.routers.diagnostics.require_role"


def _mock_diagnostic_report():
    """Create a mock DiagnosticReport."""
    return MagicMock(
        tenant_id="acme",
        gateway_id="gw-1",
        redacted=True,
        request_summary=None,
        causes=[],
        timing=None,
        network_path=None,
    )


def _admin_user_dict():
    """Return a dict matching what the diagnostics router expects."""
    return {"id": "admin-user-id", "roles": ["cpi-admin"], "tenant_id": ""}


def _tenant_admin_dict():
    """Return a dict matching what the diagnostics router expects."""
    return {"id": "tenant-admin-user-id", "roles": ["tenant-admin"], "tenant_id": "acme"}


def _patch_require_role(user_dict):
    """Patch require_role to return a dependency that yields the given dict."""

    def fake_require_role(allowed_roles):
        async def dep():
            if not any(r in user_dict.get("roles", []) for r in allowed_roles):
                from fastapi import HTTPException

                raise HTTPException(status_code=403, detail="Access denied")
            return user_dict

        return dep

    return patch(REQUIRE_ROLE_PATH, side_effect=fake_require_role)


class TestRunDiagnostic:
    """Tests for GET /v1/admin/diagnostics/{gateway_id}."""

    def test_run_diagnostic_success(self, app, mock_db_session):
        """CPI admin runs diagnostic on a gateway."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        report = _mock_diagnostic_report()
        mock_svc = MagicMock()
        mock_svc.diagnose = AsyncMock(return_value=report)

        with _patch_require_role(_admin_user_dict()), patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app) as client:
                gw_id = uuid4()
                resp = client.get(f"/v1/admin/diagnostics/{gw_id}")

        assert resp.status_code == 200
        app.dependency_overrides.clear()

    def test_run_diagnostic_with_params(self, app, mock_db_session):
        """CPI admin runs diagnostic with custom time range and request_id."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        report = _mock_diagnostic_report()
        mock_svc = MagicMock()
        mock_svc.diagnose = AsyncMock(return_value=report)

        with _patch_require_role(_admin_user_dict()), patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app) as client:
                gw_id = uuid4()
                resp = client.get(
                    f"/v1/admin/diagnostics/{gw_id}?time_range_minutes=120&request_id=req-001"
                )

        assert resp.status_code == 200
        mock_svc.diagnose.assert_called_once()
        call_kwargs = mock_svc.diagnose.call_args
        assert call_kwargs.kwargs.get("time_range_minutes") == 120
        assert call_kwargs.kwargs.get("request_id") == "req-001"
        app.dependency_overrides.clear()

    def test_run_diagnostic_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        """Viewer (no admin role) is denied access."""
        with TestClient(app_with_no_tenant_user) as client:
            gw_id = uuid4()
            resp = client.get(f"/v1/admin/diagnostics/{gw_id}")

        assert resp.status_code == 403


class TestCheckConnectivity:
    """Tests for GET /v1/admin/diagnostics/{gateway_id}/connectivity."""

    def test_connectivity_success(self, app, mock_db_session):
        """CPI admin checks connectivity for a gateway."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        result = MagicMock(overall_status="healthy", stages=[])
        mock_svc = MagicMock()
        mock_svc.check_connectivity = AsyncMock(return_value=result)

        with _patch_require_role(_admin_user_dict()), patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app) as client:
                gw_id = uuid4()
                resp = client.get(f"/v1/admin/diagnostics/{gw_id}/connectivity")

        assert resp.status_code == 200
        app.dependency_overrides.clear()

    def test_connectivity_tenant_admin(self, app, mock_db_session):
        """Tenant admin can also check connectivity."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        result = MagicMock(overall_status="healthy", stages=[])
        mock_svc = MagicMock()
        mock_svc.check_connectivity = AsyncMock(return_value=result)

        with _patch_require_role(_tenant_admin_dict()), patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app) as client:
                gw_id = uuid4()
                resp = client.get(f"/v1/admin/diagnostics/{gw_id}/connectivity")

        assert resp.status_code == 200
        app.dependency_overrides.clear()

    def test_connectivity_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        """Viewer is denied access to connectivity check."""
        with TestClient(app_with_no_tenant_user) as client:
            gw_id = uuid4()
            resp = client.get(f"/v1/admin/diagnostics/{gw_id}/connectivity")

        assert resp.status_code == 403


class TestDiagnosticHistory:
    """Tests for GET /v1/admin/diagnostics/{gateway_id}/history."""

    def test_history_success(self, app, mock_db_session):
        """CPI admin gets diagnostic history."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        history = MagicMock(items=[], total=0)
        mock_svc = MagicMock()
        mock_svc.get_history = AsyncMock(return_value=history)

        with _patch_require_role(_admin_user_dict()), patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app) as client:
                gw_id = uuid4()
                resp = client.get(f"/v1/admin/diagnostics/{gw_id}/history")

        assert resp.status_code == 200
        app.dependency_overrides.clear()

    def test_history_custom_limit(self, app, mock_db_session):
        """Custom limit parameter is forwarded."""
        from src.database import get_db

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_db] = override_get_db

        history = MagicMock(items=[], total=0)
        mock_svc = MagicMock()
        mock_svc.get_history = AsyncMock(return_value=history)

        with _patch_require_role(_admin_user_dict()), patch(SVC_PATH, return_value=mock_svc):
            with TestClient(app) as client:
                gw_id = uuid4()
                resp = client.get(f"/v1/admin/diagnostics/{gw_id}/history?limit=50")

        assert resp.status_code == 200
        call_kwargs = mock_svc.get_history.call_args
        assert call_kwargs.kwargs.get("limit") == 50
        app.dependency_overrides.clear()

    def test_history_403_viewer(self, app_with_no_tenant_user, mock_db_session):
        """Viewer is denied access to diagnostic history."""
        with TestClient(app_with_no_tenant_user) as client:
            gw_id = uuid4()
            resp = client.get(f"/v1/admin/diagnostics/{gw_id}/history")

        assert resp.status_code == 403
