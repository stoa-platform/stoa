"""L3-01: Consecutive L2 PASS counter.

Reads the L2 history and computes the number of consecutive PASS runs.
This is the primary demo confidence indicator.

Thresholds:
    >= 50 consecutive → "production-ready" (HIGH confidence)
    >= 10 consecutive → "stable" (MEDIUM confidence)
    < 10             → "unstable" (LOW confidence)
    0                → "BLOCKED"
"""

from __future__ import annotations

import json
import time

import pytest

from scoring.l3_analyzer import analyze_stability, L3Result

pytestmark = [pytest.mark.l3]


class TestConsecutivePass:
    """L3-01: Consecutive PASS tracking and demo confidence."""

    def test_consecutive_pass_from_history(self):
        """Verify consecutive pass counter from L3 history."""
        result = analyze_stability()
        # This is a live check — we just verify the analyzer runs
        assert isinstance(result, L3Result)
        assert result.consecutive_l2_pass >= 0
        assert result.demo_confidence in ("HIGH", "MEDIUM", "LOW", "BLOCKED")

    def test_high_confidence_threshold(self):
        history = [{"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 500}}}] * 55
        result = analyze_stability(history)
        assert result.consecutive_l2_pass == 55
        assert result.demo_confidence == "HIGH"
        assert result.stability_status == "stable"

    def test_medium_confidence_threshold(self):
        fail = [{"demo_ready": False, "cujs": {"CUJ-01": {"status": "FAIL", "e2e_ms": 500}}}]
        passes = [{"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 500}}}] * 15
        result = analyze_stability(fail + passes)
        assert result.consecutive_l2_pass == 15
        assert result.demo_confidence == "MEDIUM"

    def test_low_confidence_threshold(self):
        fail = [{"demo_ready": False, "cujs": {}}]
        passes = [{"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 500}}}] * 5
        result = analyze_stability(fail + passes)
        assert result.consecutive_l2_pass == 5
        assert result.demo_confidence == "LOW"

    def test_blocked_on_last_fail(self):
        passes = [{"demo_ready": True, "cujs": {}}] * 100
        fail = [{"demo_ready": False, "cujs": {}}]
        result = analyze_stability(passes + fail)
        assert result.consecutive_l2_pass == 0
        assert result.demo_confidence == "BLOCKED"

    def test_empty_history(self):
        result = analyze_stability([])
        assert result.consecutive_l2_pass == 0
        assert result.demo_confidence == "BLOCKED"
        assert result.stability_status == "unknown"
