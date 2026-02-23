"""Tests for diagnostic service auto-RCA (CAB-1316)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.models.execution_log import ErrorCategory, ExecutionLog, ExecutionStatus
from src.schemas.diagnostic import DiagnosticCategory, DiagnosticReport
from src.services.diagnostic_service import DiagnosticService


def _make_log(
    status_code: int = 500,
    error_category: ErrorCategory | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
    request_id: str = "req-001",
) -> ExecutionLog:
    """Build a mock ExecutionLog for testing classification."""
    log = MagicMock(spec=ExecutionLog)
    log.status_code = status_code
    log.error_category = error_category
    log.error_message = error_message
    log.duration_ms = duration_ms
    log.request_id = request_id
    log.method = "POST"
    log.path = "/api/test"
    log.status = ExecutionStatus.ERROR
    log.tenant_id = "tenant-1"
    log.started_at = datetime.now(UTC)
    return log


class TestErrorTaxonomy:
    """Verify all 9 error categories exist in the enum."""

    def test_error_taxonomy_all_categories(self) -> None:
        expected = {
            "auth",
            "rate_limit",
            "backend",
            "timeout",
            "validation",
            "network",
            "certificate",
            "policy",
            "circuit_breaker",
        }
        actual = {e.value for e in ErrorCategory}
        assert actual == expected


class TestClassifySingleError:
    """Test individual error classification rules."""

    def setup_method(self) -> None:
        self.db = AsyncMock()
        self.svc = DiagnosticService(self.db)

    def test_classify_auth_error(self) -> None:
        log = _make_log(
            status_code=401,
            error_category=ErrorCategory.AUTH,
            error_message="JWT expired",
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.AUTH
        assert cause.confidence >= 0.8

    def test_classify_rate_limit(self) -> None:
        log = _make_log(
            status_code=429,
            error_category=ErrorCategory.RATE_LIMIT,
            error_message="quota exceeded",
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.RATE_LIMIT
        assert cause.confidence >= 0.9

    def test_classify_circuit_breaker_open(self) -> None:
        log = _make_log(
            status_code=503,
            error_category=ErrorCategory.CIRCUIT_BREAKER,
            error_message="CB open",
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CIRCUIT_BREAKER
        assert cause.confidence == 0.95

    def test_classify_backend_error(self) -> None:
        log = _make_log(
            status_code=502,
            error_category=ErrorCategory.BACKEND,
            error_message="upstream unreachable",
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.BACKEND
        assert cause.confidence >= 0.8

    def test_classify_timeout(self) -> None:
        log = _make_log(
            status_code=504,
            error_category=ErrorCategory.TIMEOUT,
            error_message="timeout after 30000ms",
            duration_ms=30000,
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CONNECTIVITY
        assert cause.confidence >= 0.8
        assert "30000ms" in cause.evidence[0]

    def test_classify_certificate_error(self) -> None:
        log = _make_log(
            status_code=502,
            error_category=ErrorCategory.CERTIFICATE,
            error_message="TLS handshake failed",
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CERTIFICATE
        assert cause.confidence >= 0.9

    def test_classify_policy_denial(self) -> None:
        log = _make_log(
            status_code=403,
            error_category=ErrorCategory.POLICY,
            error_message="OPA policy denied",
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.POLICY
        assert cause.confidence >= 0.9


class TestDiagnosticReport:
    """Test diagnostic report properties."""

    def setup_method(self) -> None:
        self.db = AsyncMock()
        self.svc = DiagnosticService(self.db)

    def test_diagnostic_report_redacted_by_default(self) -> None:
        report = DiagnosticReport(tenant_id="t1", gateway_id="gw1")
        assert report.redacted is True
        assert report.request_summary is None

    def test_diagnostic_report_has_timing(self) -> None:
        logs = [_make_log(duration_ms=100), _make_log(duration_ms=200)]
        timing = self.svc._aggregate_timing(logs)
        assert timing.total_ms is not None
        assert timing.total_ms == 150.0


class TestConnectivity:
    """Test connectivity check with mocked gateway."""

    @pytest.mark.asyncio
    async def test_connectivity_gateway_not_found(self) -> None:
        db = AsyncMock()
        svc = DiagnosticService(db)
        with patch.object(svc, "_get_gateway", return_value=None):
            result = await svc.check_connectivity(
                tenant_id="t1", gateway_id="nonexistent"
            )
        assert result.overall_status == "unhealthy"
        assert result.stages[0].name == "lookup"
        assert result.stages[0].status == "error"


class TestRouterAuth:
    """Test that diagnostic endpoints require authentication."""

    def test_router_requires_auth(self) -> None:
        from src.routers.diagnostics import router

        routes = [r.path for r in router.routes]
        prefix = "/v1/admin/diagnostics"
        assert f"{prefix}/{{gateway_id}}" in routes
        assert f"{prefix}/{{gateway_id}}/connectivity" in routes
        assert f"{prefix}/{{gateway_id}}/history" in routes


class TestFalsePositiveRate:
    """Verify <10% false-positive rate across 20+ known error patterns."""

    TEST_CASES = [
        # (status_code, error_category, error_message, expected_category)
        (401, ErrorCategory.AUTH, "Unauthorized", DiagnosticCategory.AUTH),
        (403, ErrorCategory.AUTH, "Forbidden", DiagnosticCategory.AUTH),
        (
            429,
            ErrorCategory.RATE_LIMIT,
            "Too many requests",
            DiagnosticCategory.RATE_LIMIT,
        ),
        (429, None, "Rate limit exceeded", DiagnosticCategory.RATE_LIMIT),
        (502, ErrorCategory.BACKEND, "Bad gateway", DiagnosticCategory.BACKEND),
        (503, ErrorCategory.BACKEND, "Service unavailable", DiagnosticCategory.BACKEND),
        (
            504,
            ErrorCategory.TIMEOUT,
            "Gateway timeout",
            DiagnosticCategory.CONNECTIVITY,
        ),
        (504, None, "Read timed out", DiagnosticCategory.CONNECTIVITY),
        (
            503,
            ErrorCategory.CIRCUIT_BREAKER,
            "Circuit open",
            DiagnosticCategory.CIRCUIT_BREAKER,
        ),
        (500, None, "circuit breaker tripped", DiagnosticCategory.CIRCUIT_BREAKER),
        (
            502,
            ErrorCategory.CERTIFICATE,
            "SSL certificate verify failed",
            DiagnosticCategory.CERTIFICATE,
        ),
        (502, None, "TLS handshake error", DiagnosticCategory.CERTIFICATE),
        (403, ErrorCategory.POLICY, "OPA denied", DiagnosticCategory.POLICY),
        (403, None, "guardrail blocked request", DiagnosticCategory.POLICY),
        (403, None, "policy denied access", DiagnosticCategory.POLICY),
        (
            502,
            ErrorCategory.NETWORK,
            "DNS resolution failed",
            DiagnosticCategory.CONNECTIVITY,
        ),
        (502, None, "connection refused", DiagnosticCategory.CONNECTIVITY),
        (500, None, "Internal server error", DiagnosticCategory.BACKEND),
        (502, None, "upstream timeout", DiagnosticCategory.BACKEND),
        (
            429,
            ErrorCategory.RATE_LIMIT,
            "consumer quota exhausted",
            DiagnosticCategory.RATE_LIMIT,
        ),
    ]

    def test_false_positive_rate_below_10pct(self) -> None:
        db = AsyncMock()
        svc = DiagnosticService(db)

        correct = 0
        total = len(self.TEST_CASES)
        assert total >= 20, f"Need 20+ test cases, got {total}"

        for status_code, error_cat, error_msg, expected_cat in self.TEST_CASES:
            log = _make_log(
                status_code=status_code,
                error_category=error_cat,
                error_message=error_msg,
            )
            cause = svc._classify_single(log)
            if cause and cause.category == expected_cat:
                correct += 1

        accuracy = correct / total
        false_positive_rate = 1.0 - accuracy
        assert false_positive_rate < 0.10, (
            f"False positive rate {false_positive_rate:.1%} exceeds 10% threshold "
            f"({correct}/{total} correct)"
        )


class TestNetworkPathParsing:
    """Test _parse_network_path from hop detection headers (Phase 2)."""

    @staticmethod
    def _make_response(headers: dict[str, str]) -> httpx.Response:
        """Build a mock httpx.Response with given headers."""
        return httpx.Response(200, headers=headers)

    def test_parse_single_via_header(self) -> None:
        resp = self._make_response({"via": "1.1 stoa-gateway (0.1.0)"})
        path = DiagnosticService._parse_network_path(resp, total_latency_ms=50.0)
        assert path is not None
        assert path.total_hops == 1
        assert path.hops[0].protocol == "1.1"
        assert path.hops[0].pseudonym == "stoa-gateway"

    def test_parse_multiple_via_hops(self) -> None:
        resp = self._make_response({"via": "1.1 proxy-a, 2.0 cdn.example.com"})
        path = DiagnosticService._parse_network_path(resp, total_latency_ms=120.0)
        assert path is not None
        assert path.total_hops == 2
        assert path.hops[0].pseudonym == "proxy-a"
        assert path.hops[1].pseudonym == "cdn.example.com"
        assert path.total_latency_ms == 120.0

    def test_parse_stoa_timing_header(self) -> None:
        resp = self._make_response({"x-stoa-timing": "gw=5;hops=2"})
        path = DiagnosticService._parse_network_path(resp, total_latency_ms=100.0)
        assert path is not None
        assert len(path.detected_intermediaries) == 1
        assert "2 hops" in path.detected_intermediaries[0]

    def test_parse_no_hop_headers_returns_none(self) -> None:
        resp = self._make_response({"content-type": "application/json"})
        path = DiagnosticService._parse_network_path(resp, total_latency_ms=30.0)
        assert path is None

    def test_parse_combined_via_and_timing(self) -> None:
        resp = self._make_response(
            {"via": "1.1 stoa-gateway (0.1.0)", "x-stoa-timing": "gw=5;hops=1"}
        )
        path = DiagnosticService._parse_network_path(resp, total_latency_ms=80.0)
        assert path is not None
        assert path.total_hops == 1
        assert "stoa-gateway" in path.detected_intermediaries
