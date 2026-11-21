"""L3-02/03: Latency and score regression detection.

Compares recent runs against a baseline window to detect:
- L3-02: Latency regression (p95 degradation > 15%)
- L3-03: Score regression (composite drop > 5 points)

Uses sliding windows: last 3 runs vs previous 10 runs.
"""

from __future__ import annotations

import pytest

from scoring.l3_analyzer import analyze_stability, L3Result

pytestmark = [pytest.mark.l3]


def _make_entry(e2e_ms: float, cuj_id: str = "CUJ-01", status: str = "PASS") -> dict:
    return {
        "demo_ready": status == "PASS",
        "cujs": {cuj_id: {"status": status, "e2e_ms": e2e_ms}},
    }


class TestLatencyRegression:
    """L3-02: Detect latency regression across CUJs."""

    def test_no_regression_stable_latency(self):
        """Stable latency should produce zero regressions."""
        history = [_make_entry(500)] * 20
        result = analyze_stability(history)
        assert len(result.regressions_detected) == 0

    def test_detect_15pct_regression(self):
        """15%+ latency increase should be detected."""
        baseline = [_make_entry(500)] * 10
        recent = [_make_entry(600)] * 3  # +20%
        result = analyze_stability(baseline + recent)
        assert len(result.regressions_detected) == 1
        assert "+20%" in result.regressions_detected[0]

    def test_detect_100pct_regression(self):
        """100% latency regression (doubling) clearly detected."""
        baseline = [_make_entry(200)] * 10
        recent = [_make_entry(400)] * 3
        result = analyze_stability(baseline + recent)
        assert len(result.regressions_detected) == 1
        assert "+100%" in result.regressions_detected[0]

    def test_no_regression_on_improvement(self):
        """Latency improvement should not be flagged."""
        baseline = [_make_entry(500)] * 10
        recent = [_make_entry(300)] * 3  # -40% = improvement
        result = analyze_stability(baseline + recent)
        assert len(result.regressions_detected) == 0

    def test_regression_per_cuj(self):
        """Each CUJ is checked independently."""
        baseline = []
        for _ in range(10):
            baseline.append({
                "demo_ready": True,
                "cujs": {
                    "CUJ-01": {"status": "PASS", "e2e_ms": 500},
                    "CUJ-02": {"status": "PASS", "e2e_ms": 1000},
                },
            })
        recent = []
        for _ in range(3):
            recent.append({
                "demo_ready": True,
                "cujs": {
                    "CUJ-01": {"status": "PASS", "e2e_ms": 700},   # +40% regression
                    "CUJ-02": {"status": "PASS", "e2e_ms": 1050},  # +5% ok
                },
            })
        result = analyze_stability(baseline + recent)
        assert len(result.regressions_detected) == 1
        assert "CUJ-01" in result.regressions_detected[0]

    def test_insufficient_history_no_regression(self):
        """With < 13 entries, regression check is skipped."""
        history = [_make_entry(500)] * 5
        result = analyze_stability(history)
        assert len(result.regressions_detected) == 0

    def test_marginal_14pct_not_flagged(self):
        """14% increase is under 15% threshold — not flagged."""
        baseline = [_make_entry(500)] * 10
        recent = [_make_entry(570)] * 3  # +14%
        result = analyze_stability(baseline + recent)
        assert len(result.regressions_detected) == 0
