"""Tests for AI Session Trace Ingest & Stats — CAB-1666

Covers: POST /v1/traces/ingest, GET /v1/traces/stats/ai-sessions
"""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

SVC_PATH = "src.routers.traces.TraceService"
INGEST_KEY_PATH = "src.routers.traces.HEGEMON_INGEST_KEY"


def _make_trace(**overrides):
    """Create a mock trace object for ingest responses."""
    from datetime import UTC, datetime

    mock = MagicMock()
    defaults = {
        "id": "trace-001",
        "trigger_type": "ai-session",
        "trigger_source": "hegemon-backend",
        "tenant_id": "hegemon",
        "api_name": "CAB-1528",
        "environment": "production",
        "total_duration_ms": 1320000,
        "error_summary": None,
        "steps": [],
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(mock, k, v)

    mock.status = MagicMock()
    mock.status.value = overrides.get("status_value", "success")
    mock.created_at = datetime(2026, 3, 1, tzinfo=UTC)
    return mock


VALID_INGEST_BODY = {
    "trigger_type": "ai-session",
    "trigger_source": "hegemon-backend",
    "tenant_id": "hegemon",
    "api_name": "CAB-1528",
    "environment": "production",
    "git_branch": "feat/CAB-1528-something",
    "git_author": "hegemon-worker-1",
    "total_duration_ms": 1320000,
    "status": "success",
    "steps": [
        {"name": "claimed", "status": "success", "duration_ms": 0},
        {"name": "pr-created", "status": "success", "duration_ms": 900000, "details": {"pr": 1158}},
        {"name": "merged", "status": "success", "duration_ms": 120000},
    ],
    "metadata": {
        "total_tokens": 45000,
        "cost_usd": 2.24,
        "model": "claude-opus-4-6",
        "turns": 18,
    },
}


class TestIngestEndpoint:
    """Tests for POST /v1/traces/ingest."""

    def test_ingest_success(self, app_with_cpi_admin, mock_db_session):
        """Happy path: ingest a completed AI session."""
        trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=trace)
        mock_svc.add_step = AsyncMock(return_value=trace)
        mock_svc.complete = AsyncMock(return_value=trace)
        mock_svc.get = AsyncMock(return_value=trace)
        mock_svc.session.commit = AsyncMock()

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=VALID_INGEST_BODY,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ingested"] is True
        assert data["trace_id"] == "trace-001"
        # 1 session-summary step + 3 body steps = 4 add_step calls
        assert mock_svc.add_step.call_count == 4

    def test_ingest_failed_session(self, app_with_cpi_admin, mock_db_session):
        """Ingest a failed session — error_summary is set."""
        trace = _make_trace(status_value="failed")
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=trace)
        mock_svc.add_step = AsyncMock(return_value=trace)
        mock_svc.complete = AsyncMock(return_value=trace)
        mock_svc.get = AsyncMock(return_value=trace)
        mock_svc.session.commit = AsyncMock()

        body = {
            **VALID_INGEST_BODY,
            "status": "failed",
            "steps": [
                {"name": "claimed", "status": "success"},
                {"name": "pr-created", "status": "failed", "error": "CI failed"},
            ],
        }

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=body,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 200
        # Verify complete() was called with FAILED status
        complete_call = mock_svc.complete.call_args
        assert complete_call[0][1].value == "failed"
        assert "pr-created" in complete_call[0][2]  # error_summary mentions failed step

    def test_ingest_no_api_key(self, app_with_cpi_admin, mock_db_session):
        """Missing API key returns 422 (missing header)."""
        mock_svc = MagicMock()

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post("/v1/traces/ingest", json=VALID_INGEST_BODY)

        assert resp.status_code == 422

    def test_ingest_wrong_api_key(self, app_with_cpi_admin, mock_db_session):
        """Wrong API key returns 401."""
        mock_svc = MagicMock()

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=VALID_INGEST_BODY,
                headers={"X-STOA-API-KEY": "wrong-key"},
            )

        assert resp.status_code == 401

    def test_ingest_key_not_configured(self, app_with_cpi_admin, mock_db_session):
        """Returns 503 when HEGEMON_INGEST_KEY is not set."""
        mock_svc = MagicMock()

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, ""),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=VALID_INGEST_BODY,
                headers={"X-STOA-API-KEY": "any-key"},
            )

        assert resp.status_code == 503

    def test_ingest_invalid_trigger_type(self, app_with_cpi_admin, mock_db_session):
        """Only ai-session trigger_type is accepted."""
        mock_svc = MagicMock()
        body = {**VALID_INGEST_BODY, "trigger_type": "gitlab-push"}

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=body,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 422  # Pydantic validation error

    def test_ingest_no_metadata(self, app_with_cpi_admin, mock_db_session):
        """Ingest without metadata — no session-summary step created."""
        trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=trace)
        mock_svc.add_step = AsyncMock(return_value=trace)
        mock_svc.complete = AsyncMock(return_value=trace)
        mock_svc.get = AsyncMock(return_value=trace)
        mock_svc.session.commit = AsyncMock()

        body = {**VALID_INGEST_BODY, "metadata": None}

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=body,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 200
        # Only 3 body steps, no session-summary
        assert mock_svc.add_step.call_count == 3

    def test_ingest_no_steps(self, app_with_cpi_admin, mock_db_session):
        """Ingest with empty steps list — only metadata step."""
        trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=trace)
        mock_svc.add_step = AsyncMock(return_value=trace)
        mock_svc.complete = AsyncMock(return_value=trace)
        mock_svc.get = AsyncMock(return_value=trace)
        mock_svc.session.commit = AsyncMock()

        body = {**VALID_INGEST_BODY, "steps": []}

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=body,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 200
        # Only session-summary step
        assert mock_svc.add_step.call_count == 1

    def test_ingest_missing_required_field(self, app_with_cpi_admin, mock_db_session):
        """Missing trigger_source (required) returns 422."""
        mock_svc = MagicMock()
        body = {k: v for k, v in VALID_INGEST_BODY.items() if k != "trigger_source"}

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=body,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 422


class TestAISessionStats:
    """Tests for GET /v1/traces/stats/ai-sessions."""

    def test_stats_empty(self, app_with_cpi_admin, mock_db_session):
        """Stats with no AI sessions returns zero totals."""
        mock_svc = MagicMock()
        mock_svc.get_ai_session_stats = AsyncMock(
            return_value={
                "days": 7,
                "totals": {
                    "sessions": 0,
                    "total_duration_ms": 0,
                    "avg_duration_ms": 0,
                    "success_count": 0,
                    "success_rate": 0,
                },
                "workers": [],
                "daily": [],
            }
        )

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/traces/stats/ai-sessions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["sessions"] == 0
        assert data["workers"] == []
        assert data["daily"] == []

    def test_stats_with_data(self, app_with_cpi_admin, mock_db_session):
        """Stats with data returns totals, workers, and daily."""
        mock_svc = MagicMock()
        mock_svc.get_ai_session_stats = AsyncMock(
            return_value={
                "days": 7,
                "totals": {
                    "sessions": 15,
                    "total_duration_ms": 19800000,
                    "avg_duration_ms": 1320000,
                    "success_count": 12,
                    "success_rate": 80.0,
                },
                "workers": [
                    {
                        "worker": "hegemon-backend",
                        "sessions": 10,
                        "total_duration_ms": 13200000,
                        "avg_duration_ms": 1320000,
                        "success_count": 8,
                        "success_rate": 80.0,
                        "last_activity": "2026-03-01T12:00:00+00:00",
                    },
                ],
                "daily": [
                    {"date": "2026-03-01", "sessions": 5},
                    {"date": "2026-03-02", "sessions": 10},
                ],
            }
        )

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/traces/stats/ai-sessions")

        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["sessions"] == 15
        assert len(data["workers"]) == 1
        assert data["workers"][0]["worker"] == "hegemon-backend"
        assert len(data["daily"]) == 2

    def test_stats_with_worker_filter(self, app_with_cpi_admin, mock_db_session):
        """Stats with worker filter passes param to service."""
        mock_svc = MagicMock()
        mock_svc.get_ai_session_stats = AsyncMock(
            return_value={
                "days": 7,
                "totals": {
                    "sessions": 5,
                    "total_duration_ms": 0,
                    "avg_duration_ms": 0,
                    "success_count": 5,
                    "success_rate": 100.0,
                },
                "workers": [
                    {
                        "worker": "hegemon-mcp",
                        "sessions": 5,
                        "total_duration_ms": 0,
                        "avg_duration_ms": 0,
                        "success_count": 5,
                        "success_rate": 100.0,
                        "last_activity": None,
                    }
                ],
                "daily": [],
            }
        )

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/traces/stats/ai-sessions?worker=hegemon-mcp&days=14")

        assert resp.status_code == 200
        mock_svc.get_ai_session_stats.assert_called_once_with(14, "hegemon-mcp")

    def test_stats_default_params(self, app_with_cpi_admin, mock_db_session):
        """Default params: days=7, worker=None."""
        mock_svc = MagicMock()
        mock_svc.get_ai_session_stats = AsyncMock(
            return_value={
                "days": 7,
                "totals": {
                    "sessions": 0,
                    "total_duration_ms": 0,
                    "avg_duration_ms": 0,
                    "success_count": 0,
                    "success_rate": 0,
                },
                "workers": [],
                "daily": [],
            }
        )

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/traces/stats/ai-sessions")

        assert resp.status_code == 200
        mock_svc.get_ai_session_stats.assert_called_once_with(7, None)

    def test_stats_invalid_days(self, app_with_cpi_admin, mock_db_session):
        """days=0 returns 422 (ge=1)."""
        mock_svc = MagicMock()

        with patch(SVC_PATH, return_value=mock_svc), TestClient(app_with_cpi_admin) as client:
            resp = client.get("/v1/traces/stats/ai-sessions?days=0")

        assert resp.status_code == 422


class TestCostAlertDedup:
    """Tests for cost alert deduplication (CAB-1691)."""

    def test_ingest_sends_alert_and_records(self, app_with_cpi_admin, mock_db_session):
        """Alert is sent and recorded on first threshold breach."""
        trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=trace)
        mock_svc.add_step = AsyncMock(return_value=trace)
        mock_svc.complete = AsyncMock(return_value=trace)
        mock_svc.get = AsyncMock(return_value=trace)
        mock_svc.session.commit = AsyncMock()
        mock_svc.check_cost_alert = AsyncMock(
            return_value={"alert": True, "today_cost_usd": 55.0, "threshold_usd": 50.0, "sessions_today": 20}
        )
        mock_svc.send_cost_alert_slack = AsyncMock(return_value=True)
        mock_svc.record_cost_alert = AsyncMock()
        mock_svc.push_cost_metrics = AsyncMock(return_value=True)

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=VALID_INGEST_BODY,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 200
        mock_svc.send_cost_alert_slack.assert_called_once()
        mock_svc.record_cost_alert.assert_called_once()

    def test_ingest_no_alert_when_below_threshold(self, app_with_cpi_admin, mock_db_session):
        """No alert sent when cost is below threshold."""
        trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=trace)
        mock_svc.add_step = AsyncMock(return_value=trace)
        mock_svc.complete = AsyncMock(return_value=trace)
        mock_svc.get = AsyncMock(return_value=trace)
        mock_svc.session.commit = AsyncMock()
        mock_svc.check_cost_alert = AsyncMock(return_value=None)
        mock_svc.push_cost_metrics = AsyncMock(return_value=True)

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=VALID_INGEST_BODY,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 200
        mock_svc.send_cost_alert_slack.assert_not_called()
        mock_svc.record_cost_alert.assert_not_called()

    def test_ingest_no_record_when_slack_fails(self, app_with_cpi_admin, mock_db_session):
        """Alert is NOT recorded if Slack send fails (so it retries next ingest)."""
        trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=trace)
        mock_svc.add_step = AsyncMock(return_value=trace)
        mock_svc.complete = AsyncMock(return_value=trace)
        mock_svc.get = AsyncMock(return_value=trace)
        mock_svc.session.commit = AsyncMock()
        mock_svc.check_cost_alert = AsyncMock(
            return_value={"alert": True, "today_cost_usd": 55.0, "threshold_usd": 50.0, "sessions_today": 20}
        )
        mock_svc.send_cost_alert_slack = AsyncMock(return_value=False)
        mock_svc.record_cost_alert = AsyncMock()
        mock_svc.push_cost_metrics = AsyncMock(return_value=True)

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=VALID_INGEST_BODY,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 200
        mock_svc.send_cost_alert_slack.assert_called_once()
        mock_svc.record_cost_alert.assert_not_called()


class TestPushgatewayPerWorker:
    """Tests for per-worker Pushgateway metrics (CAB-1695)."""

    def test_ingest_triggers_pushgateway(self, app_with_cpi_admin, mock_db_session):
        """Ingest triggers push_cost_metrics."""
        trace = _make_trace()
        mock_svc = MagicMock()
        mock_svc.create = AsyncMock(return_value=trace)
        mock_svc.add_step = AsyncMock(return_value=trace)
        mock_svc.complete = AsyncMock(return_value=trace)
        mock_svc.get = AsyncMock(return_value=trace)
        mock_svc.session.commit = AsyncMock()
        mock_svc.check_cost_alert = AsyncMock(return_value=None)
        mock_svc.push_cost_metrics = AsyncMock(return_value=True)

        with (
            patch(SVC_PATH, return_value=mock_svc),
            patch(INGEST_KEY_PATH, "test-key"),
            TestClient(app_with_cpi_admin) as client,
        ):
            resp = client.post(
                "/v1/traces/ingest",
                json=VALID_INGEST_BODY,
                headers={"X-STOA-API-KEY": "test-key"},
            )

        assert resp.status_code == 200
        mock_svc.push_cost_metrics.assert_called_once()
