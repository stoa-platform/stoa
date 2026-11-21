"""L3-04: Error rate trend detection.

Tracks per-CUJ error rates and detects improving/degrading/stable trends
by comparing the last 20 runs vs the previous 20 runs.

Trend thresholds:
    delta > +5pp  → degrading
    delta < -5pp  → improving
    else          → stable
"""

from __future__ import annotations

import pytest

from scoring.l3_analyzer import analyze_stability, L3Result

pytestmark = [pytest.mark.l3]


class TestErrorRate:
    """L3-04: Per-CUJ error rate computation."""

    def test_zero_errors(self):
        """All PASS → 0% error rate per CUJ."""
        history = [
            {"demo_ready": True, "cujs": {
                "CUJ-01": {"status": "PASS", "e2e_ms": 500},
                "CUJ-02": {"status": "PASS", "e2e_ms": 1000},
            }}
        ] * 20
        result = analyze_stability(history)
        assert result.error_rates.get("CUJ-01", 0) == 0
        assert result.error_rates.get("CUJ-02", 0) == 0

    def test_partial_errors(self):
        """50% failure rate should be captured."""
        history = []
        for i in range(20):
            status = "PASS" if i % 2 == 0 else "FAIL"
            history.append({
                "demo_ready": status == "PASS",
                "cujs": {"CUJ-01": {"status": status, "e2e_ms": 500}},
            })
        result = analyze_stability(history)
        assert result.error_rates["CUJ-01"] == 50.0

    def test_multiple_cujs_independent_rates(self):
        """Each CUJ computes its error rate independently."""
        history = []
        for i in range(20):
            history.append({
                "demo_ready": True,
                "cujs": {
                    "CUJ-01": {"status": "PASS", "e2e_ms": 500},
                    "CUJ-02": {"status": "PASS" if i >= 4 else "FAIL", "e2e_ms": 500},
                },
            })
        result = analyze_stability(history)
        assert result.error_rates["CUJ-01"] == 0.0
        assert result.error_rates["CUJ-02"] == 20.0


class TestErrorTrend:
    """L3-04: Error rate trend detection (improving/degrading/stable)."""

    def test_stable_when_insufficient_history(self):
        """< 40 entries → trend defaults to stable."""
        history = [
            {"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 500}}}
        ] * 30
        result = analyze_stability(history)
        assert result.error_trend == "stable"

    def test_degrading_trend(self):
        """Previous 20: 0% errors → Recent 20: 30% errors = degrading."""
        previous = [
            {"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 500}}}
        ] * 20
        recent = []
        for i in range(20):
            status = "PASS" if i % 3 != 0 else "FAIL"  # ~33% error
            recent.append({
                "demo_ready": status == "PASS",
                "cujs": {"CUJ-01": {"status": status, "e2e_ms": 500}},
            })
        result = analyze_stability(previous + recent)
        assert result.error_trend == "degrading"

    def test_improving_trend(self):
        """Previous 20: 30% errors → Recent 20: 0% errors = improving."""
        previous = []
        for i in range(20):
            status = "PASS" if i % 3 != 0 else "FAIL"
            previous.append({
                "demo_ready": status == "PASS",
                "cujs": {"CUJ-01": {"status": status, "e2e_ms": 500}},
            })
        recent = [
            {"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 500}}}
        ] * 20
        result = analyze_stability(previous + recent)
        assert result.error_trend == "improving"

    def test_stable_when_delta_under_5pp(self):
        """Small delta (< 5pp) → stable, not flagged."""
        # Previous: 10% error, recent: 12% error → delta = 2pp < 5pp
        previous = []
        for i in range(20):
            status = "FAIL" if i < 2 else "PASS"  # 10% error
            previous.append({
                "demo_ready": status == "PASS",
                "cujs": {"CUJ-01": {"status": status, "e2e_ms": 500}},
            })
        recent = []
        for i in range(20):
            status = "FAIL" if i < 3 else "PASS"  # 15% error
            recent.append({
                "demo_ready": status == "PASS",
                "cujs": {"CUJ-01": {"status": status, "e2e_ms": 500}},
            })
        result = analyze_stability(previous + recent)
        assert result.error_trend == "stable"

    def test_empty_history_no_crash(self):
        """Empty history should not crash error rate computation."""
        result = analyze_stability([])
        assert result.error_rates == {}
        assert result.error_trend == "stable"
