"""Unit tests for scoring modules — run locally without K8s."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from scoring.l1_scorer import score_l1
from scoring.l2_reporter import aggregate_results
from scoring.l3_analyzer import L3Result, analyze_stability
from scoring.push_metrics import MetricsPusher


class TestL1Scorer:
    def test_full_score_all_pass(self):
        dims = {
            "auth_chain": {"passes": 10, "fails": 0, "p95_seconds": 0.1},
            "policy_eval": {"passes": 10, "fails": 0, "p95_seconds": 0.05},
            "guardrails": {"passes": 10, "fails": 0, "p95_seconds": 0.1},
            "quota_burst": {"passes": 10, "fails": 0, "p95_seconds": 0.1},
            "resilience": {"passes": 10, "fails": 0, "p95_seconds": 0.5},
            "governance": {"passes": 10, "fails": 0, "p95_seconds": 0.2},
            "tls_mtls": {"passes": 10, "fails": 0, "p95_seconds": 0.01},
            "request_transform": {"passes": 10, "fails": 0, "p95_seconds": 0.1},
            "mcp_discovery": {"passes": 10, "fails": 0, "p95_seconds": 0.02},
            "mcp_toolcall": {"passes": 10, "fails": 0, "p95_seconds": 0.1},
            "llm_routing": {"passes": 10, "fails": 0, "p95_seconds": 0.5},
            "llm_cost": {"passes": 10, "fails": 0, "p95_seconds": 0.2},
            "llm_circuit_breaker": {"passes": 10, "fails": 0, "p95_seconds": 0.5},
            "native_tools_crud": {"passes": 10, "fails": 0, "p95_seconds": 0.1},
            "api_bridge": {"passes": 10, "fails": 0, "p95_seconds": 0.5},
            "uac_binding": {"passes": 10, "fails": 0, "p95_seconds": 0.5},
            "pii_detection": {"passes": 10, "fails": 0, "p95_seconds": 0.1},
            "distributed_tracing": {"passes": 10, "fails": 0, "p95_seconds": 0.2},
            "prompt_cache": {"passes": 10, "fails": 0, "p95_seconds": 0.2},
            "federation": {"passes": 10, "fails": 0, "p95_seconds": 0.5},
        }
        result = score_l1(dims)
        assert result["l1a_core_score"] > 80
        assert result["l1b_ai_score"] > 80
        assert result["composite_score"] > 80
        assert len(result["dimensions"]) == 20

    def test_kong_no_mcp_scores_zero(self):
        """Kong has no MCP features — L1-B should score near 0."""
        dims = {
            "auth_chain": {"passes": 10, "fails": 0, "p95_seconds": 0.1},
            "policy_eval": {"passes": 10, "fails": 0, "p95_seconds": 0.05},
        }
        features = ["auth_chain", "policy_eval", "guardrails", "quota_burst",
                     "resilience", "governance", "tls_mtls", "request_transform"]
        result = score_l1(dims, features=features)
        assert result["l1a_core_score"] > 0
        assert result["l1b_ai_score"] == 0  # No AI features
        assert result["composite_score"] < result["l1a_core_score"]

    def test_separate_scores_always_visible(self):
        dims = {"mcp_discovery": {"passes": 10, "fails": 0, "p95_seconds": 0.02}}
        result = score_l1(dims)
        assert "l1a_core_score" in result
        assert "l1b_ai_score" in result
        assert "composite_score" in result


class TestL2Reporter:
    def test_aggregate_all_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            for i in range(1, 6):
                (p / f"cuj_cuj_{i:02d}.json").write_text(json.dumps({
                    "cuj_id": f"CUJ-{i:02d}",
                    "status": "PASS",
                    "e2e_ms": 500 + i * 100,
                    "sub_tests": {},
                }))
            result = aggregate_results(p)
            assert result["demo_ready"] is True
            assert result["summary"] == "5/5 CUJs PASS"
            assert result["demo_note"] == "GO"

    def test_blocker_fail_blocks_demo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            (p / "cuj_cuj_01.json").write_text(json.dumps({
                "cuj_id": "CUJ-01", "status": "FAIL", "e2e_ms": 3000, "sub_tests": {},
            }))
            (p / "cuj_cuj_02.json").write_text(json.dumps({
                "cuj_id": "CUJ-02", "status": "PASS", "e2e_ms": 1000, "sub_tests": {},
            }))
            result = aggregate_results(p)
            assert result["demo_ready"] is False
            assert "BLOCKED" in result["demo_note"]

    def test_degraded_when_only_optional_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir)
            for cid in ["CUJ-01", "CUJ-02", "CUJ-05"]:
                (p / f"cuj_{cid.lower().replace('-', '_')}.json").write_text(json.dumps({
                    "cuj_id": cid, "status": "PASS", "e2e_ms": 500, "sub_tests": {},
                }))
            (p / "cuj_cuj_03.json").write_text(json.dumps({
                "cuj_id": "CUJ-03", "status": "FAIL", "e2e_ms": 5000, "sub_tests": {},
            }))
            result = aggregate_results(p)
            assert result["demo_ready"] is True
            assert "DEGRADED" in result["demo_note"]


class TestL3Analyzer:
    def test_high_confidence(self):
        history = [{"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 500}}}] * 55
        result = analyze_stability(history)
        assert result.demo_confidence == "HIGH"
        assert result.consecutive_l2_pass == 55

    def test_blocked_on_fail(self):
        history = [{"demo_ready": False, "cujs": {}}]
        result = analyze_stability(history)
        assert result.demo_confidence == "BLOCKED"
        assert result.consecutive_l2_pass == 0

    def test_regression_detected(self):
        baseline = [{"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 500}}}] * 10
        recent = [{"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 1000}}}] * 3
        result = analyze_stability(baseline + recent)
        assert len(result.regressions_detected) > 0
        assert "+100%" in result.regressions_detected[0]

    def test_flaky_detection(self):
        history = []
        for i in range(100):
            status = "PASS" if i % 5 != 0 else "FAIL"  # 20% failure = flaky
            history.append({"demo_ready": status == "PASS", "cujs": {"CUJ-03": {"status": status, "e2e_ms": 500}}})
        result = analyze_stability(history)
        assert len(result.flaky_cujs) > 0
        assert "CUJ-03" in result.flaky_cujs[0]

    def test_error_rates_computed(self):
        history = []
        for i in range(20):
            status = "PASS" if i % 4 != 0 else "FAIL"  # 25% error
            history.append({"demo_ready": status == "PASS", "cujs": {"CUJ-01": {"status": status, "e2e_ms": 500}}})
        result = analyze_stability(history)
        assert result.error_rates["CUJ-01"] == 25.0

    def test_error_trend_in_result(self):
        history = [{"demo_ready": True, "cujs": {"CUJ-01": {"status": "PASS", "e2e_ms": 500}}}] * 40
        result = analyze_stability(history)
        assert result.error_trend == "stable"
        assert result.error_rates.get("CUJ-01", 0) == 0


class TestMetricsPusher:
    def test_render_format(self):
        pusher = MetricsPusher()
        pusher.add_gauge("test_metric", 42.5, {"env": "test"}, "A test metric")
        pusher.add_gauge("test_metric", 10.0, {"env": "prod"}, "A test metric")
        output = pusher.render()
        assert '# HELP test_metric A test metric' in output
        assert '# TYPE test_metric gauge' in output
        assert 'test_metric{env="test"} 42.5' in output
        assert 'test_metric{env="prod"} 10.0' in output
        # HELP/TYPE only once per metric name
        assert output.count("# HELP test_metric") == 1

    def test_clear(self):
        pusher = MetricsPusher()
        pusher.add_gauge("x", 1)
        pusher.clear()
        assert pusher.render().strip() == ""
