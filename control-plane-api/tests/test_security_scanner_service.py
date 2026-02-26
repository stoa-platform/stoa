"""Tests for SecurityScannerService (CAB-1528).

Covers: calculate_score, list_findings, ingest_findings, resolve_finding,
create_scan, complete_scan, get_scan_history, set_baseline, detect_drift,
get_compliance_score, get_secrets_health, _score_to_grade.
"""
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.security_scanner_service import SecurityScannerService


@pytest.fixture
def svc():
    return SecurityScannerService()


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


def _score_mocks(severity_rows, total, scans=None):
    """Build 3 mock results for calculate_score's 3 DB queries."""
    sev = MagicMock()
    sev.all.return_value = severity_rows
    tot = MagicMock()
    tot.scalar_one.return_value = total
    sc = MagicMock()
    sc.all.return_value = scans or []
    return [sev, tot, sc]


def _count_and_rows(count, rows):
    """Build 2 mock results: count query + rows query."""
    cnt = MagicMock()
    cnt.scalar_one.return_value = count
    r = MagicMock()
    r.scalars.return_value.all.return_value = rows
    return [cnt, r]


class TestScoreToGrade:
    @pytest.mark.parametrize("score,grade", [
        (95, "A"), (90, "A"), (89.9, "B"), (80, "B"),
        (79.9, "C"), (70, "C"), (69.9, "D"), (60, "D"),
        (59.9, "F"), (0, "F"),
    ])
    def test_all_grades(self, score, grade):
        assert SecurityScannerService._score_to_grade(score) == grade


class TestCalculateScore:
    @pytest.mark.asyncio
    async def test_no_findings(self, svc, mock_db):
        mock_db.execute = AsyncMock(side_effect=_score_mocks([], 0))
        result = await svc.calculate_score("t1", mock_db)
        assert result.score == 100.0
        assert result.grade == "A"
        assert result.open_findings == 0
        assert result.trend is None

    @pytest.mark.asyncio
    async def test_critical_findings(self, svc, mock_db):
        mock_db.execute = AsyncMock(
            side_effect=_score_mocks([MagicMock(severity="critical", cnt=3)], 3)
        )
        result = await svc.calculate_score("t1", mock_db)
        assert result.score == 70.0
        assert result.grade == "C"

    @pytest.mark.asyncio
    async def test_mixed_severities(self, svc, mock_db):
        rows = [
            MagicMock(severity="critical", cnt=1),
            MagicMock(severity="high", cnt=2),
            MagicMock(severity="medium", cnt=3),
            MagicMock(severity="low", cnt=4),
            MagicMock(severity="info", cnt=5),
        ]
        mock_db.execute = AsyncMock(side_effect=_score_mocks(rows, 15))
        result = await svc.calculate_score("t1", mock_db)
        assert result.score == 72.0  # 100 - (10+10+6+2+0)

    @pytest.mark.asyncio
    async def test_score_floor_at_zero(self, svc, mock_db):
        mock_db.execute = AsyncMock(
            side_effect=_score_mocks([MagicMock(severity="critical", cnt=20)], 20)
        )
        assert (await svc.calculate_score("t1", mock_db)).score == 0.0

    @pytest.mark.asyncio
    async def test_trend(self, svc, mock_db):
        prev = MagicMock(completed_at=datetime(2026, 1, 1, tzinfo=UTC), score=85.0)
        curr = MagicMock(completed_at=datetime(2026, 1, 15, tzinfo=UTC), score=90.0)
        mock_db.execute = AsyncMock(side_effect=_score_mocks([], 0, [curr, prev]))
        assert (await svc.calculate_score("t1", mock_db)).trend == 15.0


class TestListFindings:
    @pytest.mark.asyncio
    async def test_empty(self, svc, mock_db):
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(0, []))
        result = await svc.list_findings("t1", mock_db)
        assert result.total == 0 and result.has_more is False

    @pytest.mark.asyncio
    async def test_with_results(self, svc, mock_db):
        f = MagicMock(
            id=uuid.uuid4(), tenant_id="t1", scan_id=uuid.uuid4(), scanner="trivy",
            severity="high", rule_id="CVE-1", rule_name="Vuln", resource_type="container",
            resource_name="nginx", description="d", remediation="u", status="open",
            created_at=datetime.now(UTC), resolved_at=None,
        )
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(1, [f]))
        result = await svc.list_findings("t1", mock_db)
        assert len(result.findings) == 1

    @pytest.mark.asyncio
    async def test_pagination(self, svc, mock_db):
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(100, []))
        result = await svc.list_findings("t1", mock_db, page=1, page_size=50)
        assert result.has_more is True


class TestIngestFindings:
    @pytest.mark.asyncio
    async def test_ingest_multiple(self, svc, mock_db):
        sid = str(uuid.uuid4())
        raw = [{"severity": "high", "rule_id": "R1", "title": "T1"}, {"rule_id": "R2"}]
        assert await svc.ingest_findings("t1", sid, "trivy", raw, mock_db) == 2
        assert mock_db.add.call_count == 2

    @pytest.mark.asyncio
    async def test_ingest_empty(self, svc, mock_db):
        assert await svc.ingest_findings("t1", str(uuid.uuid4()), "trivy", [], mock_db) == 0


class TestResolveFinding:
    @pytest.mark.asyncio
    async def test_success(self, svc, mock_db):
        mock_db.execute = AsyncMock(return_value=MagicMock(rowcount=1))
        assert await svc.resolve_finding(str(uuid.uuid4()), mock_db) is True

    @pytest.mark.asyncio
    async def test_not_found(self, svc, mock_db):
        mock_db.execute = AsyncMock(return_value=MagicMock(rowcount=0))
        assert await svc.resolve_finding(str(uuid.uuid4()), mock_db) is False


class TestScanManagement:
    @pytest.mark.asyncio
    async def test_create_scan(self, svc, mock_db):
        assert await svc.create_scan("t1", "trivy", mock_db) is not None
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_scan(self, svc, mock_db):
        await svc.complete_scan(str(uuid.uuid4()), 85.0, mock_db)
        mock_db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_scan_history(self, svc, mock_db):
        s = MagicMock(
            id=uuid.uuid4(), tenant_id="t1", scanner="trivy", status="completed",
            findings_count=5, score=90.0, started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        scans_r = MagicMock()
        scans_r.scalars.return_value.all.return_value = [s]
        cnt_r = MagicMock()
        cnt_r.scalar_one.return_value = 1
        mock_db.execute = AsyncMock(side_effect=[scans_r, cnt_r])
        assert (await svc.get_scan_history("t1", mock_db)).total == 1


class TestDriftDetection:
    @pytest.mark.asyncio
    async def test_set_baseline_new(self, svc, mock_db):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=r)
        await svc.set_baseline("t1", {"R1": "resolved"}, mock_db)
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_baseline_update(self, svc, mock_db):
        existing = MagicMock(baseline={"R1": "open"})
        r = MagicMock()
        r.scalar_one_or_none.return_value = existing
        mock_db.execute = AsyncMock(return_value=r)
        await svc.set_baseline("t1", {"R1": "resolved"}, mock_db)
        assert existing.baseline == {"R1": "resolved"}

    @pytest.mark.asyncio
    async def test_no_baseline(self, svc, mock_db):
        r = MagicMock()
        r.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=r)
        drift = await svc.detect_drift("t1", mock_db)
        assert drift.has_baseline is False

    @pytest.mark.asyncio
    async def test_with_regression(self, svc, mock_db):
        bl = MagicMock(
            baseline={"R1": "resolved", "R2": "resolved"},
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_at=datetime(2025, 12, 1, tzinfo=UTC),
        )
        bl_r = MagicMock()
        bl_r.scalar_one_or_none.return_value = bl
        fr = MagicMock()
        fr.all.return_value = [MagicMock(rule_id="R1", title="Rule 1", severity="high")]
        mock_db.execute = AsyncMock(side_effect=[bl_r, fr])
        drift = await svc.detect_drift("t1", mock_db)
        assert drift.total_drifts == 1
        assert drift.drifts[0].rule_id == "R1"

    @pytest.mark.asyncio
    async def test_no_regression(self, svc, mock_db):
        bl = MagicMock(
            baseline={"R1": "resolved"},
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_at=datetime(2025, 12, 1, tzinfo=UTC),
        )
        bl_r = MagicMock()
        bl_r.scalar_one_or_none.return_value = bl
        fr = MagicMock()
        fr.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[bl_r, fr])
        assert (await svc.detect_drift("t1", mock_db)).total_drifts == 0


class TestComplianceScore:
    @pytest.mark.asyncio
    async def test_dora_clean(self, svc, mock_db):
        r = MagicMock()
        r.all.return_value = []
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "DORA", mock_db)
        assert resp.score == 100.0 and resp.total_controls == 7

    @pytest.mark.asyncio
    async def test_dora_critical(self, svc, mock_db):
        r = MagicMock()
        r.all.return_value = [MagicMock(severity="critical", cnt=2)]
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "DORA", mock_db)
        assert resp.score == 0.0
        assert all(c.status == "non_compliant" for c in resp.controls)

    @pytest.mark.asyncio
    async def test_dora_high_only(self, svc, mock_db):
        r = MagicMock()
        r.all.return_value = [MagicMock(severity="high", cnt=1)]
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "DORA", mock_db)
        assert all(c.status == "partial" for c in resp.controls)

    @pytest.mark.asyncio
    async def test_nis2(self, svc, mock_db):
        r = MagicMock()
        r.all.return_value = []
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "nis2", mock_db)
        assert resp.total_controls == 6


class TestSecretsHealth:
    @pytest.mark.asyncio
    async def test_returns_empty(self, svc):
        result = await svc.get_secrets_health("t1")
        assert result.total_secrets == 0 and result.secrets == []
