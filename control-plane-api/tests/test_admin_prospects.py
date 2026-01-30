"""
Tests for Admin Prospects Router - CAB-911

Tests the admin prospects dashboard endpoints:
- List prospects with filters
- Get prospect detail with timeline
- Get aggregated metrics
- Export to CSV
- RBAC authorization (cpi-admin only)
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestAdminProspectsRouter:
    """Test suite for Admin Prospects Dashboard endpoints."""

    # ============== Helper Methods ==============

    def _create_mock_invite(
        self,
        status: str = "converted",
        company: str = "Nexora Energy",
        email: str = "pierre@nexora-energy.com",
    ) -> MagicMock:
        """Create a mock Invite object."""
        mock = MagicMock()
        mock.id = uuid4()
        mock.email = email
        mock.company = company
        mock.token = "test_token_" + str(uuid4())[:8]
        mock.source = "demo"
        mock.status = status
        mock.created_at = datetime.now(timezone.utc) - timedelta(days=1)
        mock.expires_at = datetime.now(timezone.utc) + timedelta(days=6)
        mock.opened_at = (
            datetime.now(timezone.utc) - timedelta(hours=23)
            if status in ("opened", "converted")
            else None
        )
        return mock

    def _create_mock_event(
        self,
        invite_id,
        event_type: str = "tool_called",
        metadata: dict = None,
    ) -> MagicMock:
        """Create a mock ProspectEvent object."""
        mock = MagicMock()
        mock.id = uuid4()
        mock.invite_id = invite_id
        mock.event_type = event_type
        mock.event_data = metadata or {}
        mock.timestamp = datetime.now(timezone.utc) - timedelta(hours=1)
        return mock

    def _create_mock_feedback(
        self,
        invite_id,
        nps_score: int = 9,
        comment: str = "Great demo!",
    ) -> MagicMock:
        """Create a mock ProspectFeedback object."""
        mock = MagicMock()
        mock.id = uuid4()
        mock.invite_id = invite_id
        mock.nps_score = nps_score
        mock.comment = comment
        mock.created_at = datetime.now(timezone.utc)
        return mock

    # ============== Authorization Tests ==============

    def test_list_prospects_requires_cpi_admin(
        self, app_with_tenant_admin, mock_db_session
    ):
        """Tenant-admin should be denied access (403)."""
        with TestClient(app_with_tenant_admin) as client:
            response = client.get("/v1/admin/prospects")
            assert response.status_code == 403
            assert "Platform admin" in response.json()["detail"]

    def test_list_prospects_denies_viewer(
        self, app, mock_user_viewer, mock_db_session
    ):
        """Viewer should be denied access (403)."""
        from src.auth.dependencies import get_current_user
        from src.database import get_db

        async def override_get_current_user():
            return mock_user_viewer

        async def override_get_db():
            yield mock_db_session

        app.dependency_overrides[get_current_user] = override_get_current_user
        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            response = client.get("/v1/admin/prospects")
            assert response.status_code == 403

        app.dependency_overrides.clear()

    def test_list_prospects_allows_cpi_admin(
        self, app_with_cpi_admin, mock_db_session
    ):
        """CPI-admin should have access (200)."""
        # Mock the service layer to return empty list
        with patch(
            "src.routers.admin_prospects.prospects_service.list_prospects"
        ) as mock_list:
            mock_list.return_value = MagicMock(
                data=[],
                meta=MagicMock(total=0, page=1, limit=25),
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/prospects")
                assert response.status_code == 200
                data = response.json()
                assert "data" in data
                assert "meta" in data

    # ============== List Prospects Tests ==============

    def test_list_prospects_with_filters(
        self, app_with_cpi_admin, mock_db_session
    ):
        """Test listing prospects with company and status filters."""
        with patch(
            "src.routers.admin_prospects.prospects_service.list_prospects"
        ) as mock_list:
            mock_invite = self._create_mock_invite()
            mock_list.return_value = MagicMock(
                data=[
                    MagicMock(
                        id=mock_invite.id,
                        email=mock_invite.email,
                        company=mock_invite.company,
                        status="converted",
                        source="demo",
                        created_at=mock_invite.created_at,
                        opened_at=mock_invite.opened_at,
                        last_activity_at=datetime.now(timezone.utc),
                        time_to_first_tool_seconds=45.0,
                        nps_score=9,
                        nps_category="promoter",
                        total_events=5,
                    )
                ],
                meta=MagicMock(total=1, page=1, limit=25),
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    "/v1/admin/prospects",
                    params={"company": "Nexora Energy", "status": "converted"},
                )
                assert response.status_code == 200
                data = response.json()
                assert len(data["data"]) == 1
                assert data["meta"]["total"] == 1

                # Verify filter was passed to service
                mock_list.assert_called_once()
                call_kwargs = mock_list.call_args.kwargs
                assert call_kwargs["company"] == "Nexora Energy"
                assert call_kwargs["status"] == "converted"

    def test_list_prospects_pagination(
        self, app_with_cpi_admin, mock_db_session
    ):
        """Test pagination parameters are passed correctly."""
        with patch(
            "src.routers.admin_prospects.prospects_service.list_prospects"
        ) as mock_list:
            mock_list.return_value = MagicMock(
                data=[],
                meta=MagicMock(total=50, page=2, limit=10),
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    "/v1/admin/prospects",
                    params={"page": 2, "limit": 10},
                )
                assert response.status_code == 200

                mock_list.assert_called_once()
                call_kwargs = mock_list.call_args.kwargs
                assert call_kwargs["page"] == 2
                assert call_kwargs["limit"] == 10

    # ============== Prospect Detail Tests ==============

    def test_get_prospect_detail_success(
        self, app_with_cpi_admin, mock_db_session
    ):
        """Test getting detailed prospect info with timeline."""
        invite_id = uuid4()

        with patch(
            "src.routers.admin_prospects.prospects_service.get_prospect_detail"
        ) as mock_detail:
            mock_detail.return_value = MagicMock(
                id=invite_id,
                email="pierre@nexora-energy.com",
                company="Nexora Energy",
                status="converted",
                source="demo",
                created_at=datetime.now(timezone.utc),
                opened_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                nps_score=9,
                nps_category="promoter",
                nps_comment="Le MCP Gateway m'a bluffé",
                metrics=MagicMock(
                    time_to_open_seconds=900.0,
                    time_to_first_tool_seconds=45.0,
                    tools_called_count=5,
                    pages_viewed_count=3,
                    errors_count=1,
                    session_duration_seconds=3600.0,
                ),
                timeline=[
                    MagicMock(
                        id=uuid4(),
                        event_type="tool_called",
                        timestamp=datetime.now(timezone.utc),
                        metadata={"tool": "stoa_list_tools"},
                        is_first_tool_call=True,
                    )
                ],
                errors=[
                    MagicMock(
                        id=uuid4(),
                        event_type="error_encountered",
                        timestamp=datetime.now(timezone.utc),
                        metadata={"error": "403 Forbidden"},
                        is_first_tool_call=False,
                    )
                ],
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/admin/prospects/{invite_id}")
                assert response.status_code == 200
                data = response.json()
                assert data["email"] == "pierre@engie.fr"
                assert data["nps_score"] == 9
                assert "metrics" in data
                assert "timeline" in data
                assert len(data["timeline"]) <= 50  # Timeline limit

    def test_get_prospect_detail_not_found(
        self, app_with_cpi_admin, mock_db_session
    ):
        """Test 404 when prospect not found."""
        with patch(
            "src.routers.admin_prospects.prospects_service.get_prospect_detail"
        ) as mock_detail:
            mock_detail.return_value = None

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(f"/v1/admin/prospects/{uuid4()}")
                assert response.status_code == 404
                assert "not found" in response.json()["detail"].lower()

    # ============== Metrics Tests ==============

    def test_get_metrics_success(self, app_with_cpi_admin, mock_db_session):
        """Test getting aggregated KPIs."""
        with patch(
            "src.routers.admin_prospects.prospects_service.get_metrics"
        ) as mock_metrics:
            mock_metrics.return_value = MagicMock(
                total_invited=12,
                total_active=8,
                avg_time_to_tool=52.0,
                avg_nps=8.4,
                by_status=MagicMock(
                    total_invites=12,
                    pending=2,
                    opened=2,
                    converted=6,
                    expired=2,
                ),
                nps=MagicMock(
                    promoters=5,
                    passives=2,
                    detractors=1,
                    no_response=4,
                    nps_score=50.0,
                    avg_score=8.4,
                ),
                timing=MagicMock(
                    avg_time_to_open_seconds=3600.0,
                    avg_time_to_first_tool_seconds=52.0,
                ),
                top_companies=[
                    MagicMock(company="Nexora Energy", invite_count=4, converted_count=3),
                    MagicMock(company="Maison Aurèle", invite_count=3, converted_count=2),
                ],
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/prospects/metrics")
                assert response.status_code == 200
                data = response.json()
                assert data["total_invited"] == 12
                assert data["total_active"] == 8
                assert "by_status" in data
                assert "nps" in data

    # ============== Export Tests ==============

    def test_export_csv_success(self, app_with_cpi_admin, mock_db_session):
        """Test CSV export returns proper file."""
        with patch(
            "src.routers.admin_prospects.prospects_service.export_prospects_csv"
        ) as mock_export:
            mock_export.return_value = "ID,Email,Company\n1,test@test.com,Nexora Energy"

            with TestClient(app_with_cpi_admin) as client:
                response = client.get("/v1/admin/prospects/export")
                assert response.status_code == 200
                assert "text/csv" in response.headers["content-type"]
                assert "attachment" in response.headers["content-disposition"]
                assert "prospects_" in response.headers["content-disposition"]
                assert ".csv" in response.headers["content-disposition"]

    def test_export_csv_with_filters(self, app_with_cpi_admin, mock_db_session):
        """Test CSV export passes filters to service."""
        with patch(
            "src.routers.admin_prospects.prospects_service.export_prospects_csv"
        ) as mock_export:
            mock_export.return_value = "ID,Email,Company\n"

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    "/v1/admin/prospects/export",
                    params={"company": "Nexora Energy", "status": "converted"},
                )
                assert response.status_code == 200

                mock_export.assert_called_once()
                call_kwargs = mock_export.call_args.kwargs
                assert call_kwargs["company"] == "Nexora Energy"
                assert call_kwargs["status"] == "converted"

    # ============== Date Filter Tests ==============

    def test_list_prospects_with_date_range(
        self, app_with_cpi_admin, mock_db_session
    ):
        """Test filtering by date range."""
        with patch(
            "src.routers.admin_prospects.prospects_service.list_prospects"
        ) as mock_list:
            mock_list.return_value = MagicMock(
                data=[],
                meta=MagicMock(total=0, page=1, limit=25),
            )

            with TestClient(app_with_cpi_admin) as client:
                response = client.get(
                    "/v1/admin/prospects",
                    params={
                        "date_from": "2026-01-01T00:00:00Z",
                        "date_to": "2026-01-31T23:59:59Z",
                    },
                )
                assert response.status_code == 200

                mock_list.assert_called_once()
                call_kwargs = mock_list.call_args.kwargs
                assert call_kwargs["date_from"] is not None
                assert call_kwargs["date_to"] is not None
