"""Security scans select changed build contexts and fail closed on invalid diffs."""

from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / ".github/scripts/security-scan-changes.py"
COMPONENTS = ("control-plane-api", "portal", "stoa-gateway", "control-plane-ui")


def select(event: str, paths: list[str]) -> list[str]:
    return runpy.run_path(str(SCRIPT))["select_components"](event, paths)


def test_regression_scan_metadata_passes_image_pinning_guard() -> None:
    findings = runpy.run_path(str(ROOT / "scripts/ci/check_image_pinning.py"))["findings"]
    for path in (SCRIPT, Path(__file__)):
        assert findings(path.relative_to(ROOT).as_posix(), path.read_text()) == []


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["README.md", "docs/guide.mdx", "portal/README.md", "portal/docs/guide.mdx",
          "portal/docs/diagram.png", "stoa-gateway/CLAUDE.md", "shared/README.md", ".claude/docs/ci.md"], []),
        (["control-plane-api/src/app.py"], ["control-plane-api"]),
        (["stoa-gateway/src/main.rs"], ["stoa-gateway"]),
        (["portal/src/App.tsx"], ["portal"]),
        (["control-plane-ui/nginx.conf.template"], ["control-plane-ui"]),
        (["shared/package-lock.json"], ["portal", "control-plane-ui"]),
        (["shared/src/index.ts", "tsconfig.base.json"], ["portal", "control-plane-ui"]),
        (["other-component/Dockerfile"], []),
    ],
)
def test_pr_context_selection(paths: list[str], expected: list[str]) -> None:
    assert select("pull_request", paths) == expected


@pytest.mark.parametrize("component", COMPONENTS)
@pytest.mark.parametrize("file", ("Dockerfile", "package.json", "package-lock.json",
                                  "Cargo.toml", "Cargo.lock", "requirements.txt"))
def test_manifests_and_dockerfiles(component: str, file: str) -> None:
    assert select("pull_request", [f"{component}/{file}"]) == [component]


@pytest.mark.parametrize("path", (
    "LICENSE", "NOTICE", ".dockerignore", "scripts/ci/release_legal.py",
    ".github/workflows/security-scan.yml", ".github/scripts/security-scan-changes.py",
    "scripts/ci/tests/test_security_scan_paths.py",
))
def test_global_build_inputs_select_all(path: str) -> None:
    assert select("pull_request", [path]) == list(COMPONENTS)


@pytest.mark.parametrize("event", ("merge_group", "push", "schedule", "workflow_dispatch"))
def test_non_pr_events_scan_every_component(event: str) -> None:
    assert select(event, ["docs/only.md"]) == list(COMPONENTS)
    assert runpy.run_path(str(SCRIPT))["select_components"](
        event, ["docs/only.md"], sast=True) == list(COMPONENTS)


@pytest.mark.parametrize(("path", "expected"), (
    ("README.md", []), ("portal/docs/guide.mdx", []),
    ("stoa-gateway/docs/example.rs", ["stoa-gateway"]),
    ("control-plane-api/docs/example.py", ["control-plane-api"]),
    ("portal/src/App.tsx", ["portal"]),
    ("shared/src/index.ts", ["portal", "control-plane-ui"]),
))
def test_sast_preserves_executable_documentation(path: str, expected: list[str]) -> None:
    assert runpy.run_path(str(SCRIPT))["select_components"](
        "pull_request", [path], sast=True) == expected


@pytest.mark.parametrize("path", (
    ".github/workflows/ci-gate.yml", ".github/workflows/security-scan.yml",
    ".github/scripts/security-scan-changes.py", "scripts/ci/tests/test_security_scan_paths.py",
    "pyproject.toml", ".bandit", ".eslintrc.cjs", "eslint.config.mjs",
    ".cargo/config.toml", "rust-toolchain.toml", "Cargo.lock", ".clippy.toml",
))
def test_sast_configuration_changes_scan_all(path: str) -> None:
    assert runpy.run_path(str(SCRIPT))["select_components"](
        "pull_request", [path], sast=True) == list(COMPONENTS)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout.strip()


def commit(repo: Path) -> str:
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=CI", "-c", "user.email=ci@example.com",
        "-c", "commit.gpgsign=false", "commit", "-m", "fixture")
    return git(repo, "rev-parse", "HEAD")


def test_cli_diff_add_delete_rename_and_invalid_sha(tmp_path: Path) -> None:
    git(tmp_path, "init", "-b", "main")
    for name in ("control-plane-api/src/old.py", "stoa-gateway/src/old.rs"):
        path = tmp_path / name
        path.parent.mkdir(parents=True)
        path.write_text("seed\n", encoding="utf-8")
    base = commit(tmp_path)
    destination = tmp_path / "control-plane-ui/src/renamed.ts"
    destination.parent.mkdir(parents=True)
    git(tmp_path, "mv", "control-plane-api/src/old.py", str(destination))
    (tmp_path / "stoa-gateway/src/old.rs").unlink()
    added = tmp_path / "portal/src/café new.ts"
    added.parent.mkdir(parents=True)
    added.write_text("added\n", encoding="utf-8")
    head = commit(tmp_path)
    output = tmp_path / "outputs"
    env = dict(os.environ, EVENT_NAME="pull_request", BASE_SHA=base, HEAD_SHA=head,
               GITHUB_OUTPUT=str(output))
    proc = subprocess.run(["python3", str(SCRIPT)], cwd=tmp_path, env=env,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    flags = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert all(flags[name] == "true" for name in (
        *COMPONENTS, "container-scan", "sast-rust", "sast-python", "sast-javascript"))
    assert json.loads(flags["container-matrix"]) == {"component": [
        {"name": name, "path": name,
         "context": "." if name in ("portal", "control-plane-ui") else name}
        for name in COMPONENTS]}
    output.unlink()
    env["BASE_SHA"] = "invalid-sha"
    failed = subprocess.run(["python3", str(SCRIPT)], cwd=tmp_path, env=env,
                            capture_output=True, text=True)
    assert failed.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize("target", (
    "dependency-scan", "container-scan", "sast-rust", "sast-python", "sast-javascript",
))
@pytest.mark.parametrize(("flag", "detector", "scan", "success"), (
    ("false", "success", "skipped", True), ("true", "success", "success", True),
    ("false", "failure", "skipped", False), ("invalid", "success", "skipped", False),
    ("true", "success", "failure", False), ("true", "success", "cancelled", False),
    ("true", "success", "skipped", False),
))
def test_scan_summary(target: str, flag: str, detector: str, scan: str, success: bool) -> None:
    job = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]["scan-summary"]
    assert job["if"] == "always()"
    scans = ("dependency-scan", "container-scan", "sast-rust", "sast-python", "sast-javascript")
    needs = {name: {"result": "success" if flag == "true" else "skipped"} for name in scans}
    needs["scan-changes"] = {"result": detector, "outputs": {
        name: flag for name in scans if name != "dependency-scan"}}
    needs[target]["result"] = scan
    proc = subprocess.run(["bash", "-c", job["steps"][0]["run"]], capture_output=True,
                          env=dict(os.environ, RESULTS=json.dumps(needs)))
    assert (proc.returncode == 0) is success


def test_workflow_enforces_selected_sast_and_keeps_unconditional_scans() -> None:
    jobs = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]
    for scan in ("sast-rust", "sast-python", "sast-javascript"):
        assert jobs[scan]["needs"] == "scan-changes"
        assert jobs[scan]["if"] == f"needs.scan-changes.outputs.{scan} == 'true'"
        assert scan in jobs["scan-summary"]["needs"]
        assert jobs["scan-changes"]["outputs"][scan] == f"${{{{ steps.diff.outputs.{scan} }}}}"
    for scan in ("secret-scan", "opsec-scan"):
        assert "if" not in jobs[scan]
    install = next(s for s in jobs["dependency-scan"]["steps"] if s["name"] == "Install cargo-audit")
    assert install["with"] == {"tool": "cargo-audit@0.22.2", "fallback": "none"}
    assert install["uses"].startswith("taiki-e/install-action@")


def test_web_filters_share_all_sast_inputs_and_exclude_prose() -> None:
    module = runpy.run_path(str(SCRIPT))
    filters = module["web_filters"]()
    assert set(filters) == {"portal", "control-plane-ui"}
    for component, rules in filters.items():
        assert rules[0].startswith("{") and rules[0].endswith("}")
        paths = set(rules[0][1:-1].split(","))
        assert paths == {
            f"{component}/**", "shared/**", "tsconfig.base.json", ".cargo/**",
            *module["COMMON"], *module["SAST_COMMON"],
        }
        assert rules[1:] == ["!**/*.{md,mdx}", "!.claude/**"]


def test_web_scans_keep_check_names_and_full_non_pr_runs() -> None:
    jobs = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]
    detector = jobs["scan-changes"]
    web = next(step for step in detector["steps"] if step.get("id") == "web")
    assert web["uses"] == "dorny/paths-filter@0e4a8c6effa4802afeda77dc8d303f8176d7dfad"
    assert web["if"] == "github.event_name == 'pull_request'"
    assert web["with"]["token"] == ""
    assert web["with"]["predicate-quantifier"] == "every"
    assert web["with"]["filters"] == "${{ steps.diff.outputs.web-filters }}"
    for component in ("portal", "control-plane-ui"):
        assert detector["outputs"][f"sast-{component}"] == f"${{{{ steps.web.outputs.{component} }}}}"
    validation = next(step for step in detector["steps"]
                      if step["name"] == "Validate JavaScript filter outputs")
    for value, success in (("true", True), ("false", True), ("", False), ("invalid", False)):
        proc = subprocess.run(["bash", "-c", validation["run"]],
                              env=dict(os.environ, UI_CHANGED=value, PORTAL_CHANGED=value))
        assert (proc.returncode == 0) is success
    scan = jobs["sast-javascript"]
    assert scan["name"] == "SAST JavaScript (ESLint)"
    assert scan["strategy"]["matrix"]["project"] == ["control-plane-ui", "portal"]
    check = next(step for step in scan["steps"] if step.get("id") == "check")
    assert check["if"] == (
        "github.event_name != 'pull_request' || "
        "needs.scan-changes.outputs[format('sast-{0}', matrix.project)] == 'true'"
    )
    for name in ("Install dependencies", "Install ESLint security plugin",
                 "Run ESLint security report (non-blocking)", "Run ESLint security gate (blocking)"):
        assert next(step for step in scan["steps"] if step["name"] == name)["if"] == (
            "steps.check.outputs.exists == 'true'"
        )


@pytest.mark.parametrize(("name", "directory", "command"), (
    ("Cargo audit", "stoa-gateway", "cargo audit"),
    ("Pip audit — control-plane-api", None, None),
    ("NPM audit — control-plane-ui", "control-plane-ui", "npm audit --audit-level=high --omit=dev"),
    ("NPM audit — portal", "portal", "npm audit --audit-level=high --omit=dev"),
))
def test_regression_dependency_findings_are_blocking(
    name: str, directory: str | None, command: str | None,
) -> None:
    job = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]["dependency-scan"]
    step = next(step for step in job["steps"] if step["name"] == name)
    assert not job.get("continue-on-error", False)
    assert not step.get("continue-on-error", False)
    assert step.get("working-directory") == directory
    assert "||" not in step["run"]
    assert "if [" not in step["run"]
    if command:
        assert step["run"].strip() == command
    else:
        assert "pip-audit -r control-plane-api/requirements.txt --desc" in step["run"]
        assert "--ignore-vuln CVE-2024-23342" in step["run"]


def test_regression_selected_dependency_audits_run_after_earlier_failure() -> None:
    job = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]["dependency-scan"]
    for step in job["steps"]:
        if step["name"] != "Checkout repository":
            assert step["if"].startswith("${{ !cancelled() && ")
            assert "needs.scan-changes.outputs." in step["if"]
    node = next(step for step in job["steps"] if step["name"] == "Set up Node.js")
    assert node["if"] == (
        "${{ !cancelled() && (needs.scan-changes.outputs.control-plane-ui == 'true' || "
        "needs.scan-changes.outputs.portal == 'true') }}"
    )


def test_regression_trivy_high_critical_findings_are_blocking() -> None:
    job = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]["container-scan"]
    assert not job.get("continue-on-error", False)
    scans = [step for step in job["steps"] if step.get("uses", "").startswith("aquasecurity/trivy-action@")]
    assert len(scans) == 3
    for step in scans:
        assert not step.get("continue-on-error", False)
        assert step["with"]["vuln-type"] == "os,library"
    report = next(step for step in scans if step["name"] == "Run Trivy (SARIF)")
    assert report["with"]["format"] == "sarif"
    assert report["with"]["severity"] == "CRITICAL,HIGH"
    assert report["with"]["ignore-unfixed"] is False
    assert report["with"]["exit-code"] == "0"
    upload = next(step for step in job["steps"] if step["name"] == "Upload to GitHub Security")
    assert upload["continue-on-error"] is True
    assert upload["with"]["sarif_file"] == report["with"]["output"]
    gates = (
        ("Run Trivy (fail on fixable HIGH+)", "CRITICAL,HIGH", True),
        ("Run Trivy (fail on any CRITICAL)", "CRITICAL", False),
    )
    for name, severity, ignore_unfixed in gates:
        gate = next(step for step in scans if step["name"] == name)
        assert gate["with"]["severity"] == severity
        assert gate["with"]["ignore-unfixed"] is ignore_unfixed
        assert gate["with"]["exit-code"] == "1"
        assert gate["if"] == "${{ !cancelled() && steps.check.outputs.exists == 'true' }}"


@pytest.mark.parametrize("name", (
    "Run Trivy (SARIF)",
    "Run Trivy (fail on fixable HIGH+)",
    "Run Trivy (fail on any CRITICAL)",
))
def test_regression_trivy_cannot_load_repository_ignorefiles(name: str) -> None:
    job = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]["container-scan"]
    step = next(step for step in job["steps"] if step["name"] == name)
    # An empty action input alone still lets Trivy load .trivyignore by default.
    assert step["env"]["TRIVY_IGNOREFILE"] == "/dev/null"
    assert Path(step["env"]["TRIVY_IGNOREFILE"]).read_bytes() == b""
    # A nonempty action input would override the explicit environment variable.
    assert not step["with"].get("trivyignores")


@pytest.mark.skipif(shutil.which("trivy") is None, reason="requires the Trivy executable")
@pytest.mark.parametrize("fixed_version", ("", "1.1"))
def test_regression_trivy_critical_ignorefile_bypass(tmp_path: Path, fixed_version: str) -> None:
    job = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]["container-scan"]
    gate = next(step for step in job["steps"] if step["name"] == "Run Trivy (fail on any CRITICAL)")
    finding = {"VulnerabilityID": "TEST-CRITICAL", "PkgName": "fixture",
               "InstalledVersion": "1.0", "FixedVersion": fixed_version, "Severity": "CRITICAL"}
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"SchemaVersion": 2, "ArtifactName": "fixture",
                                 "ArtifactType": "container_image", "Results": [
                                     {"Target": "fixture", "Class": "lang-pkgs", "Type": "npm",
                                      "Vulnerabilities": [finding]}]}))
    (tmp_path / ".trivyignore").write_text("TEST-CRITICAL\n")
    command = ["trivy", "convert", "--format", "json", "--severity", gate["with"]["severity"],
               "--exit-code", gate["with"]["exit-code"], str(report)]
    env = {key: value for key, value in os.environ.items() if not key.startswith("TRIVY_")}
    # Replay the same finding without a database or container runtime.
    baseline = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
    assert baseline.returncode == 0, baseline.stderr
    assert not json.loads(baseline.stdout)["Results"][0].get("Vulnerabilities")
    protected = subprocess.run(command, cwd=tmp_path, env={**env, **gate["env"]},
                               capture_output=True, text=True)
    assert protected.returncode == 1, protected.stderr
    assert json.loads(protected.stdout)["Results"][0]["Vulnerabilities"][0]["VulnerabilityID"] == "TEST-CRITICAL"


@pytest.mark.parametrize("exists", (False, True))
def test_regression_container_requires_dockerfile(tmp_path: Path, exists: bool) -> None:
    job = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]["container-scan"]
    check = next(step for step in job["steps"] if step.get("id") == "check")
    if exists:
        (tmp_path / "fixture").mkdir()
        (tmp_path / "fixture/Dockerfile").write_text("FROM scratch\n")
    output = tmp_path / "output"
    script = check["run"].replace("${{ matrix.component.path }}", "fixture").replace(
        "${{ matrix.component.name }}", "fixture")
    proc = subprocess.run(["bash", "-e", "-o", "pipefail", "-c", script], cwd=tmp_path,
                          env=dict(os.environ, GITHUB_OUTPUT=str(output)), capture_output=True, text=True)
    assert (proc.returncode == 0) is exists
    if exists:
        assert output.read_text().strip() == "exists=true"
    else:
        assert "::error::" in proc.stdout
