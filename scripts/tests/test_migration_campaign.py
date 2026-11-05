# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
"""Offline campaign integration tests with real generation and comparison."""

import json
import subprocess
import sys
from pathlib import Path

from scripts import migration_campaign as campaign

FIXTURES = Path(__file__).parent / "fixtures/camel"


def test_all_flows_and_measurements():
    report = campaign.run(FIXTURES)
    assert len(report) >= 3
    assert [row["flow"] for row in report] == sorted(row["flow"] for row in report)
    assert all(row["result"] == "PASS" and not row["diff"] for row in report)
    for row in report:
        assert row["generation_seconds"] >= 0
        assert row["comparison_seconds"] >= 0
        assert "<routes" in row["route_xml"]
        assert "offline" in row["explanation"]


def test_changed_generated_constant_is_explained(monkeypatch, tmp_path):
    original = campaign.generate
    monkeypatch.setattr(
        campaign, "generate", lambda flow: original(flow).replace("text/plain", "text/changed")
    )
    row = next(row for row in campaign.run(FIXTURES) if row["flow"] == "constant.xml")
    assert row["result"] == "FAIL"
    assert "text/changed" in row["diff"] and "text/plain" in row["diff"]
    assert "differ" in row["explanation"]
    monkeypatch.setattr(sys, "argv", ["campaign", "--output", str(tmp_path)])
    assert campaign.main() == 1
    assert "text/changed" in (tmp_path / "campaign.md").read_text()


def test_invalid_flow_does_not_hide_other_results(tmp_path):
    (tmp_path / "bad.xml").write_text("<FLOW>")
    (tmp_path / "good.xml").write_text((FIXTURES / "constant.xml").read_text())
    bad, good = campaign.run(tmp_path)
    assert bad["result"] == "ERROR" and "Invalid flow XML" in bad["explanation"]
    assert bad["generation_seconds"] >= 0 and bad["comparison_seconds"] is None
    assert good["result"] == "PASS"


def test_cli_reports_and_empty_input(tmp_path):
    script = Path(__file__).parents[1] / "migration_campaign.py"
    output = tmp_path / "output"
    result = subprocess.run(
        [sys.executable, str(script), "--output", str(output)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    rows = json.loads((output / "campaign.json").read_text())
    summary = (output / "campaign.md").read_text()
    assert all(row["flow"] in summary for row in rows)
    assert "Generation (s)" in summary and "Comparison (s)" in summary
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--fixtures",
            str(tmp_path / "missing"),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2 and "No XML flow fixtures" in result.stderr
