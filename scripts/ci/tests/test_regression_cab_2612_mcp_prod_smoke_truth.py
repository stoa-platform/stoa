"""CAB-2612: a skipped prod MCP smoke must not read as a green validation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/ci/mcp_prod_smoke_truth.sh"
WF = ROOT / ".github/workflows/mcp-sdk-smoke.yml"
COMMIT = "c4b1ea7bc801b0f6858f1e043ac3c710deae88fb"


def _run(tmp_path: Path, **overrides: str):
    out, summary = tmp_path / "out", tmp_path / "summary"
    out.write_text("")
    summary.write_text("")
    env = {
        "PATH": os.environ["PATH"],
        "MCP_SMOKE_EVENT": "schedule",
        "MCP_SMOKE_REQUIRED_INPUT": "",
        "MCP_SMOKE_REQUIRED_VAR": "",
        "MCP_SMOKE_DNS": "false",
        "MCP_SMOKE_RAN": "false",
        "MCP_SMOKE_EXIT": "",
        "MCP_SMOKE_SETUP": "skipped",
        "MCP_SMOKE_REASON": "",
        "MCP_COMMIT": COMMIT,
        "MCP_ENVIRONMENT": "prod",
        "GITHUB_OUTPUT": str(out),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    env.update(overrides)
    proc = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    parsed = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    return proc, parsed, summary.read_text()


def test_skip_required_and_dns_ko_are_not_green(tmp_path):
    proc, outputs, summary = _run(tmp_path, MCP_SMOKE_REQUIRED_VAR="true")
    assert proc.returncode != 0 and outputs["mcp_prod_status"] == "SKIP"
    assert "::error::NON VÉRIFIÉ" in proc.stdout and "SKIP — NON VÉRIFIÉ" in summary
    assert COMMIT in summary and "| Environment | prod |" in summary
    assert "| State | PASS |" not in summary

    proc, outputs, summary = _run(tmp_path, MCP_SMOKE_DNS="false")
    assert proc.returncode != 0 and outputs["mcp_prod_status"] == "SKIP"
    assert "DNS non résolu" in summary and "mcp_prod_status=PASS" not in proc.stdout
    assert "| State | PASS |" not in summary and "| State | FAIL |" not in summary


def test_optional_skip_warns_without_passing(tmp_path):
    proc, outputs, summary = _run(
        tmp_path,
        MCP_SMOKE_EVENT="workflow_dispatch",
        MCP_SMOKE_REQUIRED_INPUT="false",
        MCP_SMOKE_REQUIRED_VAR="true",
    )
    assert proc.returncode == 0 and outputs["mcp_prod_status"] == "SKIP"
    assert "::warning::NON VÉRIFIÉ" in proc.stdout and "::error::" not in proc.stdout
    assert "DNS non résolu" in summary and "| State | PASS |" not in summary


def test_endpoint_absent_skips_and_executed_smoke_passes(tmp_path):
    proc, outputs, summary = _run(
        tmp_path, MCP_SMOKE_DNS="true", MCP_SMOKE_SETUP="success"
    )
    assert proc.returncode != 0 and outputs["mcp_prod_status"] == "SKIP"
    assert "endpoint absent" in summary and "| State | PASS |" not in summary

    proc, outputs, summary = _run(
        tmp_path,
        MCP_SMOKE_DNS="true",
        MCP_SMOKE_RAN="true",
        MCP_SMOKE_EXIT="0",
        MCP_SMOKE_SETUP="success",
    )
    assert proc.returncode == 0 and outputs["mcp_prod_status"] == "PASS"
    assert "| State | PASS |" in summary and "NON VÉRIFIÉ" not in summary
    assert "::warning::" not in proc.stdout and "::error::" not in proc.stdout
    assert COMMIT in summary and "| Environment | prod |" in summary


def test_failures_defaults_and_precedence(tmp_path):
    proc, outputs, summary = _run(
        tmp_path, MCP_SMOKE_DNS="true", MCP_SMOKE_RAN="true", MCP_SMOKE_EXIT="1",
        MCP_SMOKE_SETUP="success", MCP_SMOKE_REQUIRED_VAR="false",
    )
    assert proc.returncode != 0 and outputs["mcp_prod_status"] == "FAIL"
    assert "| State | FAIL |" in summary and "| State | PASS |" not in summary
    proc, outputs, summary = _run(tmp_path, MCP_SMOKE_DNS="true", MCP_SMOKE_SETUP="failure")
    assert proc.returncode != 0 and outputs["mcp_prod_status"] == "FAIL" and "install failed" in summary
    for event in ("schedule", "workflow_dispatch"):
        proc, outputs, _ = _run(tmp_path, MCP_SMOKE_EVENT=event)
        assert proc.returncode != 0 and outputs["mcp_prod_status"] == "SKIP"
    proc, outputs, _ = _run(
        tmp_path, MCP_SMOKE_EVENT="workflow_dispatch",
        MCP_SMOKE_REQUIRED_INPUT="true", MCP_SMOKE_REQUIRED_VAR="false",
    )
    assert proc.returncode != 0 and outputs["mcp_prod_status"] == "SKIP"
    proc, outputs, _ = _run(tmp_path, MCP_SMOKE_REQUIRED_VAR="false")
    assert proc.returncode == 0 and outputs["mcp_prod_status"] == "SKIP"
    proc, outputs, _ = _run(
        tmp_path, MCP_SMOKE_REQUIRED_VAR="maybe", MCP_SMOKE_DNS="true",
        MCP_SMOKE_RAN="true", MCP_SMOKE_EXIT="0",
    )
    assert proc.returncode != 0 and outputs.get("mcp_prod_status") != "PASS"


def test_workflow_keeps_the_probe_honest_and_does_not_republish():
    script, text = SCRIPT.read_text(), WF.read_text()
    assert not any(tok in script for tok in ("getent", "curl", "dig ", "kubectl", "terraform"))
    assert "continue-on-error" not in text
    assert not any(tok in text.lower() for tok in ("kubectl", "terraform", "cloudflare", "wrangler"))
    doc = yaml.safe_load(text)
    if True in doc and "on" not in doc:
        doc["on"] = doc.pop(True)
    target = doc["on"]["workflow_dispatch"]["inputs"]["target"]
    assert target["type"] == "choice" and target["default"] == "prod"
    assert target["options"] == ["prod", "local"]
    pre, post = doc["jobs"]["pre-merge"], doc["jobs"]["post-deploy"]
    assert any("local_mcp_sdk_smoke.py" in step.get("run", "") for step in pre["steps"])
    assert "continue-on-error" not in pre
    assert post["outputs"]["mcp_prod_status"] == "${{ steps.truth.outputs.mcp_prod_status }}"
    assert "schedule" in post["if"] and "workflow_dispatch" in post["if"]
    steps = post["steps"]
    dns = next(step for step in steps if step.get("id") == "dns")
    smoke = next(step for step in steps if step.get("id") == "smoke")
    truth = next(step for step in steps if step.get("id") == "truth")
    checkout = next(step for step in steps if "actions/checkout" in step.get("uses", ""))
    assert "if" not in checkout and steps.index(checkout) < steps.index(dns)
    assert "if" not in dns and "getent hosts mcp.gostoa.dev" in dns["run"]
    assert smoke["if"] == "success() && steps.dns.outputs.resolves == 'true'"
    assert 'echo "ran=true"' in smoke["run"] and "exit_code" in smoke["run"]
    assert truth["if"] == "success() || failure()"
    assert "bash scripts/ci/mcp_prod_smoke_truth.sh" in truth["run"]
    assert truth["env"]["MCP_SMOKE_REQUIRED_INPUT"] == "true"
    assert "MCP_SMOKE_REQUIRED_VAR" not in truth["env"]
    assert truth["env"]["MCP_COMMIT"] == "${{ github.sha }}"
    assert truth["env"]["MCP_ENVIRONMENT"] == "prod"
