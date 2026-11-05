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


def _resolve(
    tmp_path: Path,
    env: str,
    input_domain: str = "",
    var_domain: str = "",
    *,
    with_summary: bool = False,
    prod_domain: str = "",
):
    out = tmp_path / "out"
    out.write_text("")
    process_env = {
        "PATH": os.environ["PATH"],
        "SMOKE_ENV": env,
        "SMOKE_INPUT_DOMAIN": input_domain,
        "SMOKE_VAR_DOMAIN": var_domain,
        "SMOKE_PROD_DOMAIN": prod_domain,
        "GITHUB_OUTPUT": str(out),
    }
    if with_summary:
        summary = tmp_path / "summary"
        summary.write_text("")
        process_env["GITHUB_STEP_SUMMARY"] = str(summary)
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )
    outputs = dict(l.split("=", 1) for l in out.read_text().splitlines() if "=" in l)
    return proc, outputs


@pytest.mark.parametrize("with_summary", [False, True])
def test_dev_deploy_without_dev_domain_is_skipped_not_prod(tmp_path, with_summary):
    proc, out = _resolve(tmp_path, "dev", with_summary=with_summary)
    assert proc.returncode == 0
    assert out == {"domain": "", "skip": "true"}
    assert "::warning::SKIPPED, no dev target" in proc.stdout
    assert "success" not in proc.stdout.lower()
    if with_summary:
        summary = (tmp_path / "summary").read_text()
        assert "SKIPPED, no dev target" in summary
        assert "success" not in summary.lower()


@pytest.mark.parametrize("domain", [PROD, f"dev.{PROD}", f"preview.dev.{PROD}"])
@pytest.mark.parametrize("source", ["input_domain", "var_domain"])
def test_dev_deploy_never_probes_prod_or_its_subdomains(tmp_path, domain, source):
    proc, out = _resolve(tmp_path, "dev", with_summary=True, **{source: domain})
    assert proc.returncode != 0
    assert "::error::" in proc.stdout + proc.stderr
    assert out == {}
    assert domain not in proc.stdout + proc.stderr + (tmp_path / "summary").read_text()


@pytest.mark.parametrize("domain", ["dev.example.org", "preview.example.dev"])
@pytest.mark.parametrize("source", ["input_domain", "var_domain"])
def test_dev_deploy_accepts_public_domain(tmp_path, domain, source):
    proc, out = _resolve(tmp_path, "dev", **{source: domain})
    assert proc.returncode == 0
    assert out == {"domain": domain, "skip": "false"}


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


@pytest.mark.parametrize(
    "suffix",
    [
        "local",
        "localhost",
        "internal",
        "intranet",
        "lan",
        "home",
        "corp",
        "home.arpa",
        "svc",
        "cluster.local",
        "test",
        "example",
        "invalid",
    ],
)
@pytest.mark.parametrize("source", ["input_domain", "var_domain"])
def test_rejects_reserved_suffixes_before_logging_or_outputs(tmp_path, suffix, source):
    domain = f"smoke.{suffix}"
    proc, out = _resolve(tmp_path, "prod", with_summary=True, **{source: domain})
    assert proc.returncode != 0
    assert "::error::" in proc.stdout + proc.stderr
    assert out == {}
    assert domain not in proc.stdout + proc.stderr + (tmp_path / "summary").read_text()


@pytest.mark.parametrize("domain", ["smoke", "smoke.unregistered-tld"])
@pytest.mark.parametrize("source", ["input_domain", "var_domain"])
def test_rejects_names_without_public_tld_before_logging_or_outputs(tmp_path, domain, source):
    proc, out = _resolve(tmp_path, "prod", with_summary=True, **{source: domain})
    assert proc.returncode != 0
    assert "::error::" in proc.stdout + proc.stderr
    assert out == {}
    assert domain not in proc.stdout + proc.stderr + (tmp_path / "summary").read_text()


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


@pytest.mark.parametrize("domain", ["prod.example.com", "dev.prod.example.com", "preview.dev.prod.example.com"])
@pytest.mark.parametrize("source", ["input_domain", "var_domain"])
def test_dev_rejects_configured_prod_domain_and_subdomains(tmp_path, domain, source):
    proc, out = _resolve(
        tmp_path, "dev", prod_domain="prod.example.com", with_summary=True, **{source: domain}
    )
    assert proc.returncode != 0
    assert "::error::" in proc.stdout
    assert out == {}
    assert domain not in proc.stdout + proc.stderr + (tmp_path / "summary").read_text()


@pytest.mark.parametrize("prod_domain", ["PROD.EXAMPLE.COM", "prod.example.com.", " PROD.EXAMPLE.COM. "])
@pytest.mark.parametrize("domain", ["prod.example.com", "PROD.EXAMPLE.COM", " prod.example.com. "])
@pytest.mark.parametrize("prefix", ["", "preview."])
@pytest.mark.parametrize("source", ["input_domain", "var_domain"])
def test_dev_rejects_equivalent_configured_prod_domains(tmp_path, prod_domain, domain, prefix, source):
    candidate = f"{prefix}{domain.strip()}"
    proc, out = _resolve(
        tmp_path, "dev", prod_domain=prod_domain, with_summary=True, **{source: f" {candidate} "}
    )
    assert proc.returncode != 0
    assert "refusing to probe prod" in proc.stdout
    assert out == {}
    assert "Smoke targets:" not in proc.stdout
    assert (tmp_path / "summary").read_text() == ""


@pytest.mark.parametrize("source", ["input_domain", "var_domain"])
def test_dev_accepts_canonicalized_distinct_domain(tmp_path, source):
    proc, out = _resolve(
        tmp_path, "dev", prod_domain=" PROD.EXAMPLE.COM. ", **{source: " DEV.EXAMPLE.COM. "}
    )
    assert proc.returncode == 0
    assert out == {"domain": "dev.example.com", "skip": "false"}


@pytest.mark.parametrize("domain", [PROD, f"dev.{PROD}", f"preview.dev.{PROD}"])
def test_configured_prod_does_not_replace_default_guard(tmp_path, domain):
    proc, out = _resolve(tmp_path, "dev", input_domain=domain, prod_domain="prod.example.com")
    assert proc.returncode != 0
    assert out == {}


@pytest.mark.parametrize("domain", ["dev.example.com", "notprod.example.com", "prod.example.com.example.org"])
def test_configured_prod_guard_allows_distinct_dev_domains(tmp_path, domain):
    proc, out = _resolve(tmp_path, "dev", var_domain=domain, prod_domain="prod.example.com")
    assert proc.returncode == 0
    assert out == {"domain": domain, "skip": "false"}


def test_workflow_passes_configured_prod_domain_to_resolver():
    job = yaml.safe_load((WF / "reusable-health-smoke.yml").read_text())["jobs"]["health-check"]
    assert job["env"]["SMOKE_PROD_DOMAIN"] == "${{ vars.SMOKE_BASE_DOMAIN_PROD }}"
