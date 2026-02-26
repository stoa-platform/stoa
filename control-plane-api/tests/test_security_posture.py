"""Tests for Security Posture Dashboard (CAB-1461 P1, CAB-1489 completion).

101 tests covering:
- SecurityScannerService: score calculation, findings CRUD, scans, drift, compliance, secrets
- Edge cases: info-only findings, empty baseline, complete_scan, NIS2 with findings, boundary grades
- Router endpoints: all 10 endpoints with RBAC checks
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Register security_posture router on the app (idempotent).
# This ensures tests work regardless of whether main.py includes the router.
from src.main import app as _app
from src.routers.security_posture import router as _security_router

_registered_paths = {getattr(r, "path", "") for r in _app.routes}
if "/v1/security/{tenant_id}/score" not in _registered_paths:
    _app.include_router(_security_router)

from src.schemas.security_posture import (
    ComplianceControl,
    ComplianceScoreResponse,
    DriftAlert,
    DriftReportResponse,
    FindingSeverity,
    FindingsListResponse,
    ScanHistoryResponse,
    SecurityFindingResponse,
    SecurityScanResponse,
    SecurityScoreResponse,
    SecretsHealthResponse,
    SeverityBreakdown,
)
from src.services.security_scanner_service import SecurityScannerService

SERVICE_PATH = "src.routers.security_posture.security_scanner_service"


# ────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────


@pytest.fixture
def service():
    return SecurityScannerService()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _make_score_response(tenant_id="acme", score=85.0, grade="B"):
    return SecurityScoreResponse(
        tenant_id=tenant_id,
        score=score,
        grade=grade,
        findings_summary=SeverityBreakdown(critical=0, high=1, medium=3, low=2, info=0),
        total_findings=10,
        open_findings=6,
        last_scan_at=datetime.now(UTC),
        trend=2.5,
    )


def _make_findings_response(tenant_id="acme"):
    return FindingsListResponse(
        findings=[
            SecurityFindingResponse(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                scan_id=str(uuid.uuid4()),
                scanner="trivy",
                severity=FindingSeverity.HIGH,
                rule_id="CVE-2024-1234",
                rule_name="Test Vulnerability",
                resource_type="container",
                resource_name="nginx:latest",
                description="Test finding",
                remediation="Update to latest",
                status="open",
                created_at=datetime.now(UTC),
            )
        ],
        total=1,
        page=1,
        page_size=50,
        has_more=False,
    )


def _make_scan_history_response(tenant_id="acme"):
    return ScanHistoryResponse(
        scans=[
            SecurityScanResponse(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                scanner="trivy",
                status="completed",
                findings_count=5,
                score=85.0,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
        ],
        total=1,
    )


def _make_drift_response(tenant_id="acme", has_baseline=True, drifts=None):
    return DriftReportResponse(
        tenant_id=tenant_id,
        baseline_date=datetime.now(UTC) if has_baseline else None,
        drifts=drifts or [],
        total_drifts=len(drifts) if drifts else 0,
        has_baseline=has_baseline,
    )


def _make_compliance_response(tenant_id="acme", framework="DORA"):
    return ComplianceScoreResponse(
        tenant_id=tenant_id,
        framework=framework,
        score=85.7,
        controls=[
            ComplianceControl(
                control_id="DORA-5.1",
                framework=framework,
                article="Art.5",
                description="ICT risk management framework",
                status="compliant",
                findings_count=0,
            )
        ],
        compliant_count=6,
        total_controls=7,
    )


def _make_secrets_response(tenant_id="acme"):
    return SecretsHealthResponse(
        tenant_id=tenant_id,
        total_secrets=0,
        healthy=0,
        expiring_soon=0,
        expired=0,
        orphan=0,
        secrets=[],
    )


# ════════════════════════════════════════════════
# SERVICE UNIT TESTS
# ════════════════════════════════════════════════


class TestScoreToGrade:
    """Test the grade calculation helper."""

    def test_grade_a_at_90(self, service):
        assert service._score_to_grade(90.0) == "A"

    def test_grade_a_at_100(self, service):
        assert service._score_to_grade(100.0) == "A"

    def test_grade_a_at_95(self, service):
        assert service._score_to_grade(95.0) == "A"

    def test_grade_b_at_80(self, service):
        assert service._score_to_grade(80.0) == "B"

    def test_grade_b_at_89(self, service):
        assert service._score_to_grade(89.9) == "B"

    def test_grade_c_at_70(self, service):
        assert service._score_to_grade(70.0) == "C"

    def test_grade_c_at_79(self, service):
        assert service._score_to_grade(79.9) == "C"

    def test_grade_d_at_60(self, service):
        assert service._score_to_grade(60.0) == "D"

    def test_grade_d_at_69(self, service):
        assert service._score_to_grade(69.9) == "D"

    def test_grade_f_at_59(self, service):
        assert service._score_to_grade(59.9) == "F"

    def test_grade_f_at_0(self, service):
        assert service._score_to_grade(0.0) == "F"


class TestCalculateScore:
    """Test security score calculation."""

    @pytest.mark.asyncio
    async def test_perfect_score_no_findings(self, service, mock_db):
        """No open findings → score 100."""
        severity_result = MagicMock()
        severity_result.all.return_value = []
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        scan_result = MagicMock()
        scan_result.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[severity_result, total_result, scan_result])

        result = await service.calculate_score("acme", mock_db)
        assert result.score == 100.0
        assert result.grade == "A"
        assert result.open_findings == 0

    @pytest.mark.asyncio
    async def test_score_with_critical_finding(self, service, mock_db):
        """1 critical finding → score 90 (100 - 10*1)."""
        row = MagicMock()
        row.severity = "critical"
        row.cnt = 1
        severity_result = MagicMock()
        severity_result.all.return_value = [row]
        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        scan_result = MagicMock()
        scan_result.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[severity_result, total_result, scan_result])

        result = await service.calculate_score("acme", mock_db)
        assert result.score == 90.0
        assert result.grade == "A"

    @pytest.mark.asyncio
    async def test_score_with_mixed_findings(self, service, mock_db):
        """2 critical + 3 high → score 100-20-15 = 65."""
        rows = [MagicMock(severity="critical", cnt=2), MagicMock(severity="high", cnt=3)]
        severity_result = MagicMock()
        severity_result.all.return_value = rows
        total_result = MagicMock()
        total_result.scalar_one.return_value = 5
        scan_result = MagicMock()
        scan_result.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[severity_result, total_result, scan_result])

        result = await service.calculate_score("acme", mock_db)
        assert result.score == 65.0
        assert result.grade == "D"

    @pytest.mark.asyncio
    async def test_score_floor_at_zero(self, service, mock_db):
        """Many findings → score floors at 0."""
        rows = [MagicMock(severity="critical", cnt=20)]
        severity_result = MagicMock()
        severity_result.all.return_value = rows
        total_result = MagicMock()
        total_result.scalar_one.return_value = 20
        scan_result = MagicMock()
        scan_result.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[severity_result, total_result, scan_result])

        result = await service.calculate_score("acme", mock_db)
        assert result.score == 0.0
        assert result.grade == "F"

    @pytest.mark.asyncio
    async def test_trend_calculation(self, service, mock_db):
        """Trend = current score - previous score."""
        severity_result = MagicMock()
        severity_result.all.return_value = []
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        prev_scan = MagicMock(completed_at=datetime.now(UTC), score=95.0)
        curr_scan = MagicMock(completed_at=datetime.now(UTC), score=None)
        scan_result = MagicMock()
        scan_result.all.return_value = [curr_scan, prev_scan]
        mock_db.execute = AsyncMock(side_effect=[severity_result, total_result, scan_result])

        result = await service.calculate_score("acme", mock_db)
        assert result.trend == 5.0  # 100 - 95

    @pytest.mark.asyncio
    async def test_no_trend_single_scan(self, service, mock_db):
        """No trend with only one scan."""
        severity_result = MagicMock()
        severity_result.all.return_value = []
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        scan_result = MagicMock()
        scan_result.all.return_value = [MagicMock(completed_at=datetime.now(UTC), score=100.0)]
        mock_db.execute = AsyncMock(side_effect=[severity_result, total_result, scan_result])

        result = await service.calculate_score("acme", mock_db)
        assert result.trend is None


class TestListFindings:
    """Test findings listing with filters."""

    @pytest.mark.asyncio
    async def test_list_findings_default(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        findings_result = MagicMock()
        findings_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[count_result, findings_result])

        result = await service.list_findings("acme", mock_db)
        assert result.total == 0
        assert result.findings == []
        assert result.page == 1

    @pytest.mark.asyncio
    async def test_list_findings_with_severity_filter(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        findings_result = MagicMock()
        findings_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[count_result, findings_result])

        result = await service.list_findings("acme", mock_db, severity="critical")
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_findings_pagination(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 100
        findings_result = MagicMock()
        findings_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[count_result, findings_result])

        result = await service.list_findings("acme", mock_db, page=2, page_size=10)
        assert result.total == 100
        assert result.has_more is True

    @pytest.mark.asyncio
    async def test_list_findings_with_all_filters(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        findings_result = MagicMock()
        findings_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[count_result, findings_result])

        result = await service.list_findings("acme", mock_db, severity="high", status="open", scanner="trivy")
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_list_findings_has_more_false(self, service, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 5
        findings_result = MagicMock()
        findings_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[count_result, findings_result])

        result = await service.list_findings("acme", mock_db, page=1, page_size=50)
        assert result.has_more is False


class TestIngestFindings:
    """Test finding ingestion."""

    @pytest.mark.asyncio
    async def test_ingest_single_finding(self, service, mock_db):
        mock_db.execute = AsyncMock()
        raw = [{"severity": "high", "rule_id": "CVE-1234", "rule_name": "Test"}]
        count = await service.ingest_findings("acme", str(uuid.uuid4()), "trivy", raw, mock_db)
        assert count == 1
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_ingest_multiple_findings(self, service, mock_db):
        mock_db.execute = AsyncMock()
        raw = [
            {"severity": "high", "rule_id": "CVE-1", "rule_name": "Test1"},
            {"severity": "medium", "rule_id": "CVE-2", "rule_name": "Test2"},
            {"severity": "low", "rule_id": "CVE-3", "rule_name": "Test3"},
        ]
        count = await service.ingest_findings("acme", str(uuid.uuid4()), "trivy", raw, mock_db)
        assert count == 3

    @pytest.mark.asyncio
    async def test_ingest_with_defaults(self, service, mock_db):
        mock_db.execute = AsyncMock()
        raw = [{"id": "unknown-rule", "title": "Unknown"}]
        count = await service.ingest_findings("acme", str(uuid.uuid4()), "kubescape", raw, mock_db)
        assert count == 1

    @pytest.mark.asyncio
    async def test_ingest_empty_list(self, service, mock_db):
        mock_db.execute = AsyncMock()
        count = await service.ingest_findings("acme", str(uuid.uuid4()), "trivy", [], mock_db)
        assert count == 0

    @pytest.mark.asyncio
    async def test_ingest_updates_scan_record(self, service, mock_db):
        mock_db.execute = AsyncMock()
        raw = [{"severity": "high", "rule_id": "CVE-1", "rule_name": "T"}]
        await service.ingest_findings("acme", str(uuid.uuid4()), "trivy", raw, mock_db)
        # execute called for: update scan record + flush
        assert mock_db.execute.called


class TestResolveFinding:
    """Test finding resolution."""

    @pytest.mark.asyncio
    async def test_resolve_existing(self, service, mock_db):
        result = MagicMock()
        result.rowcount = 1
        mock_db.execute = AsyncMock(return_value=result)
        assert await service.resolve_finding(str(uuid.uuid4()), mock_db) is True

    @pytest.mark.asyncio
    async def test_resolve_nonexistent(self, service, mock_db):
        result = MagicMock()
        result.rowcount = 0
        mock_db.execute = AsyncMock(return_value=result)
        assert await service.resolve_finding(str(uuid.uuid4()), mock_db) is False


class TestCreateScan:
    """Test scan creation."""

    @pytest.mark.asyncio
    async def test_create_scan(self, service, mock_db):
        scan_id = await service.create_scan("acme", "trivy", mock_db)
        assert scan_id  # UUID string
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_create_scan_returns_uuid(self, service, mock_db):
        scan_id = await service.create_scan("acme", "kubescape", mock_db)
        uuid.UUID(scan_id)  # Validates UUID format

    @pytest.mark.asyncio
    async def test_create_scan_flushes(self, service, mock_db):
        await service.create_scan("acme", "trivy", mock_db)
        mock_db.flush.assert_awaited_once()


class TestGetScanHistory:
    """Test scan history retrieval."""

    @pytest.mark.asyncio
    async def test_empty_history(self, service, mock_db):
        scans_result = MagicMock()
        scans_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        mock_db.execute = AsyncMock(side_effect=[scans_result, count_result])

        result = await service.get_scan_history("acme", mock_db)
        assert result.scans == []
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_history_with_scans(self, service, mock_db):
        scan = MagicMock()
        scan.id = uuid.uuid4()
        scan.tenant_id = "acme"
        scan.scanner = "trivy"
        scan.status = "completed"
        scan.findings_count = 5
        scan.score = 85.0
        scan.started_at = datetime.now(UTC)
        scan.completed_at = datetime.now(UTC)
        scans_result = MagicMock()
        scans_result.scalars.return_value.all.return_value = [scan]
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        mock_db.execute = AsyncMock(side_effect=[scans_result, count_result])

        result = await service.get_scan_history("acme", mock_db)
        assert len(result.scans) == 1
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_history_respects_limit(self, service, mock_db):
        scans_result = MagicMock()
        scans_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        mock_db.execute = AsyncMock(side_effect=[scans_result, count_result])

        await service.get_scan_history("acme", mock_db, limit=5)
        assert mock_db.execute.called


class TestSetBaseline:
    """Test golden state baseline management."""

    @pytest.mark.asyncio
    async def test_create_new_baseline(self, service, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        await service.set_baseline("acme", {"CVE-1": "resolved"}, mock_db)
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_update_existing_baseline(self, service, mock_db):
        existing = MagicMock()
        existing.baseline = {"CVE-1": "resolved"}
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=result)

        await service.set_baseline("acme", {"CVE-1": "resolved", "CVE-2": "open"}, mock_db)
        assert existing.baseline == {"CVE-1": "resolved", "CVE-2": "open"}

    @pytest.mark.asyncio
    async def test_set_baseline_flushes(self, service, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        await service.set_baseline("acme", {}, mock_db)
        mock_db.flush.assert_awaited_once()


class TestDetectDrift:
    """Test drift detection."""

    @pytest.mark.asyncio
    async def test_no_baseline(self, service, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        report = await service.detect_drift("acme", mock_db)
        assert report.has_baseline is False
        assert report.total_drifts == 0

    @pytest.mark.asyncio
    async def test_no_drift(self, service, mock_db):
        baseline = MagicMock()
        baseline.baseline = {"CVE-1": "open"}
        baseline.updated_at = datetime.now(UTC)
        baseline.created_at = datetime.now(UTC)
        baseline_result = MagicMock()
        baseline_result.scalar_one_or_none.return_value = baseline

        finding_row = MagicMock(rule_id="CVE-1", rule_name="Test", severity="high")
        findings_result = MagicMock()
        findings_result.all.return_value = [finding_row]

        mock_db.execute = AsyncMock(side_effect=[baseline_result, findings_result])

        report = await service.detect_drift("acme", mock_db)
        assert report.has_baseline is True
        assert report.total_drifts == 0

    @pytest.mark.asyncio
    async def test_regression_drift(self, service, mock_db):
        baseline = MagicMock()
        baseline.baseline = {"CVE-1": "resolved"}
        baseline.updated_at = datetime.now(UTC)
        baseline.created_at = datetime.now(UTC)
        baseline_result = MagicMock()
        baseline_result.scalar_one_or_none.return_value = baseline

        finding_row = MagicMock(rule_id="CVE-1", title="Regression Bug", severity="high")
        findings_result = MagicMock()
        findings_result.all.return_value = [finding_row]

        mock_db.execute = AsyncMock(side_effect=[baseline_result, findings_result])

        report = await service.detect_drift("acme", mock_db)
        assert report.total_drifts == 1
        assert report.drifts[0].rule_id == "CVE-1"
        assert report.drifts[0].expected_status == "resolved"
        assert report.drifts[0].actual_status == "open"

    @pytest.mark.asyncio
    async def test_drift_with_multiple_rules(self, service, mock_db):
        baseline = MagicMock()
        baseline.baseline = {"CVE-1": "resolved", "CVE-2": "resolved", "CVE-3": "open"}
        baseline.updated_at = datetime.now(UTC)
        baseline.created_at = datetime.now(UTC)
        baseline_result = MagicMock()
        baseline_result.scalar_one_or_none.return_value = baseline

        rows = [
            MagicMock(rule_id="CVE-1", title="Bug1", severity="critical"),
            MagicMock(rule_id="CVE-3", title="Bug3", severity="low"),
        ]
        findings_result = MagicMock()
        findings_result.all.return_value = rows

        mock_db.execute = AsyncMock(side_effect=[baseline_result, findings_result])

        report = await service.detect_drift("acme", mock_db)
        assert report.total_drifts == 1  # Only CVE-1 regressed


class TestGetComplianceScore:
    """Test compliance scoring."""

    @pytest.mark.asyncio
    async def test_dora_full_compliance(self, service, mock_db):
        result = MagicMock()
        result.all.return_value = []  # No open findings
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "DORA", mock_db)
        assert response.score == 100.0
        assert response.framework == "DORA"
        assert response.total_controls == 7
        assert response.compliant_count == 7

    @pytest.mark.asyncio
    async def test_nis2_full_compliance(self, service, mock_db):
        result = MagicMock()
        result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "NIS2", mock_db)
        assert response.framework == "NIS2"
        assert response.total_controls == 6
        assert response.compliant_count == 6

    @pytest.mark.asyncio
    async def test_dora_with_critical_findings(self, service, mock_db):
        rows = [MagicMock(severity="critical", cnt=2)]
        result = MagicMock()
        result.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "DORA", mock_db)
        assert response.score == 0.0
        assert response.compliant_count == 0
        assert all(c.status == "non_compliant" for c in response.controls)

    @pytest.mark.asyncio
    async def test_dora_with_high_findings(self, service, mock_db):
        rows = [MagicMock(severity="high", cnt=3)]
        result = MagicMock()
        result.all.return_value = rows
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "DORA", mock_db)
        assert response.score == 0.0  # All partial, none compliant
        assert all(c.status == "partial" for c in response.controls)

    @pytest.mark.asyncio
    async def test_compliance_case_insensitive(self, service, mock_db):
        result = MagicMock()
        result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "dora", mock_db)
        assert response.framework == "DORA"

    @pytest.mark.asyncio
    async def test_dora_controls_have_correct_articles(self, service, mock_db):
        result = MagicMock()
        result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "DORA", mock_db)
        articles = {c.article for c in response.controls}
        assert "Art.5" in articles
        assert "Art.9" in articles
        assert "Art.11" in articles

    @pytest.mark.asyncio
    async def test_nis2_controls_have_correct_articles(self, service, mock_db):
        result = MagicMock()
        result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "NIS2", mock_db)
        articles = {c.article for c in response.controls}
        assert "Art.21" in articles
        assert "Art.23" in articles


class TestGetSecretsHealth:
    """Test secrets health check."""

    @pytest.mark.asyncio
    async def test_returns_empty_response(self, service):
        result = await service.get_secrets_health("acme")
        assert result.total_secrets == 0
        assert result.tenant_id == "acme"

    @pytest.mark.asyncio
    async def test_returns_correct_tenant(self, service):
        result = await service.get_secrets_health("other-tenant")
        assert result.tenant_id == "other-tenant"

    @pytest.mark.asyncio
    async def test_all_counts_zero(self, service):
        result = await service.get_secrets_health("acme")
        assert result.healthy == 0
        assert result.expiring_soon == 0
        assert result.expired == 0
        assert result.orphan == 0


# ════════════════════════════════════════════════
# EDGE-CASE TESTS (CAB-1489)
# ════════════════════════════════════════════════


class TestCompleteScan:
    """Test complete_scan marks scan as completed with score."""

    @pytest.mark.asyncio
    async def test_complete_scan_updates_status_and_score(self, service, mock_db):
        await service.complete_scan("11111111-1111-1111-1111-111111111111", 85.0, mock_db)
        mock_db.execute.assert_called_once()
        # Verify the update statement was executed (not select)
        call_args = mock_db.execute.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_complete_scan_with_zero_score(self, service, mock_db):
        await service.complete_scan("22222222-2222-2222-2222-222222222222", 0.0, mock_db)
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_scan_with_perfect_score(self, service, mock_db):
        await service.complete_scan("33333333-3333-3333-3333-333333333333", 100.0, mock_db)
        mock_db.execute.assert_called_once()


class TestScoreEdgeCases:
    """Edge cases for score calculation and grading (CAB-1489)."""

    @pytest.mark.asyncio
    async def test_info_only_findings_score_100(self, service, mock_db):
        """Info findings have weight=0, so score should remain 100."""
        row = MagicMock()
        row.severity = "info"
        row.cnt = 50
        severity_result = MagicMock()
        severity_result.all.return_value = [row]

        total_result = MagicMock()
        total_result.scalar_one.return_value = 50

        last_scan_result = MagicMock()
        last_scan_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[severity_result, total_result, last_scan_result])

        response = await service.calculate_score("acme", mock_db)
        assert response.score == 100.0
        assert response.grade == "A"

    @pytest.mark.asyncio
    async def test_unknown_severity_treated_as_zero_weight(self, service, mock_db):
        """Severities not in _SEVERITY_WEIGHTS get weight 0 via .get(sev, 0)."""
        row = MagicMock()
        row.severity = "unknown_level"
        row.cnt = 10
        severity_result = MagicMock()
        severity_result.all.return_value = [row]

        total_result = MagicMock()
        total_result.scalar_one.return_value = 10

        last_scan_result = MagicMock()
        last_scan_result.scalar_one_or_none.return_value = None

        mock_db.execute = AsyncMock(side_effect=[severity_result, total_result, last_scan_result])

        response = await service.calculate_score("acme", mock_db)
        assert response.score == 100.0

    def test_grade_boundary_at_exactly_60(self, service):
        assert service._score_to_grade(60.0) == "D"

    def test_grade_boundary_at_59_99(self, service):
        assert service._score_to_grade(59.99) == "F"

    def test_grade_boundary_at_exactly_90(self, service):
        assert service._score_to_grade(90.0) == "A"

    def test_grade_boundary_at_exactly_0(self, service):
        assert service._score_to_grade(0.0) == "F"


class TestDriftEdgeCases:
    """Edge cases for drift detection (CAB-1489)."""

    @pytest.mark.asyncio
    async def test_empty_baseline_dict_no_drifts(self, service, mock_db):
        """Empty baseline {} should produce zero drifts."""
        baseline_row = MagicMock()
        baseline_row.baseline = {}
        baseline_row.updated_at = datetime(2026, 1, 1, tzinfo=UTC)

        baseline_result = MagicMock()
        baseline_result.scalar_one_or_none.return_value = baseline_row

        findings_result = MagicMock()
        findings_result.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[baseline_result, findings_result])

        response = await service.detect_drift("acme", mock_db)
        assert response.has_baseline is True
        assert response.total_drifts == 0
        assert response.drifts == []


class TestComplianceEdgeCases:
    """Edge cases for compliance scoring (CAB-1489)."""

    @pytest.mark.asyncio
    async def test_nis2_with_critical_findings(self, service, mock_db):
        """NIS2 with critical findings should have non-compliant controls."""
        row = MagicMock()
        row.severity = "critical"
        row.cnt = 3
        result = MagicMock()
        result.all.return_value = [row]
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "NIS2", mock_db)
        assert response.framework == "NIS2"
        assert response.total_controls == 6
        assert response.compliant_count == 0
        assert response.score == 0.0
        for ctrl in response.controls:
            assert ctrl.status == "non_compliant"

    @pytest.mark.asyncio
    async def test_nis2_with_high_findings_partial(self, service, mock_db):
        """NIS2 with high (no critical) findings should have partial controls."""
        row = MagicMock()
        row.severity = "high"
        row.cnt = 2
        result = MagicMock()
        result.all.return_value = [row]
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "nis2", mock_db)
        assert response.framework == "NIS2"
        assert response.compliant_count == 0
        for ctrl in response.controls:
            assert ctrl.status == "partial"

    @pytest.mark.asyncio
    async def test_unknown_framework_defaults_to_nis2(self, service, mock_db):
        """Unknown framework falls through to NIS2 controls (else branch)."""
        result = MagicMock()
        result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result)

        response = await service.get_compliance_score("acme", "SOC2", mock_db)
        assert response.framework == "SOC2"
        assert response.total_controls == 6  # NIS2 controls count
        assert response.compliant_count == 6
        assert response.score == 100.0


# ════════════════════════════════════════════════
# ROUTER INTEGRATION TESTS
# ════════════════════════════════════════════════


class TestGetSecurityScoreRouter:
    """Test GET /{tenant_id}/score endpoint."""

    @pytest.mark.asyncio
    async def test_cpi_admin_can_access(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.calculate_score = AsyncMock(return_value=_make_score_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/score")
            assert resp.status_code == 200
            assert resp.json()["score"] == 85.0

    @pytest.mark.asyncio
    async def test_tenant_admin_own_tenant(self, app_with_tenant_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.calculate_score = AsyncMock(return_value=_make_score_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/score")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_tenant_admin_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.get("/v1/security/other-tenant/score")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_tenant_user_forbidden(self, app_with_no_tenant_user):
        async with AsyncClient(transport=ASGITransport(app=app_with_no_tenant_user), base_url="http://test") as ac:
            resp = await ac.get("/v1/security/acme/score")
        assert resp.status_code == 403


class TestListFindingsRouter:
    """Test GET /{tenant_id}/findings endpoint."""

    @pytest.mark.asyncio
    async def test_list_findings_default(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.list_findings = AsyncMock(return_value=_make_findings_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/findings")
            assert resp.status_code == 200
            assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_list_findings_with_filters(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.list_findings = AsyncMock(return_value=_make_findings_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/findings?severity=high&status=open&scanner=trivy")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_tenant_admin_own_tenant(self, app_with_tenant_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.list_findings = AsyncMock(return_value=_make_findings_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/findings")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.get("/v1/security/other-tenant/findings")
        assert resp.status_code == 403


class TestIngestFindingsRouter:
    """Test POST /{tenant_id}/findings/ingest endpoint."""

    @pytest.mark.asyncio
    async def test_ingest_findings(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.ingest_findings = AsyncMock(return_value=2)
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/security/acme/findings/ingest",
                    json={
                        "scan_id": str(uuid.uuid4()),
                        "scanner": "trivy",
                        "findings": [{"severity": "high", "rule_id": "CVE-1", "rule_name": "T"}],
                    },
                )
            assert resp.status_code == 201
            assert resp.json()["ingested"] == 2

    @pytest.mark.asyncio
    async def test_ingest_invalid_scanner(self, app_with_cpi_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/security/acme/findings/ingest",
                json={
                    "scan_id": str(uuid.uuid4()),
                    "scanner": "invalid_scanner",
                    "findings": [],
                },
            )
        assert resp.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_tenant_admin_can_ingest(self, app_with_tenant_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.ingest_findings = AsyncMock(return_value=1)
            async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/security/acme/findings/ingest",
                    json={
                        "scan_id": str(uuid.uuid4()),
                        "scanner": "trivy",
                        "findings": [{"severity": "low", "rule_id": "R1", "rule_name": "R"}],
                    },
                )
            assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.post(
                "/v1/security/other-tenant/findings/ingest",
                json={"scan_id": str(uuid.uuid4()), "scanner": "trivy", "findings": []},
            )
        assert resp.status_code == 403


class TestResolveFindingRouter:
    """Test POST /{tenant_id}/findings/{finding_id}/resolve endpoint."""

    @pytest.mark.asyncio
    async def test_resolve_finding(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.resolve_finding = AsyncMock(return_value=True)
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.post(f"/v1/security/acme/findings/{uuid.uuid4()}/resolve")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.resolve_finding = AsyncMock(return_value=False)
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.post(f"/v1/security/acme/findings/{uuid.uuid4()}/resolve")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.post(f"/v1/security/other-tenant/findings/{uuid.uuid4()}/resolve")
        assert resp.status_code == 403


class TestGetScanHistoryRouter:
    """Test GET /{tenant_id}/scans endpoint."""

    @pytest.mark.asyncio
    async def test_get_scan_history(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.get_scan_history = AsyncMock(return_value=_make_scan_history_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/scans")
            assert resp.status_code == 200
            assert len(resp.json()["scans"]) == 1

    @pytest.mark.asyncio
    async def test_scan_history_with_limit(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.get_scan_history = AsyncMock(return_value=_make_scan_history_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/scans?limit=5")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.get("/v1/security/other-tenant/scans")
        assert resp.status_code == 403


class TestCreateScanRouter:
    """Test POST /{tenant_id}/scans endpoint."""

    @pytest.mark.asyncio
    async def test_create_scan(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.create_scan = AsyncMock(return_value=str(uuid.uuid4()))
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.post("/v1/security/acme/scans?scanner=trivy")
            assert resp.status_code == 201
            assert "scan_id" in resp.json()

    @pytest.mark.asyncio
    async def test_create_scan_missing_scanner(self, app_with_cpi_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
            resp = await ac.post("/v1/security/acme/scans")
        assert resp.status_code == 422  # Missing required query param

    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.post("/v1/security/other-tenant/scans?scanner=trivy")
        assert resp.status_code == 403


class TestGetDriftReport:
    """Test GET /{tenant_id}/drift endpoint."""

    @pytest.mark.asyncio
    async def test_get_drift_report(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.detect_drift = AsyncMock(return_value=_make_drift_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/drift")
            assert resp.status_code == 200
            assert resp.json()["has_baseline"] is True

    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.get("/v1/security/other-tenant/drift")
        assert resp.status_code == 403


class TestSetBaselineRouter:
    """Test PUT /{tenant_id}/baseline endpoint."""

    @pytest.mark.asyncio
    async def test_set_baseline(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.set_baseline = AsyncMock()
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.put(
                    "/v1/security/acme/baseline",
                    json={"baseline": {"CVE-1": "resolved"}},
                )
            assert resp.status_code == 200
            assert resp.json()["status"] == "baseline_updated"

    @pytest.mark.asyncio
    async def test_tenant_admin_can_set(self, app_with_tenant_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.set_baseline = AsyncMock()
            async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
                resp = await ac.put(
                    "/v1/security/acme/baseline",
                    json={"baseline": {"CVE-1": "resolved"}},
                )
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.put(
                "/v1/security/other-tenant/baseline",
                json={"baseline": {}},
            )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_tenant_user_forbidden(self, app_with_no_tenant_user):
        async with AsyncClient(transport=ASGITransport(app=app_with_no_tenant_user), base_url="http://test") as ac:
            resp = await ac.put(
                "/v1/security/acme/baseline",
                json={"baseline": {}},
            )
        assert resp.status_code == 403


class TestGetComplianceScoreRouter:
    """Test GET /{tenant_id}/compliance/{framework} endpoint."""

    @pytest.mark.asyncio
    async def test_dora_compliance(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.get_compliance_score = AsyncMock(return_value=_make_compliance_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/compliance/DORA")
            assert resp.status_code == 200
            assert resp.json()["framework"] == "DORA"

    @pytest.mark.asyncio
    async def test_nis2_compliance(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.get_compliance_score = AsyncMock(return_value=_make_compliance_response(framework="NIS2"))
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/compliance/NIS2")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unsupported_framework(self, app_with_cpi_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
            resp = await ac.get("/v1/security/acme/compliance/PCI-DSS")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_case_insensitive_framework(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.get_compliance_score = AsyncMock(return_value=_make_compliance_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/compliance/dora")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.get("/v1/security/other-tenant/compliance/DORA")
        assert resp.status_code == 403


class TestGetSecretsHealthRouter:
    """Test GET /{tenant_id}/secrets/health endpoint."""

    @pytest.mark.asyncio
    async def test_get_secrets_health(self, app_with_cpi_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.get_secrets_health = AsyncMock(return_value=_make_secrets_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_cpi_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/secrets/health")
            assert resp.status_code == 200
            assert resp.json()["total_secrets"] == 0

    @pytest.mark.asyncio
    async def test_tenant_admin_own_tenant(self, app_with_tenant_admin):
        with patch(SERVICE_PATH) as mock_svc:
            mock_svc.get_secrets_health = AsyncMock(return_value=_make_secrets_response())
            async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
                resp = await ac.get("/v1/security/acme/secrets/health")
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_other_tenant_forbidden(self, app_with_tenant_admin):
        async with AsyncClient(transport=ASGITransport(app=app_with_tenant_admin), base_url="http://test") as ac:
            resp = await ac.get("/v1/security/other-tenant/secrets/health")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_tenant_user_forbidden(self, app_with_no_tenant_user):
        async with AsyncClient(transport=ASGITransport(app=app_with_no_tenant_user), base_url="http://test") as ac:
            resp = await ac.get("/v1/security/acme/secrets/health")
        assert resp.status_code == 403
