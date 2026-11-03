"""Security scans select changed build contexts and fail closed on invalid diffs."""

from __future__ import annotations

import json
import os
import runpy
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
