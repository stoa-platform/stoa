"""Required probes must execute successfully, even after continue-on-error."""

import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("outcome", ["skipped", "cancelled", "failure", "", None])
def test_required_step_rejects_missing_or_unsuccessful_execution(outcome):
    steps = {"probe": {"outcome": outcome, "conclusion": "success"}}
    result = run_guard(steps)
    assert result.returncode == 1
    assert "::error::Required step probe" in result.stdout


def run_guard(steps):
    return subprocess.run(
        ["python3", str(ROOT / "scripts/ci/require_steps.py"), "probe"],
        env={**os.environ, "REQUIRED_STEP_RESULTS": json.dumps(steps)},
        capture_output=True, text=True, check=False,
    )


def test_required_step_accepts_only_executed_success():
    assert run_guard({"probe": {"outcome": "success", "conclusion": "success"}}).returncode == 0
    assert run_guard({}).returncode == 1
    assert run_guard({"probe": {"outcome": "success", "conclusion": "skipped"}}).returncode == 1


def test_malformed_evidence_cannot_pass():
    for evidence in ([], None, {"probe": "success"}):
        assert run_guard(evidence).returncode != 0


def test_required_workflows_cannot_disable_probes():
    workflow = yaml.safe_load((ROOT / ".github/workflows/mcp-sdk-smoke.yml").read_text())
    for name, required in (("pre-merge", "checkout sdk build smoke"),
                           ("post-deploy", "checkout dns sdk smoke truth")):
        steps = workflow["jobs"][name]["steps"]
        guard = steps[-1]
        assert guard["if"] == "always()"
        assert guard["run"].endswith("require_steps.py " + required)
        assert guard["env"]["REQUIRED_STEP_RESULTS"] == "${{ toJSON(steps) }}"
    for filename in ("reusable-health-smoke.yml", "reusable-gitops-deploy.yml"):
        doc = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())
        job = next(iter(doc["jobs"].values()))
        truth = next(step for step in job["steps"] if step.get("id") == "truth")
        assert truth["if"] == "always()"
        assert truth["env"]["POST_DEPLOY_REQUIRED_INPUT"] == "true"
