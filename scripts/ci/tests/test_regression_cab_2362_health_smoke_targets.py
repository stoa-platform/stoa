"""Regression tests for CAB-2362: Health Smoke probes the deployed environment."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/ci/resolve-smoke-targets.sh"
WF = ROOT / ".github/workflows"
PROD = "gostoa.dev"


def _resolve(tmp_path: Path, env: str, input_domain: str = "", var_domain: str = ""):
    out = tmp_path / "out"
    out.write_text("")
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        env={
            "PATH": os.environ["PATH"],
            "SMOKE_ENV": env,
            "SMOKE_INPUT_DOMAIN": input_domain,
            "SMOKE_VAR_DOMAIN": var_domain,
            "GITHUB_OUTPUT": str(out),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    outputs = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)
    return proc, outputs


def test_dev_deploy_without_dev_domain_is_skipped_not_prod(tmp_path):
    proc, out = _resolve(tmp_path, "dev")
    assert proc.returncode == 0
    assert out == {"domain": "", "skip": "true"}
    assert "::warning::" in proc.stdout


def test_dev_deploy_never_probes_prod(tmp_path):
    for kw in ({"var_domain": PROD}, {"input_domain": PROD}):
        proc, out = _resolve(tmp_path, "dev", **kw)
        assert proc.returncode != 0
        assert out.get("domain") != PROD


def test_dev_deploy_uses_dev_variable(tmp_path):
    proc, out = _resolve(tmp_path, "dev", var_domain="dev.example.org")
    assert proc.returncode == 0
    assert out == {"domain": "dev.example.org", "skip": "false"}


def test_prod_deploy_probes_prod_by_default(tmp_path):
    proc, out = _resolve(tmp_path, "prod")
    assert proc.returncode == 0
    assert out == {"domain": PROD, "skip": "false"}


def test_precedence_input_over_variable(tmp_path):
    _, out = _resolve(tmp_path, "prod", input_domain="a.example.org", var_domain="b.example.org")
    assert out["domain"] == "a.example.org"
    _, out = _resolve(tmp_path, "prod", var_domain="b.example.org")
    assert out["domain"] == "b.example.org"


@pytest.mark.parametrize("bad", [".".join(["10"] * 4), "host:8080", "localhost", "a.b/c"])
def test_rejects_ip_and_non_public_names(tmp_path, bad):
    proc, _ = _resolve(tmp_path, "prod", var_domain=bad)
    assert proc.returncode != 0


def test_unknown_environment_fails(tmp_path):
    proc, _ = _resolve(tmp_path, "staging")
    assert proc.returncode != 0


@pytest.mark.parametrize("name", ["stoa-portal-ci.yml", "control-plane-ui-ci.yml", "stoa-gateway-ci.yml"])
def test_smoke_environment_matches_deploy_environment(name):
    jobs = yaml.safe_load((WF / name).read_text())["jobs"]
    deploy_env = jobs["deploy"]["with"]["environment"]
    smoke = jobs["smoke-test"]
    assert smoke["with"]["environment"] == deploy_env
    assert "base-domain" not in smoke["with"]
    assert "inputs.environment == 'prod'" not in str(smoke.get("if", ""))


def test_no_hard_coded_host_outside_derived_default():
    wf = (WF / "reusable-health-smoke.yml").read_text()
    assert PROD not in wf
    assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", wf)
    script_hits = [l for l in SCRIPT.read_text().splitlines() if PROD in l and not l.lstrip().startswith("#")]
    assert script_hits == [f'PROD_DEFAULT_DOMAIN="{PROD}"']
    assert "continue-on-error" not in wf
