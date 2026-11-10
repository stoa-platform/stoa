"""CAB-2612: a dev post-deploy miss must not read as a silent green pass."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/ci/dev_post_deploy_truth.sh"
WF = ROOT / ".github/workflows"
COMMIT = "1a327342c188"


def _load(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text())
    if True in doc and "on" not in doc:
        doc["on"] = doc.pop(True)
    return doc


def _run(tmp_path: Path, **overrides: str):
    out, summary = tmp_path / "out", tmp_path / "summary"
    out.write_text("")
    summary.write_text("")
    env = {
        "PATH": os.environ["PATH"],
        "POST_DEPLOY_CONTROL": "Wait for ArgoCD sync",
        "POST_DEPLOY_RAN": "true",
        "POST_DEPLOY_OK": "false",
        "POST_DEPLOY_REASON": "Endpoint not healthy after 300s (last: HTTP 000)",
        "POST_DEPLOY_REQUIRED_INPUT": "",
        "POST_DEPLOY_REQUIRED_VAR": "",
        "POST_DEPLOY_COMMIT": COMMIT,
        "POST_DEPLOY_ENVIRONMENT": "dev",
        "GITHUB_OUTPUT": str(out),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    env.update(overrides)
    proc = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=False
    )
    parsed = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    return proc, parsed, summary.read_text()


def test_swallowed_http_000_is_fail_not_silent_green(tmp_path):
    proc, outputs, summary = _run(tmp_path)
    assert proc.returncode == 0
    assert outputs["post_deploy_status"] == "FAIL"
    assert "::warning::FAIL" in proc.stdout
    assert "::error::" not in proc.stdout
    assert "HTTP 000" in proc.stdout and COMMIT in proc.stdout and "environment dev" in proc.stdout
    assert "| State | FAIL |" in summary and "| State | PASS |" not in summary
    assert "NON VÉRIFIÉ" not in summary
    assert f"`{COMMIT}`" in summary and "| Environment | dev |" in summary
    assert "post_deploy_status=PASS" not in proc.stdout

    proc, outputs, summary = _run(tmp_path, POST_DEPLOY_REQUIRED_VAR="true")
    assert proc.returncode != 0 and outputs["post_deploy_status"] == "FAIL"
    assert "::error::FAIL" in proc.stdout and "::warning::" not in proc.stdout
    assert "| State | FAIL |" in summary and "| State | PASS |" not in summary


def test_skip_is_visible_and_required_fails(tmp_path):
    proc, outputs, summary = _run(
        tmp_path,
        POST_DEPLOY_CONTROL="Health checks",
        POST_DEPLOY_RAN="false",
        POST_DEPLOY_OK="",
        POST_DEPLOY_REASON="SKIPPED, no dev target",
    )
    assert proc.returncode == 0 and outputs["post_deploy_status"] == "SKIP"
    assert "::warning::NON VÉRIFIÉ" in proc.stdout
    assert "SKIPPED, no dev target" in proc.stdout and COMMIT in proc.stdout
    assert "environment dev" in proc.stdout
    assert "SKIP — NON VÉRIFIÉ" in summary and "| State | PASS |" not in summary
    assert "| State | FAIL |" not in summary
    assert f"`{COMMIT}`" in summary and "| Environment | dev |" in summary

    proc, outputs, summary = _run(
        tmp_path,
        POST_DEPLOY_CONTROL="smoke-test",
        POST_DEPLOY_RAN="false",
        POST_DEPLOY_OK="",
        POST_DEPLOY_REASON="smoke-test did not run",
        POST_DEPLOY_REQUIRED_INPUT="true",
        POST_DEPLOY_REQUIRED_VAR="false",
    )
    assert proc.returncode != 0 and outputs["post_deploy_status"] == "SKIP"
    assert "::error::NON VÉRIFIÉ" in proc.stdout
    assert "SKIP — NON VÉRIFIÉ" in summary and "| State | PASS |" not in summary


def test_real_pass_and_defaults(tmp_path):
    proc, outputs, summary = _run(
        tmp_path,
        POST_DEPLOY_OK="true",
        POST_DEPLOY_REASON="endpoint healthy",
    )
    assert proc.returncode == 0 and outputs["post_deploy_status"] == "PASS"
    assert "| State | PASS |" in summary and "NON VÉRIFIÉ" not in summary
    assert "::warning::" not in proc.stdout and "::error::" not in proc.stdout
    assert f"`{COMMIT}`" in summary and "| Environment | dev |" in summary

    proc, outputs, _ = _run(tmp_path, POST_DEPLOY_REQUIRED_VAR="false")
    assert proc.returncode == 0 and outputs["post_deploy_status"] == "FAIL"
    proc, outputs, _ = _run(tmp_path, POST_DEPLOY_REQUIRED_VAR="maybe", POST_DEPLOY_OK="true")
    assert proc.returncode != 0 and outputs.get("post_deploy_status") != "PASS"
    proc, outputs, _ = _run(
        tmp_path,
        POST_DEPLOY_REQUIRED_INPUT="false",
        POST_DEPLOY_REQUIRED_VAR="true",
        POST_DEPLOY_RAN="false",
        POST_DEPLOY_OK="",
        POST_DEPLOY_REASON="SKIPPED, no dev target",
    )
    assert proc.returncode == 0 and outputs["post_deploy_status"] == "SKIP"


def test_workflows_record_the_verdict_without_weakening_guards():
    script = SCRIPT.read_text()
    assert not any(tok in script for tok in ("kubectl", "terraform", "curl", "getent", "dig "))

    gitops = _load(WF / "reusable-gitops-deploy.yml")
    job = gitops["jobs"]["gitops-deploy"]
    assert job["if"] == "vars.GITOPS_DEPLOY_ENABLED == 'true'"
    assert job["outputs"]["post_deploy_status"] == "${{ steps.truth.outputs.post_deploy_status }}"
    call = gitops["on"]["workflow_call"]
    assert (
        call["outputs"]["post_deploy_status"]["value"]
        == "${{ jobs.gitops-deploy.outputs.post_deploy_status }}"
    )
    text = (WF / "reusable-gitops-deploy.yml").read_text()
    assert "continue-on-error" not in text
    assert "ArgoCD sync may still be in progress" not in text
    wait = next(step for step in job["steps"] if step.get("id") == "wait")
    truth = next(step for step in job["steps"] if step.get("id") == "truth")
    assert "if" not in wait
    assert wait["run"].index("ran=false") < wait["run"].index("curl")
    assert "ok=false" in wait["run"]
    assert "Endpoint not healthy after ${TIMEOUT}s (last: HTTP ${HTTP_CODE})" in wait["run"]
    assert "::warning::" not in wait["run"] and "exit 1" not in wait["run"]
    assert truth["if"] == "always()"
    assert "bash scripts/ci/dev_post_deploy_truth.sh" in truth["run"]
    assert truth["env"]["POST_DEPLOY_REQUIRED_VAR"] == "${{ vars.DEV_POST_DEPLOY_REQUIRED }}"
    assert truth["env"]["POST_DEPLOY_REQUIRED_INPUT"] == "true"
    assert truth["env"]["POST_DEPLOY_COMMIT"] == "${{ github.sha }}"
    assert truth["env"]["POST_DEPLOY_ENVIRONMENT"] == "${{ inputs.environment }}"
    assert truth["env"]["POST_DEPLOY_RAN"] == "${{ steps.wait.outputs.ran }}"
    assert truth["env"]["POST_DEPLOY_OK"] == "${{ steps.wait.outputs.ok }}"
    dispatch = next(step for step in job["steps"] if "repository-dispatch@" in step.get("uses", ""))
    assert dispatch["with"]["repository"] == "PotoMitan/stoa-infra"
    assert job["steps"].index(dispatch) < job["steps"].index(wait)

    health_text = (WF / "reusable-health-smoke.yml").read_text()
    health = _load(WF / "reusable-health-smoke.yml")
    hjob = health["jobs"]["health-check"]
    assert "continue-on-error" not in health_text and "gostoa.dev" not in health_text
    assert hjob["outputs"]["post_deploy_status"] == "${{ steps.truth.outputs.post_deploy_status }}"
    assert (
        health["on"]["workflow_call"]["outputs"]["post_deploy_status"]["value"]
        == "${{ jobs.health-check.outputs.post_deploy_status }}"
    )
    checks = next(step for step in hjob["steps"] if step.get("name") == "Health checks")
    htruth = next(step for step in hjob["steps"] if step.get("id") == "truth")
    assert checks["if"] == "steps.resolve.outputs.skip != 'true'"
    assert '[ "$FAIL" -eq 0 ] || exit 1' in checks["run"]
    assert "ran=true" in checks["run"] and "ok=false" in checks["run"]
    assert htruth["if"] == "always()"
    assert "SKIPPED, no dev target" in htruth["run"]
    assert "bash scripts/ci/dev_post_deploy_truth.sh" in htruth["run"]
    assert htruth["env"]["POST_DEPLOY_REQUIRED_VAR"] == "${{ vars.DEV_POST_DEPLOY_REQUIRED }}"
    assert htruth["env"]["POST_DEPLOY_REQUIRED_INPUT"] == "true"
    assert htruth["env"]["POST_DEPLOY_ENVIRONMENT"] == "${{ inputs.environment }}"
    assert htruth["env"]["POST_DEPLOY_COMMIT"] == "${{ github.sha }}"

    api = _load(WF / "control-plane-api-ci.yml")["jobs"]
    smoke_if = api["smoke-test"]["if"]
    assert "environment == 'prod'" not in smoke_if
    assert "needs.deploy.result == 'success'" in smoke_if
    assert "vars.GITOPS_DEPLOY_ENABLED == 'true'" in smoke_if
    assert (
        api["smoke-test"]["with"]["environment"]
        == "${{ github.event.inputs.environment || 'dev' }}"
    )
    assert "base-domain" not in api["smoke-test"]["with"]
    assert api["deploy"]["with"]["verify-endpoint"] == (
        "${{ github.event.inputs.environment == 'prod' && 'https://api.gostoa.dev/health' || '' }}"
    )

    for name in ("security-scheduled.yml", "mcp-sdk-smoke.yml"):
        untouched = (WF / name).read_text()
        assert "DEV_POST_DEPLOY_REQUIRED" not in untouched
        assert "dev_post_deploy_truth" not in untouched
