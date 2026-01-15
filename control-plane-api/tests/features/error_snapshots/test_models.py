"""Tests for error snapshot models.

CAB-397: Validates Pydantic model behavior.
"""

import pytest
from datetime import datetime, timezone

from src.features.error_snapshots.models import (
    ErrorSnapshot,
    RequestSnapshot,
    ResponseSnapshot,
    SnapshotTrigger,
    SnapshotSummary,
    SnapshotListResponse,
    RoutingInfo,
    PolicyResult,
    BackendState,
    LogEntry,
    EnvironmentInfo,
)


class TestErrorSnapshot:
    """Tests for ErrorSnapshot model."""

    def test_create_minimal_snapshot(self):
        """Minimal snapshot should be valid."""
        snapshot = ErrorSnapshot(
            tenant_id="tenant-acme",
            request=RequestSnapshot(method="GET", path="/api/test"),
            response=ResponseSnapshot(status=500, duration_ms=100),
        )

        assert snapshot.tenant_id == "tenant-acme"
        assert snapshot.request.method == "GET"
        assert snapshot.response.status == 500
        assert snapshot.id.startswith("SNP-")
        assert snapshot.trigger == SnapshotTrigger.ERROR_5XX

    def test_snapshot_id_format(self):
        """Snapshot ID should follow format SNP-YYYYMMDD-HHMMSS-xxxxxxxx."""
        snapshot = ErrorSnapshot(
            tenant_id="test",
            request=RequestSnapshot(method="GET", path="/"),
            response=ResponseSnapshot(status=500, duration_ms=100),
        )

        parts = snapshot.id.split("-")
        assert len(parts) == 4
        assert parts[0] == "SNP"
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 6  # HHMMSS
        assert len(parts[3]) == 8  # hex suffix

    def test_snapshot_with_all_fields(self):
        """Full snapshot with all fields should be valid."""
        snapshot = ErrorSnapshot(
            tenant_id="tenant-acme",
            trigger=SnapshotTrigger.TIMEOUT,
            request=RequestSnapshot(
                method="POST",
                path="/api/payments",
                headers={"Content-Type": "application/json"},
                body={"amount": 100},
                query_params={"currency": "USD"},
                client_ip="192.168.1.100",
                user_agent="Mozilla/5.0",
            ),
            response=ResponseSnapshot(
                status=504,
                headers={"X-Request-ID": "abc123"},
                body={"error": "timeout"},
                duration_ms=30000,
            ),
            routing=RoutingInfo(
                api_name="payments-api",
                api_version="v1",
                route="/payments",
                backend_url="https://backend.example.com",
            ),
            policies_applied=[
                PolicyResult(name="rate-limit", result="pass", duration_ms=1),
                PolicyResult(name="auth", result="pass", duration_ms=5),
            ],
            backend_state=BackendState(
                health="degraded",
                error_rate_1m=0.15,
                p99_latency_ms=2500,
            ),
            logs=[
                LogEntry(
                    timestamp=datetime.now(timezone.utc),
                    level="ERROR",
                    message="Connection timeout",
                    extra={"backend": "payments-service"},
                )
            ],
            trace_id="trace-123",
            span_id="span-456",
            environment=EnvironmentInfo(
                pod="api-pod-abc",
                node="node-1",
                namespace="stoa-system",
                memory_percent=75.5,
                cpu_percent=45.2,
            ),
            masked_fields=["request.headers.Authorization"],
        )

        assert snapshot.trigger == SnapshotTrigger.TIMEOUT
        assert snapshot.routing.api_name == "payments-api"
        assert len(snapshot.policies_applied) == 2
        assert snapshot.backend_state.health == "degraded"
        assert len(snapshot.logs) == 1
        assert snapshot.environment.pod == "api-pod-abc"

    def test_snapshot_json_serialization(self):
        """Snapshot should serialize to JSON correctly."""
        snapshot = ErrorSnapshot(
            tenant_id="test",
            request=RequestSnapshot(method="GET", path="/"),
            response=ResponseSnapshot(status=500, duration_ms=100),
        )

        json_str = snapshot.model_dump_json()
        restored = ErrorSnapshot.model_validate_json(json_str)

        assert restored.id == snapshot.id
        assert restored.tenant_id == snapshot.tenant_id


class TestSnapshotTrigger:
    """Tests for SnapshotTrigger enum."""

    def test_trigger_values(self):
        """All trigger values should be defined."""
        assert SnapshotTrigger.ERROR_4XX.value == "4xx"
        assert SnapshotTrigger.ERROR_5XX.value == "5xx"
        assert SnapshotTrigger.TIMEOUT.value == "timeout"
        assert SnapshotTrigger.MANUAL.value == "manual"


class TestSnapshotSummary:
    """Tests for SnapshotSummary model."""

    def test_summary_from_snapshot(self):
        """Summary should contain essential fields."""
        summary = SnapshotSummary(
            id="SNP-20260115-100000-abc12345",
            timestamp=datetime.now(timezone.utc),
            tenant_id="tenant-acme",
            trigger=SnapshotTrigger.ERROR_5XX,
            status=500,
            method="POST",
            path="/api/orders",
            duration_ms=1500,
        )

        assert summary.status == 500
        assert summary.method == "POST"
        assert summary.path == "/api/orders"


class TestSnapshotListResponse:
    """Tests for SnapshotListResponse model."""

    def test_list_response_pagination(self):
        """List response should contain pagination info."""
        response = SnapshotListResponse(
            items=[
                SnapshotSummary(
                    id="SNP-20260115-100000-abc12345",
                    timestamp=datetime.now(timezone.utc),
                    tenant_id="test",
                    trigger=SnapshotTrigger.ERROR_5XX,
                    status=500,
                    method="GET",
                    path="/",
                    duration_ms=100,
                )
            ],
            total=50,
            page=2,
            page_size=20,
        )

        assert len(response.items) == 1
        assert response.total == 50
        assert response.page == 2
        assert response.page_size == 20


class TestRequestSnapshot:
    """Tests for RequestSnapshot model."""

    def test_request_with_defaults(self):
        """Request with only required fields should work."""
        request = RequestSnapshot(method="GET", path="/api/test")

        assert request.method == "GET"
        assert request.path == "/api/test"
        assert request.headers == {}
        assert request.body is None
        assert request.query_params == {}


class TestResponseSnapshot:
    """Tests for ResponseSnapshot model."""

    def test_response_with_defaults(self):
        """Response with only required fields should work."""
        response = ResponseSnapshot(status=200, duration_ms=50)

        assert response.status == 200
        assert response.duration_ms == 50
        assert response.headers == {}
        assert response.body is None


class TestPolicyResult:
    """Tests for PolicyResult model."""

    def test_policy_result_pass(self):
        """Passing policy result should be valid."""
        result = PolicyResult(name="rate-limit", result="pass", duration_ms=2)

        assert result.name == "rate-limit"
        assert result.result == "pass"
        assert result.error is None

    def test_policy_result_fail(self):
        """Failing policy result should include error."""
        result = PolicyResult(
            name="auth",
            result="fail",
            duration_ms=5,
            error="Invalid token",
        )

        assert result.result == "fail"
        assert result.error == "Invalid token"
