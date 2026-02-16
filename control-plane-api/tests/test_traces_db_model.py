"""Tests for PipelineTraceDB model methods (CAB-1291)"""
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from src.models.traces_db import PipelineTraceDB, TraceStatusDB


class TestTraceStatusDB:
    def test_values(self):
        assert TraceStatusDB.PENDING == "pending"
        assert TraceStatusDB.IN_PROGRESS == "in_progress"
        assert TraceStatusDB.SUCCESS == "success"
        assert TraceStatusDB.FAILED == "failed"
        assert TraceStatusDB.SKIPPED == "skipped"


def _make_trace(**overrides):
    """Create a PipelineTraceDB-like mock with all fields."""
    defaults = {
        "id": "trace-123",
        "trigger_type": "gitlab-push",
        "trigger_source": "gitlab",
        "git_commit_sha": "abc1234def5678",
        "git_commit_message": "feat: add endpoint",
        "git_branch": "main",
        "git_author": "alice",
        "git_author_email": "alice@example.com",
        "git_project": "stoa/api-definitions",
        "git_files_changed": ["apis/weather/openapi.yaml"],
        "tenant_id": "tenant-acme",
        "api_id": "api-1",
        "api_name": "Weather API",
        "environment": "dev",
        "created_at": datetime(2026, 2, 15, 10, 0, 0, tzinfo=UTC),
        "completed_at": datetime(2026, 2, 15, 10, 0, 5, tzinfo=UTC),
        "total_duration_ms": 5000,
        "status": TraceStatusDB.SUCCESS,
        "error_summary": None,
        "steps": [
            {"name": "webhook_received", "status": "success", "duration_ms": 15},
            {"name": "gateway_sync", "status": "failed", "duration_ms": 200, "error": "timeout"},
        ],
    }
    defaults.update(overrides)
    trace = MagicMock(spec=PipelineTraceDB)
    for k, v in defaults.items():
        setattr(trace, k, v)
    # Bind the real methods
    trace.to_summary = lambda: PipelineTraceDB.to_summary(trace)
    trace.to_dict = lambda: PipelineTraceDB.to_dict(trace)
    return trace


class TestToSummary:
    def test_standard(self):
        trace = _make_trace()
        summary = trace.to_summary()
        assert summary["id"] == "trace-123"
        assert summary["trigger_type"] == "gitlab-push"
        assert summary["status"] == "success"
        assert summary["steps_count"] == 2
        assert summary["steps_completed"] == 1
        assert summary["steps_failed"] == 1
        assert summary["git_commit_sha"] == "abc1234d"  # truncated to 8

    def test_no_commit_sha(self):
        trace = _make_trace(git_commit_sha=None)
        summary = trace.to_summary()
        assert summary["git_commit_sha"] is None

    def test_no_created_at(self):
        trace = _make_trace(created_at=None)
        summary = trace.to_summary()
        assert summary["created_at"] is None

    def test_empty_steps(self):
        trace = _make_trace(steps=[])
        summary = trace.to_summary()
        assert summary["steps_count"] == 0
        assert summary["steps_completed"] == 0
        assert summary["steps_failed"] == 0


class TestToDict:
    def test_standard(self):
        trace = _make_trace()
        d = trace.to_dict()
        assert d["id"] == "trace-123"
        assert d["trigger_type"] == "gitlab-push"
        assert d["git_branch"] == "main"
        assert d["status"] == "success"
        assert d["steps"] == trace.steps
        assert d["error_summary"] is None
        assert "created_at" in d
        assert "completed_at" in d

    def test_with_error(self):
        trace = _make_trace(
            status=TraceStatusDB.FAILED,
            error_summary="Pipeline failed at gateway_sync",
        )
        d = trace.to_dict()
        assert d["status"] == "failed"
        assert d["error_summary"] == "Pipeline failed at gateway_sync"

    def test_no_timestamps(self):
        trace = _make_trace(created_at=None, completed_at=None)
        d = trace.to_dict()
        assert d["created_at"] is None
        assert d["completed_at"] is None
