"""Regression test for CAB-2138 — py/stack-trace-exposure on GET /v1/mcp/gitops/status.

CodeQL alert #144 flagged ``errors=status.get("errors", [])`` in
``control-plane-api/src/routers/mcp_gitops.py``: upstream services can store raw
tracebacks in ``MCPServer.sync_error`` which then flow unredacted into the HTTP
response body.

The fix adds ``_scrub_sync_error`` which keeps only the first non-empty line and
caps the length at 200 chars — this test pins that behaviour.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.routers.mcp_gitops import _SYNC_ERROR_MAX_LEN, _scrub_sync_error
from src.services.git_provider import get_git_provider


@pytest.fixture()
def mock_git_provider():
    mock = MagicMock()
    mock._project = MagicMock()
    mock.is_connected = MagicMock(return_value=True)
    mock.connect = AsyncMock()
    return mock


@pytest.fixture()
def app_with_git_provider(app_with_cpi_admin, mock_git_provider):
    app_with_cpi_admin.dependency_overrides[get_git_provider] = lambda: mock_git_provider
    yield app_with_cpi_admin


class TestScrubSyncErrorUnit:
    """Unit tests for the _scrub_sync_error helper."""

    def test_empty_returns_empty(self):
        assert _scrub_sync_error("") == ""
        assert _scrub_sync_error(None) == ""

    def test_single_line_passes_through(self):
        assert _scrub_sync_error("Connection refused") == "Connection refused"

    def test_multiline_keeps_only_first_non_blank_line(self):
        traceback = (
            "\n"
            "Traceback (most recent call last):\n"
            '  File "/app/sync.py", line 42, in do_sync\n'
            "    raise RuntimeError('db pool exhausted')\n"
            "RuntimeError: db pool exhausted\n"
        )
        scrubbed = _scrub_sync_error(traceback)
        assert scrubbed == "Traceback (most recent call last):"
        assert "File " not in scrubbed
        assert "line 42" not in scrubbed

    def test_length_capped(self):
        long_err = "x" * 5000
        scrubbed = _scrub_sync_error(long_err)
        assert len(scrubbed) == _SYNC_ERROR_MAX_LEN


class TestSyncStatusResponseScrubs:
    """End-to-end: GET /v1/mcp/gitops/status must not echo tracebacks."""

    def test_status_response_does_not_leak_traceback(self, app_with_git_provider, mock_db_session, mock_git_provider):
        # regression for CAB-2138 — sync_error fields may contain full tracebacks
        raw_traceback = (
            "Traceback (most recent call last):\n"
            '  File "/app/services/mcp_sync_service.py", line 210, in _pull_server\n'
            "    server = await self.git.fetch(name)\n"
            "GitlabGetError: 404: {message: 'not found'}"
        )
        mock_status = {
            "total_servers": 2,
            "synced": 1,
            "pending": 0,
            "error": 1,
            "orphan": 0,
            "untracked": 0,
            "last_sync_at": "2026-04-20T08:00:00",
            "errors": [{"server": "tenant/widgets", "error": raw_traceback}],
        }

        with patch("src.routers.mcp_gitops.MCPSyncService") as MockSyncSvc:
            MockSyncSvc.return_value.get_sync_status = AsyncMock(return_value=mock_status)
            with TestClient(app_with_git_provider) as client:
                response = client.get("/v1/mcp/gitops/status")

        assert response.status_code == 200
        payload = response.json()
        assert payload["error"] == 1
        assert len(payload["errors"]) == 1

        returned_error = payload["errors"][0]["error"]
        assert returned_error == "Traceback (most recent call last):"
        # Ensure no stack frame details leak
        assert "File " not in returned_error
        assert "line 210" not in returned_error
        assert "mcp_sync_service.py" not in returned_error
