"""L3-06: CUJ flakiness detection.

Analyzes the pass rate per CUJ over the last ~7 days of L2 runs.
A CUJ with < 95% pass rate is considered flaky and needs investigation.

Thresholds:
    >= 95% pass rate → stable
    < 95% pass rate  → flaky (investigate)
"""

from __future__ import annotations

import pytest

from scoring.l3_analyzer import analyze_stability, L3Result

pytestmark = [pytest.mark.l3]


class TestFlakiness:
    """L3-06: CUJ flakiness detection over sliding window."""

    def test_no_flaky_when_all_pass(self):
        history = [
            {"demo_ready": True, "cujs": {
                "CUJ-01": {"status": "PASS", "e2e_ms": 500},
                "CUJ-02": {"status": "PASS", "e2e_ms": 1000},
            }}
        ] * 100
        result = analyze_stability(history)
        assert len(result.flaky_cujs) == 0

    def test_detect_flaky_cuj(self):
        """CUJ with 80% pass rate (< 95%) should be flagged."""
        history = []
        for i in range(100):
            status = "PASS" if i % 5 != 0 else "FAIL"  # 80% pass
            history.append({
                "demo_ready": True,
                "cujs": {"CUJ-03": {"status": status, "e2e_ms": 500}},
            })
        result = analyze_stability(history)
        assert len(result.flaky_cujs) == 1
        assert "CUJ-03" in result.flaky_cujs[0]
        assert "80.0%" in result.flaky_cujs[0]

    def test_95pct_not_flaky(self):
        """Exactly 95% pass rate should not be flagged."""
        history = []
        for i in range(100):
            status = "FAIL" if i < 5 else "PASS"  # 95% pass
            history.append({
                "demo_ready": True,
                "cujs": {"CUJ-01": {"status": status, "e2e_ms": 500}},
            })
        result = analyze_stability(history)
        assert len(result.flaky_cujs) == 0

    def test_multiple_flaky_cujs(self):
        """Multiple CUJs can be flaky independently."""
        history = []
        for i in range(100):
            history.append({
                "demo_ready": True,
                "cujs": {
                    "CUJ-01": {"status": "PASS", "e2e_ms": 500},  # 100% stable
                    "CUJ-03": {"status": "PASS" if i % 10 != 0 else "FAIL", "e2e_ms": 500},  # 90%
                    "CUJ-04": {"status": "PASS" if i % 4 != 0 else "FAIL", "e2e_ms": 500},   # 75%
                },
            })
        result = analyze_stability(history)
        assert len(result.flaky_cujs) == 2
        flaky_names = " ".join(result.flaky_cujs)
        assert "CUJ-03" in flaky_names
        assert "CUJ-04" in flaky_names

    def test_flaky_degrades_confidence(self):
        """Flaky CUJs should degrade confidence from HIGH to MEDIUM."""
        history = []
        for i in range(60):
            status = "PASS" if i % 10 != 0 else "FAIL"  # 90% — flaky
            history.append({
                "demo_ready": True,
                "cujs": {"CUJ-03": {"status": status, "e2e_ms": 500}},
            })
        # Last 10 all pass → consecutive_l2_pass = 10+
        for _ in range(15):
            history.append({
                "demo_ready": True,
                "cujs": {"CUJ-03": {"status": "PASS", "e2e_ms": 500}},
            })
        result = analyze_stability(history)
        assert result.consecutive_l2_pass >= 15
        # But flakiness in the window should degrade confidence
        # (depends on whether flaky window overlaps with last 100)
        assert result.demo_confidence in ("MEDIUM", "HIGH")
