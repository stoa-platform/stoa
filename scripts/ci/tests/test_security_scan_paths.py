"""Security scans select changed build contexts and fail closed on invalid diffs."""

from __future__ import annotations

import json
import os
import re
import runpy
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

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
    scans = ("dependency-scan", "container-scan", "sast-rust", "sast-python", "sast-javascript")
    needs = {name: {"result": "success" if flag == "true" else "skipped"} for name in scans}
    needs["secret-guard"] = {"result": "success"}
    needs["scan-changes"] = {"result": detector, "outputs": {
        name: flag for name in scans if name != "dependency-scan"}}
    needs[target]["result"] = scan
    _require(_scan_summary_passes(needs) is success, "unexpected Scan results status")


@pytest.mark.parametrize(("guard", "success"), (
    ("success", True), ("failure", False), ("cancelled", False), ("skipped", False), (None, False),
))
def test_scan_summary_requires_secret_guard_success(guard: str | None, success: bool) -> None:
    scans = ("dependency-scan", "container-scan", "sast-rust", "sast-python", "sast-javascript")
    needs = {name: {"result": "skipped"} for name in scans}
    needs["scan-changes"] = {"result": "success", "outputs": {
        name: "false" for name in scans if name != "dependency-scan"}}
    if guard is not None:
        needs["secret-guard"] = {"result": guard}
    _require(_scan_summary_passes(needs) is success, "Scan results must follow secret-guard")


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
    for name in ("Install dependencies",
                 "Run ESLint security report (non-blocking)", "Run ESLint security gate (blocking)"):
        assert next(step for step in scan["steps"] if step["name"] == name)["if"] == (
            "steps.check.outputs.exists == 'true'"
        )
    # The ESLint security plugin comes from the lockfile (npm ci), never from an
    # unpinned `npm install` (OpenSSF Scorecard Pinned-Dependencies).
    for step in scan["steps"]:
        assert "npm install" not in step.get("run", ""), step["name"]
    for component in ("portal", "control-plane-ui"):
        manifest = json.loads((ROOT / component / "package.json").read_text())
        assert "eslint-plugin-security" in manifest["devDependencies"], component
        lock = json.loads((ROOT / component / "package-lock.json").read_text())
        assert "node_modules/eslint-plugin-security" in lock["packages"], component


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
        assert "pip-audit -r control-plane-api/requirements-lock.txt --desc" in step["run"]
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


@pytest.mark.parametrize("component", COMPONENTS)
def test_regression_scan_never_reuses_a_cached_os_package_stage(component: str) -> None:
    """A cached `apk upgrade` layer kept a fixed CVE (libxslt, CVE-2026-87636) in the scanned image."""
    job = yaml.safe_load((ROOT / ".github/workflows/security-scan.yml").read_text())["jobs"]["container-scan"]
    build = next(step for step in job["steps"] if step.get("name") == "Build image for scanning")["with"]
    if f"== '{component}'" in build["no-cache"]:
        return  # the whole build ignores the cache
    assert f'"{component}"' in build["no-cache-filters"]
    assert "'runtime'" in build["no-cache-filters"]
    dockerfile = (ROOT / component / "Dockerfile").read_text()
    assert re.search(r"^FROM \S+ AS runtime$", dockerfile, flags=re.M)
    # OS packages are installed in the last stage: it must be the one rebuilt.
    assert "\nFROM " not in dockerfile.split(" AS runtime\n", 1)[1]


# --------------------------------------------------------------------------------------
# Secret guard job. Failure messages below are fixed strings: workflow values, fixture
# values and captured output are never rendered.
# --------------------------------------------------------------------------------------

SECURITY_WORKFLOW = ".github/workflows/security-scan.yml"
GATE_WORKFLOW = ".github/workflows/ci-gate.yml"
GUARD_SCRIPT = "scripts/ci/precommit_secrets.py"
RANGE_MARKER = "RANGE_MODE_SUPPORTED = True"
NO_COMMIT = "0" * 40
TIMEOUT = 60
SELECT, CANDIDATE, RUN, CONFIRM = GUARD_STEPS = (
    "Select commit range",
    "Checkout candidate revision",
    "Run secret guard on commit range",
    "Confirm there is no commit range to scan",
)
SCAN_STEPS = [SELECT, CANDIDATE, RUN]
SCANNED, SKIPPED = "steps.range.outputs.scan == 'true'", "steps.range.outputs.scan != 'true'"
GUARD_ERROR = "::error::Secret guard: "
NO_IDS = GUARD_ERROR + "the event does not provide two full commit ids\n"
UNSUPPORTED = GUARD_ERROR + "unsupported event\n"
NO_BASE = GUARD_ERROR + "the protected base revision does not resolve to a commit\n"
NO_TEMP = GUARD_ERROR + "unable to create a temporary directory\n"
NO_SCANNER = GUARD_ERROR + "unable to read the scanner from the protected base revision\n"
NO_RANGE_MODE = GUARD_ERROR + "the scanner of the protected base revision has no range mode\n"
NO_MODE = GUARD_ERROR + "unknown scan mode\n"
NO_DECISION = GUARD_ERROR + "the commit range selection gave no decision\n"
CONFIRMED = "Secret guard: no checkout and no scan for this event\n"
DELETED = "::notice::Secret guard: branch deletion, no commit to scan\n" + CONFIRMED
CREATED = "::notice::Secret guard: branch creation, no prior revision to compare with\n" + CONFIRMED
NO_RANGE = "Secret guard: this event has no commit range, nothing to scan\n" + CONFIRMED
FOUND = ". Remove sensitive data from the range.\n"
CLOSED = ". Range scan failed closed.\n"
# The scanner is the base revision blob, written outside the checkout; every command that
# could print git output or file content has its output redirected.
EXTRACTION = (
    'git rev-parse --verify --quiet "${BASE_SHA}^{commit}" >/dev/null 2>&1 \\',
    '|| fail "the protected base revision does not resolve to a commit"',
    'scanner_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/secret-guard.XXXXXX" 2>/dev/null)" \\',
    '|| fail "unable to create a temporary directory"',
    "trap 'rm -rf -- \"$scanner_dir\"' EXIT",
    'scanner="$scanner_dir/precommit_secrets.py"',
    f'git show "${{BASE_SHA}}:{GUARD_SCRIPT}" >"$scanner" 2>/dev/null \\',
    '|| fail "unable to read the scanner from the protected base revision"',
    f"grep -qxF -- '{RANGE_MARKER}' \"$scanner\" 2>/dev/null \\",
    '|| fail "the scanner of the protected base revision has no range mode"',
)
# Fixture texts that only git output or file content could bring into a step output.
SUBJECT, CONTENT = "fixture commit subject", "fixture file content"
LEAKS = (SUBJECT, CONTENT, GUARD_SCRIPT, "fatal:")


def _require(condition: object, message: str) -> None:
    if not condition:
        pytest.fail(message, pytrace=False)


def _run(command: list[str], cwd: Path, env: dict[str, str],
         stdin: str = "") -> subprocess.CompletedProcess[str]:
    """Run a command with captured output; a timeout is a fixed failure."""
    try:
        return subprocess.run(command, cwd=cwd, env=env, input=stdin, capture_output=True,
                              text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        pass
    pytest.fail("fixture command timed out", pytrace=False)


def _fixture_env(home: Path) -> dict[str, str]:
    """Environment without the caller's Git, Python or workflow settings."""
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("GIT_", "GITHUB_", "PYTHON"))}
    env.update(HOME=str(home), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    for role in ("AUTHOR", "COMMITTER"):
        env.update({f"GIT_{role}_NAME": "CI", f"GIT_{role}_EMAIL": "ci@example.invalid"})
    return env


def _workflow_jobs(relative: str) -> dict:
    try:
        loaded = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        loaded = None
    jobs = loaded.get("jobs") if isinstance(loaded, dict) else None
    _require(isinstance(jobs, dict), "workflow jobs cannot be loaded")
    return jobs


def _steps(relative: str, job: str) -> list[dict]:
    body = _workflow_jobs(relative).get(job)
    steps = body.get("steps") if isinstance(body, dict) else None
    _require(isinstance(steps, list) and all(isinstance(step, dict) for step in steps),
             "workflow job steps cannot be loaded")
    return steps


def _script_lines(step: dict) -> list[str]:
    """Stripped lines of a step script, without blank lines and comments."""
    _require(isinstance(step.get("run"), str), "step has no script")
    _require("${{" not in step["run"], "a step script must not inline workflow expressions")
    lines = [line.strip() for line in step["run"].splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def _scan_summary_passes(needs: dict) -> bool:
    """Run the Scan results step on a `needs` context."""
    job = _workflow_jobs(SECURITY_WORKFLOW).get("scan-summary") or {}
    _require(job.get("name") == "Scan results" and job.get("if") == "always()",
             "Scan results must keep its name and always run")
    steps = _steps(SECURITY_WORKFLOW, "scan-summary")
    _require(len(steps) == 1 and isinstance(steps[0].get("run"), str),
             "Scan results must be one script step")
    env = {**os.environ, "RESULTS": json.dumps(needs)}
    return _run(["bash", "-c", steps[0]["run"]], ROOT, env).returncode == 0


def _operand(token: str, context: dict[str, str]) -> str:
    if len(token) > 1 and token[0] == token[-1] == "'":
        return token[1:-1]
    _require(token.startswith(("github.", "steps.")), "unsupported workflow expression")
    return context.get(token, "")


def _evaluate(expression: str, context: dict[str, str]) -> str:
    """Evaluate the workflow expression subset the guard job uses: a value, == and !=."""
    found = re.fullmatch(r"\s*([\w.'-]+)\s*(?:(==|!=)\s*([\w.'-]+)\s*)?", expression)
    _require(found, "unsupported workflow expression")
    left, operator, right = found.groups()
    value = _operand(left, context)
    if operator:
        equal = value == _operand(right, context)
        value = "true" if equal is (operator == "==") else ""
    return value


def _render(value: object, context: dict[str, str]) -> str:
    """Substitute the expressions of a workflow value, an absent field being empty."""
    return re.sub(r"\$\{\{(.*?)\}\}", lambda found: _evaluate(found.group(1), context),
                  str(value), flags=re.S)


def _run_script(step: dict, workspace: Path, env: dict[str, str],
                context: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run a step script as the runner starts `shell: bash`, with its rendered environment."""
    variables = {name: _render(value, context) for name, value in step.get("env", {}).items()}
    command = ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]]
    return _run(command, workspace / step.get("working-directory", "."), {**env, **variables})


def _checkout(step: dict, origin: Path, workspace: Path, env: dict[str, str],
              revision: str) -> bool:
    """Stand in for the checkout action: full history of every branch, at the tested revision."""
    path = str(workspace / step.get("with", {}).get("path", "."))
    commands = (
        ["init", "-q", path],
        ["-C", path, "fetch", "-q", str(origin), "+refs/heads/*:refs/remotes/origin/*"],
        ["-C", path, "checkout", "-q", "--detach", revision],
    )
    return all(_run(["git", *command], workspace, env).returncode == 0 for command in commands)


class GuardRun(NamedTuple):
    passed: bool
    output: str
    steps: list[str]


def _run_guard_job(origin: Path, root: Path, env: dict[str, str],
                   event: dict[str, str]) -> GuardRun:
    """Run the secret-guard steps in order for one event, as the runner would.

    `root` receives the job workspace and, next to it, the runner temporary directory.
    """
    workspace, temp, outputs = root / "workspace", root / "temp", root / "step-outputs"
    for directory in (root, workspace, temp):
        directory.mkdir()
    context = dict(event)
    # A hostile PYTHONPATH: isolated mode must keep candidate modules out of the scanner.
    env = {**env, "GITHUB_OUTPUT": str(outputs), "RUNNER_TEMP": str(temp),
           "PYTHONPATH": str(workspace / "candidate")}
    ran, output = [], ""
    for step in _steps(SECURITY_WORKFLOW, "secret-guard"):
        if "if" in step and not _evaluate(step["if"], context):
            continue
        ran.append(step.get("name"))
        if "uses" in step:
            passed = _checkout(step, origin, workspace, env, context.get("github.sha", ""))
        else:
            result = _run_script(step, workspace, env, context)
            passed, output = result.returncode == 0, output + result.stdout + result.stderr
            if outputs.exists():
                for line in outputs.read_text(encoding="utf-8").splitlines():
                    name, _, value = line.partition("=")
                    context[f"steps.{step.get('id')}.outputs.{name}"] = value
                outputs.unlink()
        if not passed:
            return GuardRun(False, output, ran)
    return GuardRun(True, output, ran)


class GuardOrigin(NamedTuple):
    path: Path
    env: dict[str, str]
    commits: dict[str, str]
    sentinels: tuple[Path, ...]
    record: Path


@pytest.fixture(scope="module")
def guard_origin(tmp_path_factory: pytest.TempPathFactory) -> GuardOrigin:
    """Repository the guard job checks out from; candidate revisions carry a hostile scanner."""
    root = tmp_path_factory.mktemp("secret-guard")
    origin, env = root / "origin", _fixture_env(root)
    names = ("candidate-scanner-ran", "candidate-module-ran", "unmarked-scanner-ran")
    sentinels = tuple(root / name for name in names)
    # Each of these records its own execution: none of them may ever run.
    hostile, module, unmarked = (
        f"# {CONTENT}\nimport pathlib\npathlib.Path({str(path)!r}).write_text('ran')\n"
        for path in sentinels)
    # A marked base scanner that records how it was started instead of scanning.
    record = root / "base-scanner-run"
    probe = (f"import json, os, pathlib, sys\n{RANGE_MARKER}\n"
             "run = [os.path.abspath(__file__), os.getcwd(), sys.argv[1:], sys.flags.isolated,\n"
             "       sys.dont_write_bytecode]\n"
             f"pathlib.Path({str(record)!r}).write_text(json.dumps(run))\n")
    real = (ROOT / GUARD_SCRIPT).read_text(encoding="utf-8")
    token = "ghp_" + "A" * 36
    commits: dict[str, str] = {}

    def git(*args: str, stdin: str = "") -> str:
        result = _run(["git", *args], origin, env, stdin)
        _require(result.returncode == 0, "git fixture command failed")
        return result.stdout.strip()

    def commit(name: str, parent: str | None, files: dict[str, str | None],
               message: str = "chore: " + SUBJECT, branch: bool = True) -> None:
        """Record a commit on top of `parent`, kept on a branch of its own unless told not to."""
        if parent is not None:
            git("checkout", "-q", "--detach", commits[parent])
        for file, content in files.items():
            if content is None:
                (origin / file).unlink()
            else:
                (origin / file).parent.mkdir(parents=True, exist_ok=True)
                (origin / file).write_text(content, encoding="utf-8")
        git("add", "-A")
        git("commit", "-q", "--allow-empty", "-F", "-", stdin=message)
        commits[name] = git("rev-parse", "HEAD")
        if branch:
            git("branch", "-f", name, "HEAD")

    origin.mkdir()
    git("init", "-q", "-b", "main")
    commit("base", None, {GUARD_SCRIPT: real, "app.txt": "seed\n", "legacy.txt": token + "\n"})
    # The base branch moves on after the branch point and drops a flagged file.
    commit("advanced", "base", {"legacy.txt": None})
    candidate = {GUARD_SCRIPT: hostile, "fnmatch.py": module, "app.txt": "clean update\n"}
    commit("clean", "base", candidate)
    commit("flagged", "clean", {"app.txt": token + "\n"})
    commit("noted", "clean", {}, f"chore: {SUBJECT}\n\n-----BEGIN " + "RSA PRIVATE KEY-----")
    # A branch moved back from `removed` to `restored` brings a sensitive path back.
    commit("restored", "base", {GUARD_SCRIPT: hostile, "deploy/.env": f"PORT=3000\n{token}\n"})
    commit("removed", "restored", {GUARD_SCRIPT: real, "deploy/.env": None})
    # No branch keeps this commit: a full fetch of the origin does not bring it.
    commit("dropped", "base", {"notes.txt": "temporary\n"}, branch=False)
    commit("bare", "base", {GUARD_SCRIPT: None})
    commit("bare-head", "bare", {GUARD_SCRIPT: hostile})
    commit("probe", "base", {GUARD_SCRIPT: probe})
    commit("probe-head", "probe", {GUARD_SCRIPT: hostile, "fnmatch.py": module})
    # Base revisions whose scanner does not carry the marker as a whole line.
    suffixes = ("", f"# {RANGE_MARKER}\n", f"{RANGE_MARKER}  # note\n", f"if True:\n    {RANGE_MARKER}\n")
    for index, suffix in enumerate(suffixes):
        commit(f"unmarked-{index}", "base", {GUARD_SCRIPT: unmarked + suffix})
        commit(f"unmarked-{index}-head", f"unmarked-{index}", {GUARD_SCRIPT: hostile})
    return GuardOrigin(origin, env, commits, sentinels, record)


def _pull_request(base: str, head: str) -> dict[str, str]:
    return {"github.event_name": "pull_request", "github.sha": head,
            "github.event.pull_request.base.sha": base, "github.event.pull_request.head.sha": head}


def _merge_group(base: str, head: str) -> dict[str, str]:
    return {"github.event_name": "merge_group", "github.sha": head,
            "github.event.merge_group.base_sha": base, "github.event.merge_group.head_sha": head}


def _push(before: str, after: str, sha: str | None = None, created: str = "false",
          deleted: str = "false") -> dict[str, str]:
    return {"github.event_name": "push", "github.sha": sha or after, "github.event.before": before,
            "github.event.after": after, "github.event.created": created,
            "github.event.deleted": deleted}


def _require_fixed_output(shown: str, expected: str, label: str) -> None:
    _require(shown == expected, f"{label}: unexpected output")
    _require(not any(text in shown for text in LEAKS),
             f"{label}: git output or file content was shown")


def _require_no_candidate_code_ran(origin: GuardOrigin) -> None:
    for sentinel in origin.sentinels:
        _require(not sentinel.exists(), "candidate or unmarked scanner code was executed")


def _assert_guard_runs(origin: GuardOrigin, tmp_path: Path, cases: list[tuple]) -> None:
    """Run the job for each (event, passed, output, steps) case; labels are case indexes."""
    for index, (event, passed, output, steps) in enumerate(cases):
        root = tmp_path / f"run-{index}"
        run = _run_guard_job(origin.path, root, origin.env, event)
        _require(run.steps == steps, f"case #{index}: unexpected steps ran")
        _require(run.passed is passed, f"case #{index}: unexpected job status")
        _require_fixed_output(run.output, output, f"case #{index}")
        checkouts = [entry.name for entry in (root / "workspace").iterdir()]
        _require(checkouts == ["candidate"] * (CANDIDATE in steps),
                 f"case #{index}: unexpected checkouts")
        _require(not any((root / "temp").iterdir()),
                 f"case #{index}: the extracted scanner must be removed")
    _require_no_candidate_code_ran(origin)


def test_secret_guard_job_structure() -> None:
    jobs = _workflow_jobs(SECURITY_WORKFLOW)
    job = jobs.get("secret-guard")
    _require(isinstance(job, dict), "secret-guard job is missing")
    _require(job.get("name") == "Secret Guard (Hook Rules)", "secret-guard job name changed")
    _require(job.get("permissions") == {"contents": "read"}, "secret-guard may only read contents")
    timeout = job.get("timeout-minutes")
    _require(isinstance(timeout, int) and 5 <= timeout <= 10, "secret-guard timeout out of bounds")
    _require(not {"if", "needs", "secrets", "continue-on-error"} & set(job),
             "secret-guard must be unconditional and blocking")
    steps = _steps(SECURITY_WORKFLOW, "secret-guard")
    _require([step.get("name") for step in steps] == list(GUARD_STEPS), "unexpected guard steps")
    select, candidate, run, confirm = steps
    _require(not any("continue-on-error" in step for step in steps), "guard steps must be blocking")
    _require([step for step in steps if "uses" in step] == [candidate],
             "the guard must have exactly one checkout, of the candidate revision")
    _require([step.get("if") for step in steps] == [None, SCANNED, SCANNED, SKIPPED],
             "checkout and scan need a selected range; everything else is the explicit no-op")

    # The checkout reuses the one action pin of the workflow, keeps no credentials and
    # names no ref: no other revision is ever checked out.
    pins = {step.get("uses") for name in jobs for step in _steps(SECURITY_WORKFLOW, name)
            if str(step.get("uses")).startswith("actions/checkout@")}
    _require(len(pins) == 1 and re.fullmatch(r"actions/checkout@[0-9a-f]{40}", min(pins)),
             "the workflow must use one pinned checkout action")
    _require(candidate.get("with") == {"path": "candidate", "fetch-depth": 0,
                                       "persist-credentials": False},
             "the candidate checkout must fetch the full history of the tested ref")

    _require(select.get("id") == "range" and select.get("shell") == "bash",
             "the range selection must be a bash step with the id range")
    _require(select.get("env") == {
        "EVENT_NAME": "${{ github.event_name }}",
        "PR_BASE_SHA": "${{ github.event.pull_request.base.sha }}",
        "PR_HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
        "MG_BASE_SHA": "${{ github.event.merge_group.base_sha }}",
        "MG_HEAD_SHA": "${{ github.event.merge_group.head_sha }}",
        "PUSH_BEFORE_SHA": "${{ github.event.before }}",
        "PUSH_AFTER_SHA": "${{ github.event.after }}",
        "PUSH_CREATED": "${{ github.event.created }}",
        "PUSH_DELETED": "${{ github.event.deleted }}",
    }, "event values must reach the range selection through its environment")
    selection = _script_lines(select)
    for index, call in enumerate((
        'scan "$PR_BASE_SHA" "$PR_HEAD_SHA" merge-base',
        'scan "$MG_BASE_SHA" "$MG_HEAD_SHA" merge-base',
        'scan "$PUSH_BEFORE_SHA" "$PUSH_AFTER_SHA" direct',
    )):
        _require(selection.count(call) == 1, f"range selection #{index} is missing")
    _require(sum(line.startswith("scan ") for line in selection) == 3,
             "only pull_request, merge_group and push may select a range")

    _require(run.get("shell") == "bash" and run.get("working-directory") == "candidate",
             "the scan must run with bash inside the candidate checkout")
    _require(run.get("env") == {
        "BASE_SHA": "${{ steps.range.outputs.base }}",
        "HEAD_SHA": "${{ steps.range.outputs.head }}",
        "SCAN_MODE": "${{ steps.range.outputs.mode }}",
    }, "the scan must take its range and mode from the selection alone")
    scan = _script_lines(run)
    command = 'python3 -I -B "$scanner" --range "$BASE_SHA" "$HEAD_SHA"'
    _require([line for line in scan if "python" in line]
             == [command, command + " --direct --allow-empty"],
             "the scanner must run isolated, with --direct --allow-empty for a push only")
    start = scan.index(EXTRACTION[0]) if EXTRACTION[0] in scan else len(scan)
    end = start + len(EXTRACTION)
    _require(tuple(scan[start:end]) == EXTRACTION and command in scan[end:],
             "the scanner must be read from the base revision, with its range mode marker "
             "checked as a fixed whole line, before it runs")
    _require([line for line in scan if re.search(r"\bgit |scanner\w*=", line)]
             == [EXTRACTION[index] for index in (0, 2, 5, 6)],
             "the base revision blob in the temporary directory must be the only scanner, "
             "and no other git command may run")
    _require(RANGE_MARKER in (ROOT / GUARD_SCRIPT).read_text(encoding="utf-8").splitlines(),
             "the scanner must declare the range mode marker on a line of its own")

    _require(confirm.get("shell") == "bash"
             and confirm.get("env") == {"SCAN": "${{ steps.range.outputs.scan }}"},
             "the no-op step must check the selection decision")
    # No bootstrap path: no script names the candidate checkout or downgrades to a warning.
    for index, step in enumerate((select, run, confirm)):
        lines = _script_lines(step)
        _require(not any("candidate" in line or "::warning::" in line for line in lines),
                 f"script #{index} must not fall back to the candidate checkout")


def test_scan_results_and_ci_gate_propagate_secret_guard() -> None:
    summary = _workflow_jobs(SECURITY_WORKFLOW).get("scan-summary") or {}
    _require(summary.get("name") == "Scan results", "the Scan results context must keep its name")
    _require("secret-guard" in (summary.get("needs") or []), "Scan results must need secret-guard")
    gate = _workflow_jobs(GATE_WORKFLOW)
    security, aggregate = gate.get("security") or {}, gate.get("ci-gate") or {}
    _require(security.get("uses") == "./" + SECURITY_WORKFLOW, "ci-gate must call the security scan")
    _require(aggregate.get("name") == "ci-gate" and "security" in (aggregate.get("needs") or []),
             "the ci-gate context must keep its name and need the security scan")


def test_secret_guard_job_runs_the_base_scanner_from_outside_the_candidate(
    guard_origin: GuardOrigin, tmp_path: Path,
) -> None:
    base, head = (guard_origin.commits[name] for name in ("probe", "probe-head"))
    events = ((_pull_request, []), (_merge_group, []), (_push, ["--direct", "--allow-empty"]))
    for index, (event, options) in enumerate(events):
        root = tmp_path / f"run-{index}"
        run = _run_guard_job(guard_origin.path, root, guard_origin.env, event(base, head))
        _require(run.passed and run.steps == SCAN_STEPS and run.output == "",
                 f"case #{index}: the base scanner must run without output")
        try:
            started = json.loads(guard_origin.record.read_text(encoding="utf-8"))
            guard_origin.record.unlink()
        except (OSError, ValueError):
            started = None
        _require(isinstance(started, list) and len(started) == 5,
                 f"case #{index}: the base scanner did not run")
        script, directory, arguments, isolated, no_bytecode = started
        temp, candidate = (root / "temp").resolve(), (root / "workspace/candidate").resolve()
        # The temporary directory is next to the workspace, so outside the candidate checkout.
        _require(Path(script).resolve().parent.parent == temp,
                 f"case #{index}: the scanner must be extracted under the temporary directory")
        _require(Path(directory).resolve() == candidate,
                 f"case #{index}: the scanner must run inside the candidate checkout")
        _require(arguments == ["--range", base, head, *options],
                 f"case #{index}: unexpected scanner arguments")
        _require(isolated == 1 and no_bytecode is True,
                 f"case #{index}: the scanner must run isolated, without bytecode")
        _require(not any(temp.iterdir()), f"case #{index}: the extracted scanner must be removed")
    _require_no_candidate_code_ran(guard_origin)


def test_secret_guard_job_scans_the_range_of_each_event(
    guard_origin: GuardOrigin, tmp_path: Path,
) -> None:
    commits = guard_origin.commits
    base, clean, flagged, noted = (commits[name] for name in ("base", "clean", "flagged", "noted"))
    in_file = "Secret guard: access token detected in diff file #1 at line 1" + FOUND
    in_message = f"Secret guard: private key detected in commit #1 ({noted[:12]}) message at line 3"
    in_message += FOUND
    empty = "Secret guard: empty commit range" + CLOSED
    unresolved = "Secret guard: unable to resolve git revision" + CLOSED
    restored = ("Secret guard: sensitive filename added or renamed at diff path #1" + FOUND
                + "Secret guard: access token detected in diff file #1 at line 2" + FOUND)
    diverged = "Secret guard: access token detected in diff file #3 at line 1" + FOUND
    cases = [
        (_pull_request(base, clean), True, "", SCAN_STEPS),
        (_pull_request(base, flagged), False, in_file, SCAN_STEPS),
        (_pull_request(base, noted), False, in_message, SCAN_STEPS),
        (_pull_request(base, base), False, empty, SCAN_STEPS),
        (_merge_group(base, clean), True, "", SCAN_STEPS),
        (_merge_group(base, flagged), False, in_file, SCAN_STEPS),
        (_merge_group(base, noted), False, in_message, SCAN_STEPS),
        (_merge_group(base, base), False, empty, SCAN_STEPS),
        (_push(base, clean), True, "", SCAN_STEPS),
        (_push(base, flagged), False, in_file, SCAN_STEPS),
        (_push(base, noted), False, in_message, SCAN_STEPS),
        # What differs only because the base moved on is not attributed to the range;
        # a push is compared with the previous tip itself, which also covers a rewind.
        (_pull_request(commits["advanced"], clean), True, "", SCAN_STEPS),
        (_merge_group(commits["advanced"], clean), True, "", SCAN_STEPS),
        (_push(commits["advanced"], clean), False, diverged, SCAN_STEPS),
        (_push(commits["removed"], commits["restored"]), False, restored, SCAN_STEPS),
        # A push that adds no commit passes.
        (_push(base, base), True, "", SCAN_STEPS),
        # The pushed commit does not resolve in the candidate checkout.
        (_push(base, "2" * 40, sha=clean), False, unresolved, SCAN_STEPS),
    ]
    _assert_guard_runs(guard_origin, tmp_path, cases)


def test_secret_guard_job_checks_nothing_out_without_a_commit_range(
    guard_origin: GuardOrigin, tmp_path: Path,
) -> None:
    commits = guard_origin.commits
    base, clean, flagged = (commits[name] for name in ("base", "clean", "flagged"))
    events = [
        ({"github.event_name": "schedule", "github.sha": flagged}, NO_RANGE),
        ({"github.event_name": "workflow_dispatch", "github.sha": flagged}, NO_RANGE),
        # Branch creation: by flag, by an all-zero previous revision, or both.
        (_push(NO_COMMIT, flagged, created="true"), CREATED),
        (_push(base, flagged, created="true"), CREATED),
        (_push(NO_COMMIT, flagged), CREATED),
        (_push("0" * 64, flagged), CREATED),
        # Branch deletion: by flag, by an all-zero pushed revision, or both; it comes first.
        (_push(flagged, NO_COMMIT, sha=clean, deleted="true"), DELETED),
        (_push(base, flagged, deleted="true"), DELETED),
        (_push(flagged, NO_COMMIT, sha=clean), DELETED),
        (_push(NO_COMMIT, NO_COMMIT, sha=clean, created="true", deleted="true"), DELETED),
    ]
    cases = [(event, True, output, [SELECT, CONFIRM]) for event, output in events]
    _assert_guard_runs(guard_origin, tmp_path, cases)


def test_secret_guard_job_fails_closed(guard_origin: GuardOrigin, tmp_path: Path) -> None:
    commits = guard_origin.commits
    base, clean = commits["base"], commits["clean"]
    unmarked = [(commits[f"unmarked-{index}"], commits[f"unmarked-{index}-head"])
                for index in range(4)]
    events = (_pull_request, _merge_group, _push)
    cases = [
        # Missing or partial commit ids stop the job before any checkout.
        (_pull_request("", clean), False, NO_IDS, [SELECT]),
        (_pull_request(base, ""), False, NO_IDS, [SELECT]),
        (_pull_request("main", clean), False, NO_IDS, [SELECT]),
        (_pull_request(base[:12], clean), False, NO_IDS, [SELECT]),
        (_pull_request(NO_COMMIT, clean), False, NO_IDS, [SELECT]),
        (_merge_group("", clean), False, NO_IDS, [SELECT]),
        (_merge_group(base, ""), False, NO_IDS, [SELECT]),
        (_push("", clean), False, NO_IDS, [SELECT]),
        (_push(base, ""), False, NO_IDS, [SELECT]),
        (_push("main", clean), False, NO_IDS, [SELECT]),
        # Any other event is an error, whatever fields it carries.
        ({**_pull_request(base, clean), "github.event_name": "pull_request_target"},
         False, UNSUPPORTED, [SELECT]),
        ({"github.event_name": "workflow_run"}, False, UNSUPPORTED, [SELECT]),
        ({}, False, UNSUPPORTED, [SELECT]),
        # A base revision the fetched history does not hold (a previous tip no branch
        # keeps, or an unknown commit), one without the scanner, or one whose scanner has
        # no range mode marker, is an error on every event: the candidate scanner is never
        # used instead, and neither git output nor file content is shown.
        (_push(commits["dropped"], base), False, NO_BASE, SCAN_STEPS),
        *((event("1" * 40, clean), False, NO_BASE, SCAN_STEPS) for event in events),
        *((event(commits["bare"], commits["bare-head"]), False, NO_SCANNER, SCAN_STEPS)
          for event in events),
        *((_pull_request(old, new), False, NO_RANGE_MODE, SCAN_STEPS) for old, new in unmarked),
        (_merge_group(*unmarked[0]), False, NO_RANGE_MODE, SCAN_STEPS),
        (_push(*unmarked[0]), False, NO_RANGE_MODE, SCAN_STEPS),
    ]
    _assert_guard_runs(guard_origin, tmp_path, cases)


def test_secret_guard_scripts_reject_an_unexpected_state(
    guard_origin: GuardOrigin, tmp_path: Path,
) -> None:
    commits = guard_origin.commits
    base, clean = commits["base"], commits["clean"]
    root = tmp_path / "job"
    workspace, temp = root / "workspace", root / "temp"
    passed = _run_guard_job(guard_origin.path, root, guard_origin.env,
                            _pull_request(base, clean)).passed
    _require(passed, "the fixture job must pass before its state is altered")
    tree = _run(["git", "rev-parse", "--verify", "--quiet", base + "^{tree}"],
                workspace / "candidate", guard_origin.env).stdout.strip()
    _require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", tree), "git fixture command failed")
    steps = _steps(SECURITY_WORKFLOW, "secret-guard")
    outputs = {"base": base, "head": clean, "mode": "merge-base"}
    cases = [
        (2, {}, temp, 0, ""),
        # A base that is no commit of the candidate history: absent, unknown, or a tree.
        (2, {"base": ""}, temp, 1, NO_BASE),
        (2, {"base": "1" * 40}, temp, 1, NO_BASE),
        (2, {"base": tree}, temp, 1, NO_BASE),
        # A candidate revision as base: its scanner has no marker and does not run.
        (2, {"base": clean}, temp, 1, NO_RANGE_MODE),
        (2, {"mode": ""}, temp, 1, NO_MODE),
        (2, {"mode": "bootstrap"}, temp, 1, NO_MODE),
        (2, {}, tmp_path / "absent", 1, NO_TEMP),
        (3, {"scan": "false"}, temp, 0, CONFIRMED),
        (3, {"scan": ""}, temp, 1, NO_DECISION),
        (3, {"scan": "maybe"}, temp, 1, NO_DECISION),
    ]
    for index, (step, changes, runner_temp, status, output) in enumerate(cases):
        context = {f"steps.range.outputs.{name}": value
                   for name, value in {**outputs, **changes}.items()}
        env = {**guard_origin.env, "RUNNER_TEMP": str(runner_temp)}
        result = _run_script(steps[step], workspace, env, context)
        _require(result.returncode == status, f"case #{index}: unexpected exit status")
        _require_fixed_output(result.stdout + result.stderr, output, f"case #{index}")
        _require(not any(temp.iterdir()), f"case #{index}: the extracted scanner must be removed")
    _require_no_candidate_code_ran(guard_origin)


def test_gate_dependency_install_never_shows_pip_output(tmp_path: Path) -> None:
    install = [step for step in _steps(GATE_WORKFLOW, "gate-contract")
               if step.get("name") == "Install pytest"]
    _require(len(install) == 1 and install[0].get("shell") == "bash",
             "gate-contract must have one bash step that installs pytest")
    # Stand-in for the interpreter: records its arguments and writes to both streams.
    stub, arguments = tmp_path / "bin/python", tmp_path / "arguments"
    stub.parent.mkdir()
    stub.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$STUB_ARGUMENTS"\n'
                    'echo "pip output $STUB_STATUS"\necho "pip error $STUB_STATUS" >&2\n'
                    'exit "$STUB_STATUS"\n', encoding="utf-8")
    stub.chmod(0o755)
    expected = "-m pip install --require-hashes -r .github/workflows/requirements/gate.txt"
    for index, status in enumerate((0, 1, 7)):
        temporary = tmp_path / f"temporary-{index}"
        temporary.mkdir()
        env = _fixture_env(tmp_path)
        env.update(PATH=f"{stub.parent}{os.pathsep}{env['PATH']}", RUNNER_TEMP=str(temporary),
                   STUB_ARGUMENTS=str(arguments), STUB_STATUS=str(status))
        result = _run_script(install[0], tmp_path, env, {})
        _require(result.returncode == status, f"case #{index}: the pip exit status must be kept")
        shown = "" if status == 0 else "dependency install failed\n"
        _require(result.stdout == "" and result.stderr == shown,
                 f"case #{index}: only the fixed failure message may be shown")
        _require(arguments.read_text(encoding="utf-8").split() == expected.split(),
                 f"case #{index}: unexpected install command")
        _require(not any(temporary.iterdir()), f"case #{index}: the pip output must be removed")
