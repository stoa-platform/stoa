"""Spec tests for CAB-2008 — Unify Security Posture Data Sources.

Generated from SPEC.md acceptance criteria. Tests the SecurityAggregationService
which aggregates OpenSearch audit-* + PG security_events + PG security_findings.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.security_aggregation_service import SecurityAggregationService


@pytest.fixture
def svc():
    return SecurityAggregationService()


@pytest.fixture
def mock_os_client():
    """Mock OpenSearch async client — default: empty results."""
    client = AsyncMock()
    client.search = AsyncMock(return_value=_os_aggs_empty())
    return client


# ---------------------------------------------------------------------------
# DB mock builder — matches the exact query sequence in calculate_aggregated_score
#
# Query sequence (6 calls):
#   1. security_events: group_by(severity) → .all() returns [{severity, cnt}]
#   2. security_events: count + max(created_at) → .one() returns (count, last_at)
#   3. security_findings: group_by(severity) where open → .all() returns [{severity, cnt}]
#   4. security_findings: count + max(created_at) → .one() returns (count, last_at)
#   5. security_findings: total count → .scalar_one() returns int
#   6. SecurityScan: last 2 scans → .all() returns [scan_rows]
# ---------------------------------------------------------------------------


def _build_score_db(
    *,
    evt_severity: dict[str, int] | None = None,
    evt_count: int = 0,
    evt_last: datetime | None = None,
    finding_severity: dict[str, int] | None = None,
    finding_count: int = 0,
    finding_last: datetime | None = None,
    finding_total: int = 0,
    scans: list | None = None,
) -> AsyncMock:
    """Build a mock db with side_effect matching calculate_aggregated_score query order."""
    # Q1: security_events severity group-by
    q1 = MagicMock()
    rows = []
    for sev, cnt in (evt_severity or {}).items():
        r = MagicMock()
        r.severity = sev
        r.cnt = cnt
        rows.append(r)
    q1.all.return_value = rows

    # Q2: security_events count + max(created_at)
    q2 = MagicMock()
    q2.one.return_value = (evt_count, evt_last)

    # Q3: security_findings severity group-by (open)
    q3 = MagicMock()
    frows = []
    for sev, cnt in (finding_severity or {}).items():
        r = MagicMock()
        r.severity = sev
        r.cnt = cnt
        frows.append(r)
    q3.all.return_value = frows

    # Q4: security_findings count + max(created_at)
    q4 = MagicMock()
    q4.one.return_value = (finding_count, finding_last)

    # Q5: security_findings total count
    q5 = MagicMock()
    q5.scalar_one.return_value = finding_total

    # Q6: SecurityScan last 2
    q6 = MagicMock()
    q6.all.return_value = scans or []

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[q1, q2, q3, q4, q5, q6])
    return db


# ---------------------------------------------------------------------------
# DB mock for list_aggregated_findings
#
# Query sequence (2 calls):
#   1. select(SecurityFinding).where(...) → .scalars().all() returns [findings]
#   2. select(SecurityEvent).where(...) → .scalars().all() returns [events]
# ---------------------------------------------------------------------------


def _build_findings_db(*, pg_findings: list | None = None, pg_events: list | None = None) -> AsyncMock:
    q1 = MagicMock()
    q1.scalars.return_value.all.return_value = pg_findings or []

    q2 = MagicMock()
    q2.scalars.return_value.all.return_value = pg_events or []

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[q1, q2])
    return db


# ---------------------------------------------------------------------------
# OpenSearch response factories
# ---------------------------------------------------------------------------


def _os_aggs_empty() -> dict:
    return {
        "hits": {"total": {"value": 0}, "hits": []},
        "aggregations": {
            "severity_counts": {"buckets": []},
            "last_event": {"value": None},
        },
    }


def _os_aggs_response(
    critical: int = 0,
    high: int = 0,
    medium: int = 0,
    info: int = 0,
    last_timestamp: str | None = None,
) -> dict:
    """OS aggs with severity counts. high→'error', medium→'warning' in OS terms."""
    buckets = []
    for sev, count in [("critical", critical), ("error", high), ("warning", medium), ("info", info)]:
        if count > 0:
            buckets.append({"key": sev, "doc_count": count})
    total = critical + high + medium + info
    return {
        "hits": {"total": {"value": total}, "hits": []},
        "aggregations": {
            "severity_counts": {"buckets": buckets},
            "last_event": ({"value_as_string": last_timestamp} if last_timestamp else {"value": None}),
        },
    }


def _os_search_response(events: list[dict]) -> dict:
    """OS search response with hit documents."""
    hits = []
    for evt in events:
        hits.append(
            {
                "_id": evt.get("id", str(uuid.uuid4())),
                "_source": {
                    "@timestamp": evt.get("timestamp", datetime.now(UTC).isoformat()),
                    "event_type": evt.get("event_type", "auth.failure"),
                    "severity": evt.get("severity", "warning"),
                    "actor": {
                        "tenant_id": evt.get("tenant_id", "oasis"),
                        "id": evt.get("user_id"),
                        "email": evt.get("email", "user@example.com"),
                        "ip_address": evt.get("ip", "10.0.0.1"),
                    },
                    "action": evt.get("action", "POST /v1/auth/token"),
                    "outcome": evt.get("outcome", "failure"),
                    "correlation_id": evt.get("correlation_id", str(uuid.uuid4())),
                },
            }
        )
    return {
        "hits": {
            "total": {"value": len(events)},
            "hits": hits,
        },
    }


def _make_pg_event(
    event_type: str = "rate_limit_exceeded",
    severity: str = "warning",
    tenant_id: str = "oasis",
) -> MagicMock:
    evt = MagicMock()
    evt.id = uuid.uuid4()
    evt.event_id = uuid.uuid4()
    evt.tenant_id = tenant_id
    evt.event_type = event_type
    evt.severity = severity
    evt.source = "kafka"
    evt.payload = {}
    evt.created_at = datetime.now(UTC)
    return evt


# ===========================================================================
# AC1: OpenSearch audit events included in score penalty
# ===========================================================================


class TestAC1ScoreIncludesOpenSearchAuditEvents:
    @pytest.mark.asyncio
    async def test_score_reflects_os_warning_events(self, svc, mock_os_client):
        """5 warning-level audit events → penalty 5 * 2.0 = 10 → score 90."""
        mock_os_client.search = AsyncMock(return_value=_os_aggs_response(medium=5))
        db = _build_score_db()

        result = await svc.calculate_aggregated_score("oasis", db, mock_os_client)

        assert result.score == pytest.approx(90.0, abs=0.1)
        assert result.findings_summary.medium == 5

    @pytest.mark.asyncio
    async def test_score_reflects_os_critical_events(self, svc, mock_os_client):
        """2 critical audit events → penalty 2 * 10.0 = 20 → score 80."""
        mock_os_client.search = AsyncMock(return_value=_os_aggs_response(critical=2))
        db = _build_score_db()

        result = await svc.calculate_aggregated_score("oasis", db, mock_os_client)

        assert result.score == pytest.approx(80.0, abs=0.1)
        assert result.findings_summary.critical == 2


# ===========================================================================
# AC2: PG security_events included in score penalty
# ===========================================================================


class TestAC2ScoreIncludesPgSecurityEvents:
    @pytest.mark.asyncio
    async def test_score_reflects_pg_security_events(self, svc, mock_os_client):
        """3 'error' severity PG events → maps to high → penalty 3 * 5.0 = 15 → score 85."""
        mock_os_client.search = AsyncMock(return_value=_os_aggs_empty())
        db = _build_score_db(evt_severity={"error": 3}, evt_count=3)

        result = await svc.calculate_aggregated_score("oasis", db, mock_os_client)

        assert result.score == pytest.approx(85.0, abs=0.1)
        assert result.findings_summary.high == 3


# ===========================================================================
# AC3: All sources empty -> score 0, status "no_data"
# ===========================================================================


class TestAC3EmptySourcesScoreZero:
    @pytest.mark.asyncio
    async def test_empty_all_sources_score_zero(self, svc, mock_os_client):
        db = _build_score_db()

        result = await svc.calculate_aggregated_score("oasis", db, mock_os_client)

        assert result.score == 0.0
        assert result.grade == "F"
        assert result.data_freshness.status == "no_data"

    @pytest.mark.asyncio
    async def test_empty_sources_freshness_counts(self, svc, mock_os_client):
        db = _build_score_db()

        result = await svc.calculate_aggregated_score("oasis", db, mock_os_client)

        sources = result.data_freshness.sources
        assert sources["opensearch_audit"].count == 0
        assert sources["pg_security_events"].count == 0
        assert sources["pg_security_findings"].count == 0


# ===========================================================================
# AC4: Derived findings from OpenSearch audit events
# ===========================================================================


class TestAC4FindingsIncludeAuditEvents:
    @pytest.mark.asyncio
    async def test_audit_findings_have_scanner_audit(self, svc, mock_os_client):
        mock_os_client.search = AsyncMock(
            return_value=_os_search_response(
                [
                    {"event_type": "auth.failure", "severity": "warning", "tenant_id": "oasis"},
                ]
            )
        )
        db = _build_findings_db()

        result = await svc.list_aggregated_findings("oasis", db, mock_os_client)

        assert len(result.findings) == 1
        assert result.findings[0].scanner == "audit"
        assert result.findings[0].severity.value == "medium"

    @pytest.mark.asyncio
    async def test_audit_findings_strip_pii(self, svc, mock_os_client):
        """Derived findings must NOT contain actor.email or actor.ip_address."""
        mock_os_client.search = AsyncMock(
            return_value=_os_search_response(
                [
                    {
                        "event_type": "auth.failure",
                        "severity": "warning",
                        "tenant_id": "oasis",
                        "email": "secret@corp.com",
                        "ip": "192.168.1.42",
                    },
                ]
            )
        )
        db = _build_findings_db()

        result = await svc.list_aggregated_findings("oasis", db, mock_os_client)

        finding = result.findings[0]
        assert "secret@corp.com" not in (finding.description or "")
        assert "192.168.1.42" not in (finding.description or "")


# ===========================================================================
# AC5: Derived findings from PG security_events
# ===========================================================================


class TestAC5FindingsIncludeSecurityEvents:
    @pytest.mark.asyncio
    async def test_security_event_findings_have_scanner_tag(self, svc, mock_os_client):
        mock_os_client.search = AsyncMock(return_value=_os_search_response([]))
        events = [_make_pg_event("rate_limit_exceeded", "warning")]
        db = _build_findings_db(pg_events=events)

        result = await svc.list_aggregated_findings("oasis", db, mock_os_client)

        assert len(result.findings) == 1
        assert result.findings[0].scanner == "security_event"


# ===========================================================================
# AC6: data_freshness present with per-source breakdown
# ===========================================================================


class TestAC6DataFreshnessPresent:
    @pytest.mark.asyncio
    async def test_freshness_has_three_sources(self, svc, mock_os_client):
        now = datetime.now(UTC)
        mock_os_client.search = AsyncMock(return_value=_os_aggs_response(medium=1, last_timestamp=now.isoformat()))
        db = _build_score_db(evt_severity={"warning": 1}, evt_count=1, evt_last=now)

        result = await svc.calculate_aggregated_score("oasis", db, mock_os_client)

        assert result.data_freshness is not None
        sources = result.data_freshness.sources
        assert "opensearch_audit" in sources
        assert "pg_security_events" in sources
        assert "pg_security_findings" in sources


# ===========================================================================
# AC7: data_freshness.status = "fresh" when data < 1h old
# ===========================================================================


class TestAC7FreshStatus:
    @pytest.mark.asyncio
    async def test_fresh_when_recent_data(self, svc, mock_os_client):
        recent = datetime.now(UTC) - timedelta(minutes=30)
        mock_os_client.search = AsyncMock(return_value=_os_aggs_response(medium=1, last_timestamp=recent.isoformat()))
        db = _build_score_db()

        result = await svc.calculate_aggregated_score("oasis", db, mock_os_client)

        assert result.data_freshness.status == "fresh"


# ===========================================================================
# AC8: data_freshness.status = "stale" when data 1h-24h old
# ===========================================================================


class TestAC8StaleStatus:
    @pytest.mark.asyncio
    async def test_stale_when_data_between_1h_and_24h(self, svc, mock_os_client):
        old = datetime.now(UTC) - timedelta(hours=6)
        mock_os_client.search = AsyncMock(return_value=_os_aggs_response(medium=1, last_timestamp=old.isoformat()))
        db = _build_score_db()

        result = await svc.calculate_aggregated_score("oasis", db, mock_os_client)

        assert result.data_freshness.status == "stale"


# ===========================================================================
# AC9: POST /findings/ingest still works (regression)
# ===========================================================================


class TestAC9IngestStillWorks:
    @pytest.mark.asyncio
    async def test_ingest_creates_scanner_findings(self):
        """Existing SecurityScannerService.ingest_findings must still work."""
        from src.services.security_scanner_service import SecurityScannerService

        scanner_svc = SecurityScannerService()
        db = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock())

        findings_data = [
            {
                "rule_id": "CVE-2024-1234",
                "title": "Test vuln",
                "severity": "high",
                "resource_type": "container",
                "resource_name": "api:latest",
                "description": "Test",
            }
        ]

        result = await scanner_svc.ingest_findings("oasis", str(uuid.uuid4()), "trivy", findings_data, db)
        assert result >= 0


# ===========================================================================
# AC10: Pagination and filters work across all sources
# ===========================================================================


class TestAC10PaginationAndFilters:
    @pytest.mark.asyncio
    async def test_severity_filter_applies_to_os(self, svc, mock_os_client):
        """Filtering by severity=high: OS query uses 'error' term, returns only high."""
        mock_os_client.search = AsyncMock(
            return_value=_os_search_response(
                [
                    {"event_type": "auth.failure", "severity": "error", "tenant_id": "oasis"},
                ]
            )
        )
        db = _build_findings_db()

        result = await svc.list_aggregated_findings("oasis", db, mock_os_client, severity="high")

        assert len(result.findings) == 1
        assert result.findings[0].severity.value == "high"

    @pytest.mark.asyncio
    async def test_pagination_across_sources(self, svc, mock_os_client):
        """page_size=2 should limit total findings returned."""
        mock_os_client.search = AsyncMock(
            return_value=_os_search_response(
                [{"event_type": f"event_{i}", "severity": "warning", "tenant_id": "oasis"} for i in range(5)]
            )
        )
        db = _build_findings_db()

        result = await svc.list_aggregated_findings("oasis", db, mock_os_client, page=1, page_size=2)

        assert len(result.findings) == 2
        assert result.has_more is True
        assert result.total == 5


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCaseOpenSearchUnavailable:
    @pytest.mark.asyncio
    async def test_os_timeout_graceful_degradation(self, svc):
        """When OS is down, score still works from PG data alone."""
        os_client = AsyncMock()
        os_client.search = AsyncMock(side_effect=ConnectionError("timeout"))
        db = _build_score_db(evt_severity={"error": 2}, evt_count=2)

        result = await svc.calculate_aggregated_score("oasis", db, os_client)

        assert result.score == pytest.approx(90.0, abs=0.1)
        assert result.data_freshness.sources["opensearch_audit"].count == -1


class TestEdgeCaseSeverityNormalization:
    @pytest.mark.asyncio
    async def test_warning_maps_to_medium(self, svc, mock_os_client):
        mock_os_client.search = AsyncMock(
            return_value=_os_search_response(
                [
                    {"severity": "warning", "tenant_id": "oasis"},
                ]
            )
        )
        db = _build_findings_db()

        result = await svc.list_aggregated_findings("oasis", db, mock_os_client)

        assert result.findings[0].severity.value == "medium"

    @pytest.mark.asyncio
    async def test_error_maps_to_high(self, svc, mock_os_client):
        mock_os_client.search = AsyncMock(
            return_value=_os_search_response(
                [
                    {"severity": "error", "tenant_id": "oasis"},
                ]
            )
        )
        db = _build_findings_db()

        result = await svc.list_aggregated_findings("oasis", db, mock_os_client)

        assert result.findings[0].severity.value == "high"


class TestEdgeCaseMixedFreshness:
    @pytest.mark.asyncio
    async def test_fresh_if_any_source_recent(self, svc, mock_os_client):
        """OS has recent data (5min), PG events old (3 days) → status is 'fresh'."""
        recent = datetime.now(UTC) - timedelta(minutes=5)
        old = datetime.now(UTC) - timedelta(days=3)

        mock_os_client.search = AsyncMock(return_value=_os_aggs_response(medium=1, last_timestamp=recent.isoformat()))
        db = _build_score_db(evt_severity={"warning": 1}, evt_count=1, evt_last=old)

        result = await svc.calculate_aggregated_score("oasis", db, mock_os_client)

        assert result.data_freshness.status == "fresh"
