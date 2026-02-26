"""Tests for compare_results.py — performance regression detector."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Add parent dir to path so we can import compare_results
sys.path.insert(0, str(Path(__file__).parent.parent))

import compare_results  # noqa: E402


def _write_k6_summary(path: Path, p95_ms: float, check_rate: float = 1.0) -> None:
    """Write a minimal k6 JSON summary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "metrics": {
            "http_req_duration": {
                "values": {
                    "p(95)": p95_ms,
                    "p(50)": p95_ms * 0.7,
                    "avg": p95_ms * 0.6,
                    "min": p95_ms * 0.1,
                    "max": p95_ms * 1.5,
                }
            },
            "checks": {"values": {"rate": check_rate, "passes": 100, "fails": 0}},
        }
    }
    path.write_text(json.dumps(data))


class TestExtractP95:
    def test_extracts_p95_from_valid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "test.json"
        _write_k6_summary(f, 42.5)
        assert compare_results.extract_p95(f) == 42.5

    def test_returns_zero_for_missing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "nonexistent.json"
        assert compare_results.extract_p95(f) == 0.0

    def test_returns_zero_for_invalid_json(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("not json")
        assert compare_results.extract_p95(f) == 0.0

    def test_returns_zero_for_empty_metrics(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.json"
        f.write_text(json.dumps({"metrics": {}}))
        assert compare_results.extract_p95(f) == 0.0


class TestExtractErrorRate:
    def test_zero_error_rate(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.json"
        _write_k6_summary(f, 10.0, check_rate=1.0)
        assert compare_results.extract_error_rate(f) == 0.0

    def test_high_error_rate(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        _write_k6_summary(f, 10.0, check_rate=0.3)
        result = compare_results.extract_error_rate(f)
        assert abs(result - 0.7) < 0.01

    def test_missing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "missing.json"
        assert compare_results.extract_error_rate(f) == 0.0


class TestCompareScenario:
    def test_pass_no_regression(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        _write_k6_summary(baseline / "health.json", 10.0)
        _write_k6_summary(pr / "health.json", 10.2)  # 2% — well within threshold

        result = compare_results.compare_scenario("health", baseline, pr)
        assert result["verdict"] == "PASS"
        assert result["baseline_p95_ms"] == 10.0
        assert result["pr_p95_ms"] == 10.2

    def test_warn_moderate_regression(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        _write_k6_summary(baseline / "sequential.json", 100.0)
        _write_k6_summary(pr / "sequential.json", 108.0)  # 8% — WARN territory

        result = compare_results.compare_scenario("sequential", baseline, pr)
        assert result["verdict"] == "WARN"

    def test_fail_large_regression(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        _write_k6_summary(baseline / "burst_50.json", 50.0)
        _write_k6_summary(pr / "burst_50.json", 60.0)  # 20% — FAIL

        result = compare_results.compare_scenario("burst_50", baseline, pr)
        assert result["verdict"] == "FAIL"

    def test_fail_high_error_rate(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        _write_k6_summary(baseline / "health.json", 10.0)
        _write_k6_summary(pr / "health.json", 10.0, check_rate=0.3)  # 70% errors

        result = compare_results.compare_scenario("health", baseline, pr)
        assert result["verdict"] == "FAIL"
        assert "error rate" in result["reason"].lower()

    def test_pass_improvement(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        _write_k6_summary(baseline / "health.json", 50.0)
        _write_k6_summary(pr / "health.json", 40.0)  # -20% = improvement

        result = compare_results.compare_scenario("health", baseline, pr)
        assert result["verdict"] == "PASS"
        assert result["regression_pct"] < 0

    def test_missing_baseline(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        baseline.mkdir()
        _write_k6_summary(pr / "health.json", 10.0)

        result = compare_results.compare_scenario("health", baseline, pr)
        assert result["verdict"] == "PASS"
        assert result["baseline_p95_ms"] == 0.0


class TestMainFunction:
    def test_pass_exit_code_zero(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        for scenario in compare_results.SCENARIOS:
            _write_k6_summary(baseline / f"{scenario}.json", 10.0)
            _write_k6_summary(pr / f"{scenario}.json", 10.0)

        with patch("sys.argv", ["compare-results.py", str(baseline), str(pr)]):
            exit_code = compare_results.main()
        assert exit_code == 0

    def test_fail_exit_code_one(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        for scenario in compare_results.SCENARIOS:
            _write_k6_summary(baseline / f"{scenario}.json", 10.0)
            _write_k6_summary(pr / f"{scenario}.json", 20.0)  # 100% regression

        with patch("sys.argv", ["compare-results.py", str(baseline), str(pr)]):
            exit_code = compare_results.main()
        assert exit_code == 1

    def test_warn_exit_code_zero_by_default(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        for scenario in compare_results.SCENARIOS:
            _write_k6_summary(baseline / f"{scenario}.json", 100.0)
            _write_k6_summary(pr / f"{scenario}.json", 108.0)  # 8% — WARN

        with patch("sys.argv", ["compare-results.py", str(baseline), str(pr)]):
            exit_code = compare_results.main()
        assert exit_code == 0

    def test_warn_exit_code_one_with_flag(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        for scenario in compare_results.SCENARIOS:
            _write_k6_summary(baseline / f"{scenario}.json", 100.0)
            _write_k6_summary(pr / f"{scenario}.json", 108.0)

        with patch(
            "sys.argv",
            ["compare-results.py", str(baseline), str(pr), "--fail-on-warn"],
        ):
            exit_code = compare_results.main()
        assert exit_code == 1

    def test_no_baseline_passes(self, tmp_path: Path) -> None:
        pr = tmp_path / "pr"
        for scenario in compare_results.SCENARIOS:
            _write_k6_summary(pr / f"{scenario}.json", 10.0)

        with patch(
            "sys.argv",
            ["compare-results.py", str(tmp_path / "nonexistent"), str(pr)],
        ):
            exit_code = compare_results.main()
        assert exit_code == 0

    def test_writes_json_report(self, tmp_path: Path) -> None:
        baseline = tmp_path / "baseline"
        pr = tmp_path / "pr"
        for scenario in compare_results.SCENARIOS:
            _write_k6_summary(baseline / f"{scenario}.json", 10.0)
            _write_k6_summary(pr / f"{scenario}.json", 10.5)

        with patch("sys.argv", ["compare-results.py", str(baseline), str(pr)]):
            compare_results.main()

        report = json.loads((pr / "regression-report.json").read_text())
        assert "overall_verdict" in report
        assert "scenarios" in report
        assert len(report["scenarios"]) == len(compare_results.SCENARIOS)
