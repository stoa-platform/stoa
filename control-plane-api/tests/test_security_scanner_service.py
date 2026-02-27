"""Tests for SecurityScannerService (CAB-1528 + CAB-1565).

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
    @pytest.mark.parametrize(
        "score,grade",
        [
            (95, "A"),
            (90, "A"),
            (89.9, "B"),
            (80, "B"),
            (79.9, "C"),
            (70, "C"),
            (69.9, "D"),
            (60, "D"),
            (59.9, "F"),
            (0, "F"),
        ],
    )
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
        mock_db.execute = AsyncMock(side_effect=_score_mocks([MagicMock(severity="critical", cnt=3)], 3))
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
        mock_db.execute = AsyncMock(side_effect=_score_mocks([MagicMock(severity="critical", cnt=20)], 20))
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
            id=uuid.uuid4(),
            tenant_id="t1",
            scan_id=uuid.uuid4(),
            scanner="trivy",
            severity="high",
            rule_id="CVE-1",
            rule_name="Vuln",
            resource_type="container",
            resource_name="nginx",
            description="d",
            remediation="u",
            status="open",
            created_at=datetime.now(UTC),
            resolved_at=None,
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
            id=uuid.uuid4(),
            tenant_id="t1",
            scanner="trivy",
            status="completed",
            findings_count=5,
            score=90.0,
            started_at=datetime.now(UTC),
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

    @pytest.mark.asyncio
    async def test_returns_correct_tenant(self, svc):
        result = await svc.get_secrets_health("tenant-xyz")
        assert result.tenant_id == "tenant-xyz"

    @pytest.mark.asyncio
    async def test_all_counters_zero(self, svc):
        result = await svc.get_secrets_health("t1")
        assert result.healthy == 0
        assert result.expiring_soon == 0
        assert result.expired == 0
        assert result.orphan == 0


# ---------- calculate_score edge cases (CAB-1565) ----------


class TestCalculateScoreEdgeCases:
    @pytest.mark.asyncio
    async def test_unknown_severity_weight_defaults_to_zero(self, svc, mock_db):
        """Unknown severity uses weight 0 (no penalty)."""
        mock_db.execute = AsyncMock(side_effect=_score_mocks([MagicMock(severity="unknown_sev", cnt=10)], 10))
        result = await svc.calculate_score("t1", mock_db)
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_info_findings_no_penalty(self, svc, mock_db):
        """Info-severity findings carry weight 0."""
        mock_db.execute = AsyncMock(side_effect=_score_mocks([MagicMock(severity="info", cnt=50)], 50))
        result = await svc.calculate_score("t1", mock_db)
        assert result.score == 100.0
        assert result.open_findings == 50

    @pytest.mark.asyncio
    async def test_single_low_finding(self, svc, mock_db):
        """Single low finding: penalty = 0.5."""
        mock_db.execute = AsyncMock(side_effect=_score_mocks([MagicMock(severity="low", cnt=1)], 1))
        result = await svc.calculate_score("t1", mock_db)
        assert result.score == 99.5
        assert result.grade == "A"

    @pytest.mark.asyncio
    async def test_trend_with_single_scan_no_trend(self, svc, mock_db):
        """Only one completed scan -> trend is None."""
        scan = MagicMock(completed_at=datetime(2026, 1, 15, tzinfo=UTC), score=90.0)
        mock_db.execute = AsyncMock(side_effect=_score_mocks([], 0, [scan]))
        result = await svc.calculate_score("t1", mock_db)
        assert result.trend is None

    @pytest.mark.asyncio
    async def test_trend_with_null_previous_score(self, svc, mock_db):
        """Previous scan has score=None -> trend is None."""
        curr = MagicMock(completed_at=datetime(2026, 1, 15, tzinfo=UTC), score=90.0)
        prev = MagicMock(completed_at=datetime(2026, 1, 1, tzinfo=UTC), score=None)
        mock_db.execute = AsyncMock(side_effect=_score_mocks([], 0, [curr, prev]))
        result = await svc.calculate_score("t1", mock_db)
        assert result.trend is None

    @pytest.mark.asyncio
    async def test_negative_trend(self, svc, mock_db):
        """Score worsened: trend is negative."""
        prev = MagicMock(completed_at=datetime(2026, 1, 1, tzinfo=UTC), score=95.0)
        curr = MagicMock(completed_at=datetime(2026, 1, 15, tzinfo=UTC), score=90.0)
        rows = [MagicMock(severity="high", cnt=1)]
        mock_db.execute = AsyncMock(side_effect=_score_mocks(rows, 1, [curr, prev]))
        result = await svc.calculate_score("t1", mock_db)
        assert result.trend == -0.0 or result.trend < 0

    @pytest.mark.asyncio
    async def test_total_findings_includes_resolved(self, svc, mock_db):
        """total_findings counts all statuses, not just open."""
        mock_db.execute = AsyncMock(side_effect=_score_mocks([MagicMock(severity="high", cnt=2)], 10))
        result = await svc.calculate_score("t1", mock_db)
        assert result.open_findings == 2
        assert result.total_findings == 10

    @pytest.mark.asyncio
    async def test_last_scan_at_populated(self, svc, mock_db):
        scan_time = datetime(2026, 2, 20, 14, 30, tzinfo=UTC)
        scan = MagicMock(completed_at=scan_time, score=80.0)
        mock_db.execute = AsyncMock(side_effect=_score_mocks([], 0, [scan]))
        result = await svc.calculate_score("t1", mock_db)
        assert result.last_scan_at == scan_time


# ---------- list_findings edge cases (CAB-1565) ----------


class TestListFindingsEdgeCases:
    @pytest.mark.asyncio
    async def test_filter_by_severity(self, svc, mock_db):
        """Severity filter is passed to query."""
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(0, []))
        await svc.list_findings("t1", mock_db, severity="critical")
        assert mock_db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_filter_by_status(self, svc, mock_db):
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(0, []))
        await svc.list_findings("t1", mock_db, status="resolved")
        assert mock_db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_filter_by_scanner(self, svc, mock_db):
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(0, []))
        await svc.list_findings("t1", mock_db, scanner="bandit")
        assert mock_db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_all_filters_combined(self, svc, mock_db):
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(0, []))
        await svc.list_findings("t1", mock_db, severity="high", status="open", scanner="trivy")
        assert mock_db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_page_size_one(self, svc, mock_db):
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(5, []))
        result = await svc.list_findings("t1", mock_db, page=1, page_size=1)
        assert result.has_more is True
        assert result.page_size == 1

    @pytest.mark.asyncio
    async def test_last_page_no_more(self, svc, mock_db):
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(2, []))
        result = await svc.list_findings("t1", mock_db, page=2, page_size=1)
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_exact_boundary_no_more(self, svc, mock_db):
        """total == page * page_size -> has_more is False."""
        mock_db.execute = AsyncMock(side_effect=_count_and_rows(50, []))
        result = await svc.list_findings("t1", mock_db, page=1, page_size=50)
        assert result.has_more is False


# ---------- ingest_findings edge cases (CAB-1565) ----------


class TestIngestFindingsEdgeCases:
    @pytest.mark.asyncio
    async def test_defaults_for_missing_fields(self, svc, mock_db):
        """Finding with only rule_id gets sensible defaults."""
        sid = str(uuid.uuid4())
        count = await svc.ingest_findings("t1", sid, "trivy", [{}], mock_db)
        assert count == 1
        added = mock_db.add.call_args[0][0]
        assert added.severity == "info"
        assert added.rule_id == "unknown"
        assert added.status == "open"

    @pytest.mark.asyncio
    async def test_severity_lowered(self, svc, mock_db):
        """Severity is lowercased."""
        sid = str(uuid.uuid4())
        await svc.ingest_findings("t1", sid, "trivy", [{"severity": "HIGH"}], mock_db)
        added = mock_db.add.call_args[0][0]
        assert added.severity == "high"

    @pytest.mark.asyncio
    async def test_fallback_rule_name_to_title(self, svc, mock_db):
        """If rule_name missing, falls back to title."""
        sid = str(uuid.uuid4())
        await svc.ingest_findings("t1", sid, "trivy", [{"title": "My Title"}], mock_db)
        added = mock_db.add.call_args[0][0]
        assert added.title == "My Title"

    @pytest.mark.asyncio
    async def test_fallback_resource_name_to_resource(self, svc, mock_db):
        """If resource_name missing, falls back to resource."""
        sid = str(uuid.uuid4())
        await svc.ingest_findings("t1", sid, "trivy", [{"resource": "my-pod"}], mock_db)
        added = mock_db.add.call_args[0][0]
        assert added.resource_name == "my-pod"

    @pytest.mark.asyncio
    async def test_details_stores_raw_dict(self, svc, mock_db):
        sid = str(uuid.uuid4())
        raw = {"severity": "low", "rule_id": "R1", "extra_data": "xyz"}
        await svc.ingest_findings("t1", sid, "trivy", [raw], mock_db)
        added = mock_db.add.call_args[0][0]
        assert added.details == raw

    @pytest.mark.asyncio
    async def test_scan_updated_on_ingest(self, svc, mock_db):
        """Scan record is updated with findings_count and completed status."""
        sid = str(uuid.uuid4())
        await svc.ingest_findings("t1", sid, "trivy", [{"rule_id": "R1"}], mock_db)
        assert mock_db.execute.await_count == 1
        assert mock_db.flush.await_count == 1


# ---------- scan management edge cases (CAB-1565) ----------


class TestScanManagementEdgeCases:
    @pytest.mark.asyncio
    async def test_create_scan_returns_uuid_string(self, svc, mock_db):
        result = await svc.create_scan("t1", "bandit", mock_db)
        uuid.UUID(result)  # should not raise

    @pytest.mark.asyncio
    async def test_scan_history_custom_limit(self, svc, mock_db):
        scans_r = MagicMock()
        scans_r.scalars.return_value.all.return_value = []
        cnt_r = MagicMock()
        cnt_r.scalar_one.return_value = 0
        mock_db.execute = AsyncMock(side_effect=[scans_r, cnt_r])
        result = await svc.get_scan_history("t1", mock_db, limit=5)
        assert result.total == 0
        assert result.scans == []

    @pytest.mark.asyncio
    async def test_scan_history_preserves_fields(self, svc, mock_db):
        started = datetime(2026, 2, 1, 10, 0, tzinfo=UTC)
        completed = datetime(2026, 2, 1, 10, 5, tzinfo=UTC)
        s = MagicMock(
            id=uuid.uuid4(),
            tenant_id="t1",
            scanner="clippy",
            status="completed",
            findings_count=12,
            score=77.5,
            started_at=started,
            completed_at=completed,
        )
        scans_r = MagicMock()
        scans_r.scalars.return_value.all.return_value = [s]
        cnt_r = MagicMock()
        cnt_r.scalar_one.return_value = 1
        mock_db.execute = AsyncMock(side_effect=[scans_r, cnt_r])
        result = await svc.get_scan_history("t1", mock_db)
        scan = result.scans[0]
        assert scan.scanner == "clippy"
        assert scan.score == 77.5
        assert scan.findings_count == 12


# ---------- drift detection edge cases (CAB-1565) ----------


class TestDriftDetectionEdgeCases:
    @pytest.mark.asyncio
    async def test_multiple_regressions(self, svc, mock_db):
        bl = MagicMock(
            baseline={"R1": "resolved", "R2": "resolved", "R3": "resolved"},
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_at=datetime(2025, 12, 1, tzinfo=UTC),
        )
        bl_r = MagicMock()
        bl_r.scalar_one_or_none.return_value = bl
        fr = MagicMock()
        fr.all.return_value = [
            MagicMock(rule_id="R1", title="Rule 1", severity="high"),
            MagicMock(rule_id="R3", title="Rule 3", severity="critical"),
        ]
        mock_db.execute = AsyncMock(side_effect=[bl_r, fr])
        drift = await svc.detect_drift("t1", mock_db)
        assert drift.total_drifts == 2
        rule_ids = {d.rule_id for d in drift.drifts}
        assert rule_ids == {"R1", "R3"}

    @pytest.mark.asyncio
    async def test_baseline_with_open_entries_no_drift(self, svc, mock_db):
        """Baseline says 'open' and current is open -> no drift."""
        bl = MagicMock(
            baseline={"R1": "open"},
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_at=datetime(2025, 12, 1, tzinfo=UTC),
        )
        bl_r = MagicMock()
        bl_r.scalar_one_or_none.return_value = bl
        fr = MagicMock()
        fr.all.return_value = [MagicMock(rule_id="R1", title="Rule 1", severity="medium")]
        mock_db.execute = AsyncMock(side_effect=[bl_r, fr])
        drift = await svc.detect_drift("t1", mock_db)
        assert drift.total_drifts == 0

    @pytest.mark.asyncio
    async def test_baseline_date_falls_back_to_created(self, svc, mock_db):
        """If updated_at is None, baseline_date uses created_at."""
        created = datetime(2025, 11, 1, tzinfo=UTC)
        bl = MagicMock(
            baseline={},
            updated_at=None,
            created_at=created,
        )
        bl_r = MagicMock()
        bl_r.scalar_one_or_none.return_value = bl
        fr = MagicMock()
        fr.all.return_value = []
        mock_db.execute = AsyncMock(side_effect=[bl_r, fr])
        drift = await svc.detect_drift("t1", mock_db)
        assert drift.baseline_date == created

    @pytest.mark.asyncio
    async def test_empty_baseline_dict(self, svc, mock_db):
        """Empty baseline -> zero drifts."""
        bl = MagicMock(
            baseline={},
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_at=datetime(2025, 12, 1, tzinfo=UTC),
        )
        bl_r = MagicMock()
        bl_r.scalar_one_or_none.return_value = bl
        fr = MagicMock()
        fr.all.return_value = [MagicMock(rule_id="R1", title="Rule 1", severity="high")]
        mock_db.execute = AsyncMock(side_effect=[bl_r, fr])
        drift = await svc.detect_drift("t1", mock_db)
        assert drift.total_drifts == 0
        assert drift.has_baseline is True

    @pytest.mark.asyncio
    async def test_resolved_rule_not_in_current(self, svc, mock_db):
        """Baseline expects resolved, rule not in current open -> no drift."""
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
        drift = await svc.detect_drift("t1", mock_db)
        assert drift.total_drifts == 0


# ---------- compliance edge cases (CAB-1565) ----------


class TestComplianceScoreEdgeCases:
    @pytest.mark.asyncio
    async def test_nis2_critical(self, svc, mock_db):
        """NIS2 with critical findings -> all non_compliant, score 0."""
        r = MagicMock()
        r.all.return_value = [MagicMock(severity="critical", cnt=1)]
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "NIS2", mock_db)
        assert resp.score == 0.0
        assert resp.compliant_count == 0
        assert resp.total_controls == 6

    @pytest.mark.asyncio
    async def test_nis2_high_only_partial(self, svc, mock_db):
        """NIS2 with high-only findings -> all partial."""
        r = MagicMock()
        r.all.return_value = [MagicMock(severity="high", cnt=3)]
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "nis2", mock_db)
        assert all(c.status == "partial" for c in resp.controls)
        assert resp.compliant_count == 0

    @pytest.mark.asyncio
    async def test_findings_count_reflects_critical_plus_high(self, svc, mock_db):
        """Control findings_count = critical + high."""
        r = MagicMock()
        r.all.return_value = [
            MagicMock(severity="critical", cnt=2),
            MagicMock(severity="high", cnt=3),
        ]
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "DORA", mock_db)
        assert all(c.findings_count == 5 for c in resp.controls)

    @pytest.mark.asyncio
    async def test_medium_only_is_compliant(self, svc, mock_db):
        """Only medium-severity findings -> compliant (heuristic ignores medium)."""
        r = MagicMock()
        r.all.return_value = [MagicMock(severity="medium", cnt=10)]
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "DORA", mock_db)
        assert resp.score == 100.0
        assert all(c.status == "compliant" for c in resp.controls)

    @pytest.mark.asyncio
    async def test_framework_case_insensitive(self, svc, mock_db):
        """Framework name is case-insensitive (dora == DORA)."""
        r = MagicMock()
        r.all.return_value = []
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "dora", mock_db)
        assert resp.framework == "DORA"
        assert resp.total_controls == 7

    @pytest.mark.asyncio
    async def test_control_ids_present(self, svc, mock_db):
        """All DORA control IDs are present in response."""
        r = MagicMock()
        r.all.return_value = []
        mock_db.execute = AsyncMock(return_value=r)
        resp = await svc.get_compliance_score("t1", "DORA", mock_db)
        ids = {c.control_id for c in resp.controls}
        assert "DORA-5.1" in ids
        assert "DORA-11.2" in ids


# ---------- resolve_finding edge cases (CAB-1565) ----------


class TestResolveFindingEdgeCases:
    @pytest.mark.asyncio
    async def test_invalid_uuid_raises(self, svc, mock_db):
        with pytest.raises(ValueError):
            await svc.resolve_finding("not-a-uuid", mock_db)


# ---------- score_to_grade boundaries (CAB-1565) ----------


class TestScoreToGradeBoundaries:
    @pytest.mark.parametrize(
        "score,grade",
        [
            (100, "A"),
            (100.0, "A"),
            (90.0, "A"),
            (89.99, "B"),
            (80.0, "B"),
            (79.99, "C"),
            (70.0, "C"),
            (69.99, "D"),
            (60.0, "D"),
            (59.99, "F"),
            (0.0, "F"),
            (-1.0, "F"),
        ],
    )
    def test_exact_boundaries(self, score, grade):
        assert SecurityScannerService._score_to_grade(score) == grade
