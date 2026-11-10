"""Required probes must execute successfully, even after continue-on-error."""

import json
import os
from pathlib import Path
import subprocess
from copy import deepcopy
from fnmatch import fnmatchcase

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ("reusable-health-smoke.yml", "reusable-gitops-deploy.yml")
PROD_REQUIRED = "${{ inputs.environment == 'prod' && 'true' || '' }}"


def load_workflow(name):
    doc = yaml.safe_load((ROOT / ".github/workflows" / name).read_text())
    if True in doc:
        doc["on"] = doc.pop(True)
    return doc


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


def assert_mcp_guards(workflow):
    for name, required in (("pre-merge", "checkout sdk build smoke"),
                           ("post-deploy", "checkout dns sdk smoke truth")):
        job = workflow["jobs"][name]
        assert job.get("continue-on-error", False) is False
        steps = job["steps"]
        guard = steps[-1]
        assert guard["if"] == "always()"
        assert guard.get("continue-on-error", False) is False
        assert guard["run"] == "python3 scripts/ci/require_steps.py " + required
        assert guard["env"]["REQUIRED_STEP_RESULTS"] == "${{ toJSON(steps) }}"


def test_required_workflows_cannot_disable_probes():
    assert_mcp_guards(load_workflow("mcp-sdk-smoke.yml"))


@pytest.mark.parametrize("job_name", ["pre-merge", "post-deploy"])
@pytest.mark.parametrize("target", ["job", "guard"])
@pytest.mark.parametrize("value", [True, "${{ true }}"])
def test_mcp_contract_rejects_masked_guard_failures(job_name, target, value):
    workflow = deepcopy(load_workflow("mcp-sdk-smoke.yml"))
    job = workflow["jobs"][job_name]
    (job if target == "job" else job["steps"][-1])["continue-on-error"] = value
    with pytest.raises(AssertionError):
        assert_mcp_guards(workflow)


@pytest.mark.parametrize("job_name", ["pre-merge", "post-deploy"])
def test_mcp_contract_rejects_an_echoed_guard(job_name):
    workflow = deepcopy(load_workflow("mcp-sdk-smoke.yml"))
    guard = workflow["jobs"][job_name]["steps"][-1]
    guard["run"] = "echo " + guard["run"]
    with pytest.raises(AssertionError):
        assert_mcp_guards(workflow)


@pytest.mark.parametrize("filename", WORKFLOWS)
def test_post_deploy_requires_prod_and_preserves_dev_variable(filename):
    job = next(iter(load_workflow(filename)["jobs"].values()))
    truth = next(step for step in job["steps"] if step.get("id") == "truth")
    assert job.get("continue-on-error", False) is False
    assert truth.get("continue-on-error", False) is False
    assert truth["if"] == "always()"
    assert truth["env"]["POST_DEPLOY_REQUIRED_INPUT"] == PROD_REQUIRED
    assert truth["env"]["POST_DEPLOY_REQUIRED_VAR"] == "${{ vars.DEV_POST_DEPLOY_REQUIRED }}"


@pytest.mark.parametrize("filename", WORKFLOWS)
@pytest.mark.parametrize("environment", ["prod", "dev"])
@pytest.mark.parametrize("variable", ["", "false", "true"])
@pytest.mark.parametrize("status", ["PASS", "FAIL", "SKIP"])
def test_post_deploy_verdict_matrix(tmp_path, filename, environment, variable, status):
    job = next(iter(load_workflow(filename)["jobs"].values()))
    truth = next(step for step in job["steps"] if step.get("id") == "truth")
    # Render only the supported policy expression; execute the real verdict step.
    policy = truth["env"]["POST_DEPLOY_REQUIRED_INPUT"]
    required_input = {"true": "true", PROD_REQUIRED: {"prod": "true", "dev": ""}[environment]}[policy]
    ran, ok = ("false", "") if status == "SKIP" else ("true", str(status == "PASS").lower())
    env = {
        "PATH": os.environ["PATH"],
        "POST_DEPLOY_REQUIRED_INPUT": required_input,
        "POST_DEPLOY_REQUIRED_VAR": variable,
        "POST_DEPLOY_ENVIRONMENT": environment,
        "POST_DEPLOY_RAN": ran, "POST_DEPLOY_OK": ok,
        "SMOKE_SKIP": str(status == "SKIP").lower(),
        "CHECKS_RAN": ran, "CHECKS_OK": ok,
        "GITHUB_OUTPUT": str(tmp_path / "output"),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
    }
    result = subprocess.run(["bash", "-c", truth["run"]], cwd=ROOT, env=env,
                            capture_output=True, text=True, check=False)
    required = environment == "prod" or variable == "true"
    assert result.returncode == int(required and status != "PASS"), result.stdout + result.stderr
    assert f"post_deploy_status={status}" in (tmp_path / "output").read_text()
    summary = (tmp_path / "summary").read_text()
    assert f"| Required | {str(required).lower()} |" in summary
    if status == "SKIP":
        assert "SKIP — NON VÉRIFIÉ" in summary and "| State | PASS |" not in summary


def test_workflow_only_changes_run_lightweight_regressions():
    factory = load_workflow("ai-factory-scripts-tests.yml")
    paths = factory["on"]["pull_request"]["paths"]
    for filename in (*WORKFLOWS, "mcp-sdk-smoke.yml"):
        assert any(fnmatchcase(".github/workflows/" + filename, pattern) for pattern in paths)
    gate = load_workflow("ci-gate.yml")
    commands = "\n".join(step.get("run", "") for step in gate["jobs"]["gate-contract"]["steps"])
    assert "scripts/ci/tests/test_regression_cab_2618_required_steps.py" in commands
    assert "scripts/ci/tests/test_regression_cab_2612_dev_post_deploy_truth.py" in commands


def test_legacy_dispatch_input_is_accepted_but_cannot_disable_prod():
    workflow = load_workflow("mcp-sdk-smoke.yml")
    legacy = workflow["on"]["workflow_dispatch"]["inputs"]["MCP_PROD_SMOKE_REQUIRED"]
    assert legacy["type"] == "boolean" and legacy["default"] is True
    truth = next(step for step in workflow["jobs"]["post-deploy"]["steps"] if step.get("id") == "truth")
    assert truth["env"]["MCP_SMOKE_REQUIRED_INPUT"] == "true"
    assert "MCP_SMOKE_REQUIRED_VAR" not in truth["env"]
    assert "inputs.MCP_PROD_SMOKE_REQUIRED" not in json.dumps(workflow["jobs"])


def test_prod_only_helper_runs_lightweight_tests_without_gateway_pr_build():
    workflow = load_workflow("mcp-sdk-smoke.yml")
    helper = "scripts/ci/mcp_prod_smoke_truth.sh"
    assert not any(fnmatchcase(helper, pattern) for pattern in workflow["on"]["pull_request"]["paths"])
    assert any(fnmatchcase(helper, pattern) for pattern in workflow["on"]["push"]["paths"])
    factory = load_workflow("ai-factory-scripts-tests.yml")
    assert any(fnmatchcase(helper, pattern) for pattern in factory["on"]["pull_request"]["paths"])
