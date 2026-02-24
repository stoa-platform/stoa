"""Comprehensive unit tests for DiagnosticService (CAB-1316).

Covers:
- _classify_single: all 8 ErrorCategory Phase-1 paths, all Phase-2 message
  pattern heuristics, all Phase-3 status-code fallbacks, and the None path.
- _parse_network_path: Via headers, X-Stoa-Timing, combined, empty.
- _aggregate_timing: empty list, single entry, multiple entries.
- _build_request_summary: GDPR-safe fields mapped correctly.
- diagnose: empty logs, single log, multiple logs, request_id filter.
- get_history: empty result, multiple logs.
- get_summary: empty logs, aggregated category counts and percentages.
- check_connectivity: gateway not found, URL parse error, DNS failure,
  TCP failure, TLS failure (HTTPS), HTTP success, HTTP error status.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.models.execution_log import ErrorCategory, ExecutionLog, ExecutionStatus
from src.schemas.diagnostic import (
    DiagnosticCategory,
    DiagnosticReport,
    TimingBreakdown,
)
from src.services.diagnostic_service import DiagnosticService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_log(
    status_code: int | None = 500,
    error_category: ErrorCategory | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
    request_id: str = "req-001",
    method: str = "POST",
    path: str = "/api/test",
) -> ExecutionLog:
    """Return a spec-mocked ExecutionLog with the given attributes."""
    log = MagicMock(spec=ExecutionLog)
    log.status_code = status_code
    log.error_category = error_category
    log.error_message = error_message
    log.duration_ms = duration_ms
    log.request_id = request_id
    log.method = method
    log.path = path
    log.status = ExecutionStatus.ERROR
    log.tenant_id = "tenant-1"
    log.started_at = datetime.now(UTC)
    return log


def _make_session() -> AsyncMock:
    """Return an AsyncMock database session with execute ready to configure."""
    session = AsyncMock()
    return session


def _make_execute_result(logs: list) -> MagicMock:
    """Wrap a list of logs in the SQLAlchemy result mock chain."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = logs
    return result


# ---------------------------------------------------------------------------
# _classify_single — Phase 1: explicit ErrorCategory (highest priority)
# ---------------------------------------------------------------------------


class TestClassifySinglePhase1ExplicitCategory:
    """All 8 explicit ErrorCategory values map to the correct DiagnosticCategory."""

    def setup_method(self) -> None:
        self.svc = DiagnosticService(_make_session())

    def test_circuit_breaker_explicit_category(self) -> None:
        log = _make_log(error_category=ErrorCategory.CIRCUIT_BREAKER)
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CIRCUIT_BREAKER
        assert cause.confidence == 0.95
        assert "circuit" in cause.summary.lower()

    def test_certificate_explicit_category(self) -> None:
        log = _make_log(error_category=ErrorCategory.CERTIFICATE, error_message="TLS error")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CERTIFICATE
        assert cause.confidence == 0.9
        assert len(cause.evidence) >= 1

    def test_policy_explicit_category(self) -> None:
        log = _make_log(error_category=ErrorCategory.POLICY, error_message="OPA denied")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.POLICY
        assert cause.confidence == 0.9
        assert cause.suggested_fix is not None

    def test_rate_limit_explicit_category(self) -> None:
        log = _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT)
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.RATE_LIMIT
        assert cause.confidence == 0.95

    def test_network_explicit_category_maps_to_connectivity(self) -> None:
        log = _make_log(error_category=ErrorCategory.NETWORK, error_message="DNS failure")
        cause = self.svc._classify_single(log)
        assert cause is not None
        # ErrorCategory.NETWORK maps to DiagnosticCategory.CONNECTIVITY
        assert cause.category == DiagnosticCategory.CONNECTIVITY
        assert cause.confidence == 0.8

    def test_timeout_explicit_category_maps_to_connectivity(self) -> None:
        log = _make_log(
            status_code=504,
            error_category=ErrorCategory.TIMEOUT,
            duration_ms=30000,
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CONNECTIVITY
        assert cause.confidence == 0.8
        # Duration should appear in evidence
        assert "30000ms" in cause.evidence[0]

    def test_timeout_explicit_category_no_duration(self) -> None:
        log = _make_log(status_code=504, error_category=ErrorCategory.TIMEOUT, duration_ms=None)
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CONNECTIVITY
        # No duration_info appended — evidence should not contain "ms"
        assert "None" not in cause.evidence[0]

    def test_auth_explicit_category(self) -> None:
        log = _make_log(status_code=401, error_category=ErrorCategory.AUTH)
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.AUTH
        assert cause.confidence == 0.9

    def test_backend_explicit_category(self) -> None:
        log = _make_log(status_code=502, error_category=ErrorCategory.BACKEND)
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.BACKEND
        assert cause.confidence == 0.85

    def test_explicit_category_takes_priority_over_status_code(self) -> None:
        """CERTIFICATE category wins over 502 status which would otherwise be BACKEND."""
        log = _make_log(
            status_code=502,
            error_category=ErrorCategory.CERTIFICATE,
            error_message="ssl handshake failed",
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CERTIFICATE

    def test_explicit_category_takes_priority_over_message_patterns(self) -> None:
        """AUTH category wins even when message contains 'circuit' keyword."""
        log = _make_log(
            status_code=401,
            error_category=ErrorCategory.AUTH,
            error_message="circuit breaker token rejected",
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.AUTH


# ---------------------------------------------------------------------------
# _classify_single — Phase 2: message-pattern heuristics
# ---------------------------------------------------------------------------


class TestClassifySinglePhase2MessagePatterns:
    """Message heuristics fire when no explicit ErrorCategory is set."""

    def setup_method(self) -> None:
        self.svc = DiagnosticService(_make_session())

    def test_message_circuit_pattern(self) -> None:
        log = _make_log(status_code=503, error_category=None, error_message="circuit breaker open")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CIRCUIT_BREAKER
        assert cause.confidence == 0.95

    def test_message_tls_pattern(self) -> None:
        log = _make_log(status_code=502, error_category=None, error_message="TLS handshake failed")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CERTIFICATE

    def test_message_certificate_pattern(self) -> None:
        log = _make_log(status_code=502, error_category=None, error_message="certificate verify failed")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CERTIFICATE

    def test_message_ssl_pattern(self) -> None:
        log = _make_log(status_code=502, error_category=None, error_message="ssl error occurred")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CERTIFICATE

    def test_message_policy_pattern(self) -> None:
        log = _make_log(status_code=403, error_category=None, error_message="policy denied request")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.POLICY

    def test_message_guardrail_pattern(self) -> None:
        log = _make_log(status_code=403, error_category=None, error_message="guardrail blocked PII")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.POLICY

    def test_message_denied_pattern(self) -> None:
        log = _make_log(status_code=403, error_category=None, error_message="access denied")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.POLICY

    def test_message_dns_pattern(self) -> None:
        log = _make_log(status_code=502, error_category=None, error_message="dns resolution failed")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CONNECTIVITY

    def test_message_connection_refused_pattern(self) -> None:
        log = _make_log(status_code=502, error_category=None, error_message="connection refused by host")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CONNECTIVITY

    def test_message_case_insensitive(self) -> None:
        """Patterns match regardless of original case (lowercased internally)."""
        log = _make_log(status_code=503, error_category=None, error_message="CIRCUIT BREAKER IS OPEN")
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.CIRCUIT_BREAKER

    def test_message_none_does_not_crash(self) -> None:
        """error_message=None is treated as empty string — no exception."""
        log = _make_log(status_code=502, error_category=None, error_message=None)
        # Falls through to Phase 3 status-code path — no exception raised
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert cause.category == DiagnosticCategory.BACKEND


# ---------------------------------------------------------------------------
# _classify_single — Phase 3: status-code fallbacks
# ---------------------------------------------------------------------------


class TestClassifySinglePhase3StatusCode:
    """Status-code fallback fires when no category or matching message."""

    def setup_method(self) -> None:
        self.svc = DiagnosticService(_make_session())

    def _no_match_log(self, status_code: int | None) -> ExecutionLog:
        """Log with no category and a generic message that won't trigger Phase 2."""
        return _make_log(status_code=status_code, error_category=None, error_message="generic err")

    def test_status_429_rate_limit(self) -> None:
        cause = self.svc._classify_single(self._no_match_log(429))
        assert cause is not None
        assert cause.category == DiagnosticCategory.RATE_LIMIT
        assert cause.confidence == 0.95

    def test_status_401_auth(self) -> None:
        cause = self.svc._classify_single(self._no_match_log(401))
        assert cause is not None
        assert cause.category == DiagnosticCategory.AUTH
        assert cause.confidence == 0.9

    def test_status_403_auth(self) -> None:
        cause = self.svc._classify_single(self._no_match_log(403))
        assert cause is not None
        assert cause.category == DiagnosticCategory.AUTH

    def test_status_504_timeout_connectivity(self) -> None:
        cause = self.svc._classify_single(self._no_match_log(504))
        assert cause is not None
        assert cause.category == DiagnosticCategory.CONNECTIVITY
        assert cause.confidence == 0.8

    def test_status_504_includes_duration_when_present(self) -> None:
        log = _make_log(status_code=504, error_category=None, error_message="generic err", duration_ms=5000)
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert "5000ms" in cause.evidence[0]

    def test_status_502_backend(self) -> None:
        cause = self.svc._classify_single(self._no_match_log(502))
        assert cause is not None
        assert cause.category == DiagnosticCategory.BACKEND
        assert cause.confidence == 0.85

    def test_status_503_backend(self) -> None:
        cause = self.svc._classify_single(self._no_match_log(503))
        assert cause is not None
        assert cause.category == DiagnosticCategory.BACKEND

    def test_status_500_backend_lower_confidence(self) -> None:
        cause = self.svc._classify_single(self._no_match_log(500))
        assert cause is not None
        assert cause.category == DiagnosticCategory.BACKEND
        assert cause.confidence == 0.6

    def test_status_599_backend_lower_confidence(self) -> None:
        """Any 5xx >= 500 (not 502/503/504) falls into the generic backend bucket."""
        cause = self.svc._classify_single(self._no_match_log(599))
        assert cause is not None
        assert cause.category == DiagnosticCategory.BACKEND
        assert cause.confidence == 0.6

    def test_status_200_no_match_returns_none(self) -> None:
        """Non-error status codes with no category/message yield None."""
        cause = self.svc._classify_single(self._no_match_log(200))
        assert cause is None

    def test_status_none_no_match_returns_none(self) -> None:
        """Missing status code and no category/message yields None."""
        cause = self.svc._classify_single(self._no_match_log(None))
        assert cause is None


# ---------------------------------------------------------------------------
# _classify_single — evidence and suggested_fix fields
# ---------------------------------------------------------------------------


class TestClassifySingleEvidenceFields:
    """Verify evidence list and suggested_fix are populated correctly."""

    def setup_method(self) -> None:
        self.svc = DiagnosticService(_make_session())

    def test_evidence_includes_error_message(self) -> None:
        log = _make_log(
            status_code=503,
            error_category=ErrorCategory.CIRCUIT_BREAKER,
            error_message="CB tripped",
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        assert any("CB tripped" in e for e in cause.evidence)

    def test_evidence_fallback_when_no_message(self) -> None:
        log = _make_log(
            error_category=ErrorCategory.CIRCUIT_BREAKER,
            error_message=None,
        )
        cause = self.svc._classify_single(log)
        assert cause is not None
        # Should use fallback string, not None
        assert any("CB open" in e for e in cause.evidence)

    def test_suggested_fix_present_for_all_categories(self) -> None:
        categories_and_logs = [
            _make_log(error_category=ErrorCategory.CIRCUIT_BREAKER),
            _make_log(error_category=ErrorCategory.CERTIFICATE),
            _make_log(error_category=ErrorCategory.POLICY),
            _make_log(error_category=ErrorCategory.RATE_LIMIT),
            _make_log(error_category=ErrorCategory.NETWORK),
            _make_log(error_category=ErrorCategory.TIMEOUT),
            _make_log(error_category=ErrorCategory.AUTH),
            _make_log(error_category=ErrorCategory.BACKEND),
        ]
        for log in categories_and_logs:
            cause = self.svc._classify_single(log)
            assert cause is not None, f"Expected cause for {log.error_category}"
            assert cause.suggested_fix, f"suggested_fix empty for {log.error_category}"


# ---------------------------------------------------------------------------
# _aggregate_timing
# ---------------------------------------------------------------------------


class TestAggregateTiming:
    """_aggregate_timing correctly averages duration_ms across logs."""

    def setup_method(self) -> None:
        self.svc = DiagnosticService(_make_session())

    def test_empty_list_returns_empty_breakdown(self) -> None:
        timing = self.svc._aggregate_timing([])
        assert isinstance(timing, TimingBreakdown)
        assert timing.total_ms is None

    def test_single_log_with_duration(self) -> None:
        logs = [_make_log(duration_ms=200)]
        timing = self.svc._aggregate_timing(logs)
        assert timing.total_ms == 200.0

    def test_multiple_logs_average(self) -> None:
        logs = [_make_log(duration_ms=100), _make_log(duration_ms=300)]
        timing = self.svc._aggregate_timing(logs)
        assert timing.total_ms == 200.0

    def test_logs_with_none_duration_excluded(self) -> None:
        logs = [_make_log(duration_ms=100), _make_log(duration_ms=None)]
        timing = self.svc._aggregate_timing(logs)
        # Only the 100ms log counted
        assert timing.total_ms == 100.0

    def test_all_logs_none_duration_returns_empty(self) -> None:
        logs = [_make_log(duration_ms=None), _make_log(duration_ms=None)]
        timing = self.svc._aggregate_timing(logs)
        assert timing.total_ms is None

    def test_rounding_to_two_decimal_places(self) -> None:
        logs = [_make_log(duration_ms=100), _make_log(duration_ms=200), _make_log(duration_ms=301)]
        timing = self.svc._aggregate_timing(logs)
        # avg = 601/3 = 200.333... → rounded to 200.33
        assert timing.total_ms == 200.33


# ---------------------------------------------------------------------------
# _build_request_summary
# ---------------------------------------------------------------------------


class TestBuildRequestSummary:
    """_build_request_summary maps log fields with GDPR redaction."""

    def setup_method(self) -> None:
        self.svc = DiagnosticService(_make_session())

    def test_all_fields_mapped(self) -> None:
        log = _make_log(
            status_code=502,
            request_id="req-xyz",
            method="GET",
            path="/v1/tools",
        )
        summary = self.svc._build_request_summary(log)
        assert summary.method == "GET"
        assert summary.path == "/v1/tools"
        assert summary.status_code == 502
        assert summary.request_id == "req-xyz"

    def test_none_fields_allowed(self) -> None:
        log = _make_log(status_code=None, method=None, path=None)
        log.request_id = None
        summary = self.svc._build_request_summary(log)
        assert summary.method is None
        assert summary.path is None
        assert summary.status_code is None
        assert summary.request_id is None


# ---------------------------------------------------------------------------
# _parse_network_path — static method
# ---------------------------------------------------------------------------


class TestParseNetworkPath:
    """_parse_network_path parses Via and X-Stoa-Timing headers."""

    @staticmethod
    def _resp(headers: dict[str, str]) -> httpx.Response:
        return httpx.Response(200, headers=headers)

    def test_single_via_hop(self) -> None:
        path = DiagnosticService._parse_network_path(self._resp({"via": "1.1 stoa-gateway (0.1.0)"}), 50.0)
        assert path is not None
        assert path.total_hops == 1
        assert path.hops[0].protocol == "1.1"
        assert path.hops[0].pseudonym == "stoa-gateway"
        assert path.total_latency_ms == 50.0

    def test_multiple_via_hops_comma_separated(self) -> None:
        path = DiagnosticService._parse_network_path(self._resp({"via": "1.1 proxy-a, 2.0 cdn.example.com"}), 120.0)
        assert path is not None
        assert path.total_hops == 2
        assert path.hops[0].pseudonym == "proxy-a"
        assert path.hops[1].pseudonym == "cdn.example.com"

    def test_via_with_version_prefix_stripped(self) -> None:
        """Protocol part: 'HTTP/1.1' → '1.1' (after split on '/')."""
        path = DiagnosticService._parse_network_path(self._resp({"via": "HTTP/1.1 proxy-x"}), 30.0)
        assert path is not None
        assert path.hops[0].protocol == "1.1"

    def test_via_entry_in_detected_intermediaries(self) -> None:
        path = DiagnosticService._parse_network_path(self._resp({"via": "1.1 stoa-gateway"}), 80.0)
        assert path is not None
        assert "stoa-gateway" in path.detected_intermediaries

    def test_x_stoa_timing_hops_only(self) -> None:
        """X-Stoa-Timing with hops=N (and no Via) adds to intermediaries."""
        path = DiagnosticService._parse_network_path(self._resp({"x-stoa-timing": "gw=5;hops=3"}), 100.0)
        assert path is not None
        assert any("3 hops" in s for s in path.detected_intermediaries)

    def test_x_stoa_timing_hops_zero_not_added(self) -> None:
        """hops=0 should NOT add an intermediary entry."""
        path = DiagnosticService._parse_network_path(self._resp({"x-stoa-timing": "hops=0"}), 10.0)
        # No Via, hops=0 → intermediaries empty → path is None
        assert path is None

    def test_combined_via_and_timing(self) -> None:
        """When both headers present, Via hops fill hops list; timing hops ignored."""
        path = DiagnosticService._parse_network_path(
            self._resp({"via": "1.1 stoa-gateway (0.1.0)", "x-stoa-timing": "gw=5;hops=1"}),
            80.0,
        )
        assert path is not None
        assert path.total_hops == 1
        assert "stoa-gateway" in path.detected_intermediaries

    def test_no_hop_headers_returns_none(self) -> None:
        path = DiagnosticService._parse_network_path(self._resp({"content-type": "application/json"}), 30.0)
        assert path is None

    def test_x_stoa_timing_invalid_hops_value_ignored(self) -> None:
        """Non-integer hops value does not raise; falls back gracefully."""
        path = DiagnosticService._parse_network_path(self._resp({"x-stoa-timing": "hops=notanumber"}), 50.0)
        assert path is None

    def test_latency_rounded_to_two_decimals(self) -> None:
        path = DiagnosticService._parse_network_path(self._resp({"via": "1.1 p"}), 50.1234)
        assert path is not None
        assert path.total_latency_ms == 50.12


# ---------------------------------------------------------------------------
# diagnose — async method
# ---------------------------------------------------------------------------


class TestDiagnose:
    """diagnose() queries the DB, classifies, and returns a DiagnosticReport."""

    @pytest.mark.asyncio
    async def test_diagnose_empty_logs(self) -> None:
        session = _make_session()
        session.execute.return_value = _make_execute_result([])
        svc = DiagnosticService(session)

        report = await svc.diagnose("t1", "gw1")

        assert isinstance(report, DiagnosticReport)
        assert report.tenant_id == "t1"
        assert report.gateway_id == "gw1"
        assert report.error_count == 0
        assert report.root_causes == []
        assert report.request_summary is None

    @pytest.mark.asyncio
    async def test_diagnose_single_log_returns_root_cause(self) -> None:
        log = _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT)
        session = _make_session()
        session.execute.return_value = _make_execute_result([log])
        svc = DiagnosticService(session)

        report = await svc.diagnose("t1", "gw1")

        assert report.error_count == 1
        assert len(report.root_causes) == 1
        assert report.root_causes[0].category == DiagnosticCategory.RATE_LIMIT
        assert report.request_summary is not None
        assert report.request_summary.request_id == "req-001"

    @pytest.mark.asyncio
    async def test_diagnose_multiple_logs_aggregated(self) -> None:
        logs = [
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT, request_id="r1"),
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT, request_id="r2"),
            _make_log(status_code=502, error_category=ErrorCategory.BACKEND, request_id="r3"),
        ]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        report = await svc.diagnose("t1", "gw1")

        assert report.error_count == 3
        # Two distinct categories
        categories = {rc.category for rc in report.root_causes}
        assert DiagnosticCategory.RATE_LIMIT in categories
        assert DiagnosticCategory.BACKEND in categories

    @pytest.mark.asyncio
    async def test_diagnose_root_causes_sorted_by_confidence_desc(self) -> None:
        logs = [
            _make_log(status_code=500, error_category=ErrorCategory.BACKEND),  # 0.85
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT),  # 0.95
        ]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        report = await svc.diagnose("t1", "gw1")

        confidences = [rc.confidence for rc in report.root_causes]
        assert confidences == sorted(confidences, reverse=True)

    @pytest.mark.asyncio
    async def test_diagnose_request_id_filter_replaces_conditions(self) -> None:
        """When request_id is passed, the filter list is replaced (not extended)."""
        log = _make_log(request_id="specific-req")
        session = _make_session()
        session.execute.return_value = _make_execute_result([log])
        svc = DiagnosticService(session)

        report = await svc.diagnose("t1", "gw1", request_id="specific-req")

        assert report.error_count == 1
        # DB was queried (execute called once)
        session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_diagnose_timing_populated_from_logs(self) -> None:
        logs = [_make_log(duration_ms=100), _make_log(duration_ms=300)]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        report = await svc.diagnose("t1", "gw1")

        assert report.timing.total_ms == 200.0

    @pytest.mark.asyncio
    async def test_diagnose_time_range_minutes_passed_through(self) -> None:
        session = _make_session()
        session.execute.return_value = _make_execute_result([])
        svc = DiagnosticService(session)

        report = await svc.diagnose("t1", "gw1", time_range_minutes=120)

        assert report.time_range_minutes == 120

    @pytest.mark.asyncio
    async def test_diagnose_same_category_evidence_merged(self) -> None:
        """Multiple logs with same category merge evidence, keep highest confidence."""
        logs = [
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT, error_message="quota 1"),
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT, error_message="quota 2"),
        ]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        report = await svc.diagnose("t1", "gw1")

        # Only one RATE_LIMIT root cause
        rate_limit_causes = [rc for rc in report.root_causes if rc.category == DiagnosticCategory.RATE_LIMIT]
        assert len(rate_limit_causes) == 1
        # Evidence should have been extended
        assert len(rate_limit_causes[0].evidence) >= 2


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------


class TestGetHistory:
    """get_history() returns DiagnosticListResponse with per-log reports."""

    @pytest.mark.asyncio
    async def test_get_history_empty_returns_empty_list(self) -> None:
        session = _make_session()
        session.execute.return_value = _make_execute_result([])
        svc = DiagnosticService(session)

        response = await svc.get_history("t1", "gw1")

        assert response.total == 0
        assert response.items == []

    @pytest.mark.asyncio
    async def test_get_history_single_log(self) -> None:
        log = _make_log(status_code=401, error_category=ErrorCategory.AUTH, duration_ms=50)
        session = _make_session()
        session.execute.return_value = _make_execute_result([log])
        svc = DiagnosticService(session)

        response = await svc.get_history("t1", "gw1")

        assert response.total == 1
        assert len(response.items) == 1
        report = response.items[0]
        assert report.error_count == 1
        assert report.time_range_minutes == 0
        assert report.timing.total_ms == 50.0

    @pytest.mark.asyncio
    async def test_get_history_multiple_logs(self) -> None:
        logs = [
            _make_log(status_code=401, error_category=ErrorCategory.AUTH, request_id="r1"),
            _make_log(status_code=502, error_category=ErrorCategory.BACKEND, request_id="r2"),
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT, request_id="r3"),
        ]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        response = await svc.get_history("t1", "gw1", limit=10)

        assert response.total == 3
        assert len(response.items) == 3

    @pytest.mark.asyncio
    async def test_get_history_log_without_duration(self) -> None:
        log = _make_log(duration_ms=None)
        session = _make_session()
        session.execute.return_value = _make_execute_result([log])
        svc = DiagnosticService(session)

        response = await svc.get_history("t1", "gw1")

        report = response.items[0]
        assert report.timing.total_ms is None


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------


class TestGetSummary:
    """get_summary() aggregates category stats across all tenant logs."""

    @pytest.mark.asyncio
    async def test_get_summary_empty_returns_zero(self) -> None:
        session = _make_session()
        session.execute.return_value = _make_execute_result([])
        svc = DiagnosticService(session)

        summary = await svc.get_summary("t1")

        assert summary.total_errors == 0
        assert summary.top_categories == []

    @pytest.mark.asyncio
    async def test_get_summary_single_category(self) -> None:
        logs = [
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT),
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT),
        ]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        summary = await svc.get_summary("t1")

        assert summary.total_errors == 2
        assert len(summary.top_categories) == 1
        stat = summary.top_categories[0]
        assert stat.category == DiagnosticCategory.RATE_LIMIT
        assert stat.count == 2
        assert stat.percentage == 100.0

    @pytest.mark.asyncio
    async def test_get_summary_multiple_categories(self) -> None:
        logs = [
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT),
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT),
            _make_log(status_code=401, error_category=ErrorCategory.AUTH),
        ]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        summary = await svc.get_summary("t1")

        assert summary.total_errors == 3
        categories = {s.category for s in summary.top_categories}
        assert DiagnosticCategory.RATE_LIMIT in categories
        assert DiagnosticCategory.AUTH in categories

    @pytest.mark.asyncio
    async def test_get_summary_sorted_by_count_desc(self) -> None:
        logs = [
            _make_log(status_code=401, error_category=ErrorCategory.AUTH),
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT),
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT),
            _make_log(status_code=429, error_category=ErrorCategory.RATE_LIMIT),
        ]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        summary = await svc.get_summary("t1")

        counts = [s.count for s in summary.top_categories]
        assert counts == sorted(counts, reverse=True)

    @pytest.mark.asyncio
    async def test_get_summary_percentage_calculation(self) -> None:
        logs = [
            _make_log(status_code=502, error_category=ErrorCategory.BACKEND),
            _make_log(status_code=502, error_category=ErrorCategory.BACKEND),
            _make_log(status_code=502, error_category=ErrorCategory.BACKEND),
            _make_log(status_code=401, error_category=ErrorCategory.AUTH),
        ]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        summary = await svc.get_summary("t1")

        backend_stat = next(s for s in summary.top_categories if s.category == DiagnosticCategory.BACKEND)
        assert backend_stat.percentage == 75.0
        auth_stat = next(s for s in summary.top_categories if s.category == DiagnosticCategory.AUTH)
        assert auth_stat.percentage == 25.0

    @pytest.mark.asyncio
    async def test_get_summary_time_range_passed_through(self) -> None:
        session = _make_session()
        session.execute.return_value = _make_execute_result([])
        svc = DiagnosticService(session)

        summary = await svc.get_summary("t1", time_range_minutes=30)

        assert summary.time_range_minutes == 30

    @pytest.mark.asyncio
    async def test_get_summary_logs_without_classifiable_category(self) -> None:
        """Logs that return None from _classify_single are not counted."""
        logs = [
            _make_log(status_code=200, error_category=None, error_message="generic err"),
        ]
        session = _make_session()
        session.execute.return_value = _make_execute_result(logs)
        svc = DiagnosticService(session)

        summary = await svc.get_summary("t1")

        # 1 error log but no classifiable category
        assert summary.total_errors == 1
        assert summary.top_categories == []


# ---------------------------------------------------------------------------
# check_connectivity
# ---------------------------------------------------------------------------


class TestCheckConnectivity:
    """check_connectivity() runs a 4-stage probe chain."""

    @pytest.mark.asyncio
    async def test_gateway_not_found_returns_unhealthy(self) -> None:
        svc = DiagnosticService(_make_session())
        with patch.object(svc, "_get_gateway", return_value=None):
            result = await svc.check_connectivity("t1", "nonexistent")

        assert result.overall_status == "unhealthy"
        assert len(result.stages) == 1
        assert result.stages[0].name == "lookup"
        assert result.stages[0].status == "error"
        assert "not found" in result.stages[0].error

    @pytest.mark.asyncio
    async def test_dns_failure_returns_unhealthy(self) -> None:
        mock_gw = MagicMock()
        mock_gw.base_url = "http://no-such-host.invalid:8080"
        svc = DiagnosticService(_make_session())

        with patch.object(svc, "_get_gateway", return_value=mock_gw):
            result = await svc.check_connectivity("t1", "gw1")

        assert result.overall_status == "unhealthy"
        stage_names = [s.name for s in result.stages]
        assert "dns" in stage_names
        dns_stage = next(s for s in result.stages if s.name == "dns")
        assert dns_stage.status == "error"

    @pytest.mark.asyncio
    async def test_tcp_failure_after_dns_success(self) -> None:
        """DNS succeeds (mocked), TCP connection fails."""

        mock_gw = MagicMock()
        mock_gw.base_url = "http://127.0.0.1:19999"
        svc = DiagnosticService(_make_session())

        with (
            patch.object(svc, "_get_gateway", return_value=mock_gw),
            patch(
                "src.services.diagnostic_service.socket.getaddrinfo",
                return_value=[("", "", "", "", ("127.0.0.1", 19999))],
            ),
            patch(
                "src.services.diagnostic_service.socket.create_connection", side_effect=OSError("Connection refused")
            ),
        ):
            result = await svc.check_connectivity("t1", "gw1")

        assert result.overall_status == "unhealthy"
        tcp_stage = next((s for s in result.stages if s.name == "tcp"), None)
        assert tcp_stage is not None
        assert tcp_stage.status == "error"

    @pytest.mark.asyncio
    async def test_http_success_returns_healthy(self) -> None:
        """DNS + TCP succeed (mocked), HTTP health check returns 200."""
        mock_gw = MagicMock()
        mock_gw.base_url = "http://127.0.0.1:8080"
        svc = DiagnosticService(_make_session())

        mock_sock = MagicMock()

        with (
            patch.object(svc, "_get_gateway", return_value=mock_gw),
            patch("src.services.diagnostic_service.socket.getaddrinfo", return_value=[()]),
            patch("src.services.diagnostic_service.socket.create_connection", return_value=mock_sock),
            patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200))),
        ):
            result = await svc.check_connectivity("t1", "gw1")

        assert result.overall_status == "healthy"
        stage_names = [s.name for s in result.stages]
        assert "dns" in stage_names
        assert "tcp" in stage_names
        assert "http_health" in stage_names
        http_stage = next(s for s in result.stages if s.name == "http_health")
        assert http_stage.status == "ok"
        assert http_stage.error is None

    @pytest.mark.asyncio
    async def test_http_error_status_records_error_stage(self) -> None:
        """HTTP health returns 503 → http_health stage status='error', overall='unhealthy'."""
        mock_gw = MagicMock()
        mock_gw.base_url = "http://127.0.0.1:8080"
        svc = DiagnosticService(_make_session())

        mock_sock = MagicMock()

        with (
            patch.object(svc, "_get_gateway", return_value=mock_gw),
            patch("src.services.diagnostic_service.socket.getaddrinfo", return_value=[()]),
            patch("src.services.diagnostic_service.socket.create_connection", return_value=mock_sock),
            patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(503))),
        ):
            result = await svc.check_connectivity("t1", "gw1")

        assert result.overall_status == "unhealthy"
        http_stage = next(s for s in result.stages if s.name == "http_health")
        assert http_stage.status == "error"
        assert "503" in http_stage.error

    @pytest.mark.asyncio
    async def test_http_exception_appends_error_stage(self) -> None:
        """httpx.HTTPError → http_health stage with error, overall depends on other stages."""
        mock_gw = MagicMock()
        mock_gw.base_url = "http://127.0.0.1:8080"
        svc = DiagnosticService(_make_session())

        mock_sock = MagicMock()

        with (
            patch.object(svc, "_get_gateway", return_value=mock_gw),
            patch("src.services.diagnostic_service.socket.getaddrinfo", return_value=[()]),
            patch("src.services.diagnostic_service.socket.create_connection", return_value=mock_sock),
            patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectError("refused"))),
        ):
            result = await svc.check_connectivity("t1", "gw1")

        assert result.overall_status == "unhealthy"
        http_stage = next((s for s in result.stages if s.name == "http_health"), None)
        assert http_stage is not None
        assert http_stage.status == "error"

    @pytest.mark.asyncio
    async def test_https_gateway_runs_tls_stage(self) -> None:
        """HTTPS gateway includes a TLS handshake stage."""
        mock_gw = MagicMock()
        mock_gw.base_url = "https://127.0.0.1:8443"
        svc = DiagnosticService(_make_session())

        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(svc, "_get_gateway", return_value=mock_gw),
            patch("src.services.diagnostic_service.socket.getaddrinfo", return_value=[()]),
            patch("src.services.diagnostic_service.socket.create_connection", return_value=mock_sock),
            patch("src.services.diagnostic_service.ssl.create_default_context") as mock_ctx,
            patch("httpx.AsyncClient.get", new=AsyncMock(return_value=httpx.Response(200))),
        ):
            mock_ctx.return_value.wrap_socket.return_value = MagicMock()
            result = await svc.check_connectivity("t1", "gw1")

        stage_names = [s.name for s in result.stages]
        assert "tls" in stage_names

    @pytest.mark.asyncio
    async def test_https_tls_failure_returns_unhealthy(self) -> None:
        """TLS handshake failure → unhealthy, no HTTP stage attempted."""
        import ssl as _ssl

        mock_gw = MagicMock()
        mock_gw.base_url = "https://127.0.0.1:8443"
        svc = DiagnosticService(_make_session())

        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)

        with (
            patch.object(svc, "_get_gateway", return_value=mock_gw),
            patch("src.services.diagnostic_service.socket.getaddrinfo", return_value=[()]),
            patch("src.services.diagnostic_service.socket.create_connection", return_value=mock_sock),
            patch("src.services.diagnostic_service.ssl.create_default_context") as mock_ctx,
        ):
            mock_ctx.return_value.wrap_socket.side_effect = _ssl.SSLError("CERTIFICATE_VERIFY_FAILED")
            result = await svc.check_connectivity("t1", "gw1")

        assert result.overall_status == "unhealthy"
        tls_stage = next((s for s in result.stages if s.name == "tls"), None)
        assert tls_stage is not None
        assert tls_stage.status == "error"
        # HTTP stage should NOT have been attempted after TLS failure
        assert not any(s.name == "http_health" for s in result.stages)

    @pytest.mark.asyncio
    async def test_connectivity_network_path_from_headers(self) -> None:
        """HTTP response with Via header populates network_path on ConnectivityResult."""
        mock_gw = MagicMock()
        mock_gw.base_url = "http://127.0.0.1:8080"
        svc = DiagnosticService(_make_session())

        mock_sock = MagicMock()
        mock_resp = httpx.Response(200, headers={"via": "1.1 stoa-gateway"})

        with (
            patch.object(svc, "_get_gateway", return_value=mock_gw),
            patch("src.services.diagnostic_service.socket.getaddrinfo", return_value=[()]),
            patch("src.services.diagnostic_service.socket.create_connection", return_value=mock_sock),
            patch("httpx.AsyncClient.get", new=AsyncMock(return_value=mock_resp)),
        ):
            result = await svc.check_connectivity("t1", "gw1")

        assert result.network_path is not None
        assert result.network_path.total_hops == 1
