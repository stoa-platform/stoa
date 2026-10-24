"""Contract tests for the ci-gate aggregator and change detector."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
AGGREGATE = ROOT / ".github" / "scripts" / "ci-gate-aggregate.sh"
CHANGES = ROOT / ".github" / "scripts" / "ci-gate-changes.sh"

COMPONENTS = (
    "control-plane-api",
    "stoa-gateway",
    "control-plane-ui",
    "portal",
    "stoa-go",
    "stoa-operator",
    "helm",
    "gate-contract",
)
JOBS = ("changes", *COMPONENTS, "security")


def _needs(results: dict[str, str], outputs: dict[str, str]) -> dict:
    body = {
        "changes": {"result": results["changes"], "outputs": outputs},
        "security": {"result": results["security"], "outputs": {}},
    }
    for name in COMPONENTS:
        body[name] = {"result": results[name], "outputs": {}}
    return body


def _baseline(touched: set[str] | None = None) -> tuple[dict[str, str], dict[str, str]]:
    selected = set(COMPONENTS if touched is None else touched)
    outputs = {name: "true" if name in selected else "false" for name in COMPONENTS}
    results = {"changes": "success", "security": "success"}
    for name in COMPONENTS:
        results[name] = "success" if name in selected else "skipped"
    return results, outputs


def _aggregate(payload: dict | str | None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("GITHUB_STEP_SUMMARY", None)
    env.pop("GITHUB_OUTPUT", None)
    if payload is None:
        env.pop("NEEDS", None)
    elif isinstance(payload, str):
        env["NEEDS"] = payload
    else:
        env["NEEDS"] = json.dumps(payload)
    return subprocess.run(
        ["bash", str(AGGREGATE)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_all_green() -> None:
    results, outputs = _baseline()
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode == 0, proc.stderr
    assert "CI Gate passed." in proc.stdout


def test_untouched_components_skipped() -> None:
    results, outputs = _baseline({"portal", "helm"})
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode == 0, proc.stderr


def test_all_components_skipped() -> None:
    results, outputs = _baseline(set())
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("job", JOBS)
@pytest.mark.parametrize("state", ("failure", "cancelled"))
def test_failure_or_cancelled_on_each_job(job: str, state: str) -> None:
    touched = {job} if job in COMPONENTS else set()
    results, outputs = _baseline(touched)
    results[job] = state
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode != 0
    assert "::error::" in proc.stdout


@pytest.mark.parametrize("component", COMPONENTS)
def test_expected_component_skipped(component: str) -> None:
    results, outputs = _baseline({component})
    results[component] = "skipped"
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode != 0
    assert component in proc.stdout


def test_security_skipped() -> None:
    results, outputs = _baseline(set())
    results["security"] = "skipped"
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode != 0
    assert "security" in proc.stdout


def test_changes_skipped() -> None:
    results, outputs = _baseline(set())
    results["changes"] = "skipped"
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode != 0
    assert "changes" in proc.stdout


@pytest.mark.parametrize("payload", ({}, "", "null", "[]"))
def test_empty_needs(payload: dict | str) -> None:
    proc = _aggregate(payload)
    assert proc.returncode != 0
    assert "empty needs" in proc.stdout


def test_needs_unset() -> None:
    proc = _aggregate(None)
    assert proc.returncode != 0
    assert "empty needs" in proc.stdout


def test_missing_detector_output() -> None:
    results, outputs = _baseline()
    del outputs["helm"]
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode != 0
    assert "helm" in proc.stdout


def test_detector_output_not_boolean() -> None:
    results, outputs = _baseline({"portal"})
    outputs["portal"] = "yes"
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode != 0
    assert "portal" in proc.stdout


@pytest.mark.parametrize("job", JOBS)
def test_unknown_result(job: str) -> None:
    touched = {job} if job in COMPONENTS else set()
    results, outputs = _baseline(touched)
    results[job] = "unknown"
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode != 0


def test_unselected_component_success_is_rejected() -> None:
    results, outputs = _baseline(set())
    results["helm"] = "success"
    proc = _aggregate(_needs(results, outputs))
    assert proc.returncode != 0
    assert "helm" in proc.stdout


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "ci-gate@example.com")
    _git(repo, "config", "user.name", "ci-gate")
    _git(repo, "config", "commit.gpgsign", "false")
    _git(repo, "config", "core.quotepath", "true")
    for rel in (
        "control-plane-api/src/app.py",
        "stoa-gateway/src/lib.rs",
        "control-plane-ui/src/app.tsx",
        "portal/src/app.tsx",
        "stoa-go/main.go",
        "stoa-operator/main.py",
        "charts/stoa/Chart.yaml",
        "docs/readme.md",
        "README.md",
    ):
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "seed")
    return repo, _git(repo, "rev-parse", "HEAD")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _detect(repo: Path, base: str, head: str) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GITHUB_OUTPUT", None)
    env["LC_ALL"] = "C"
    proc = subprocess.run(
        ["bash", str(CHANGES), base, head],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    flags: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        key, value = line.split("=", 1)
        flags[key] = value
    assert set(flags) == set(COMPONENTS)
    return flags


def _assert_selected(flags: dict[str, str], *selected: str) -> None:
    chosen = set(selected)
    for name in COMPONENTS:
        expected = "true" if name in chosen else "false"
        assert flags[name] == expected, (name, flags)


def test_detect_addition(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    (repo / "control-plane-api" / "src" / "new.py").write_text("add\n", encoding="utf-8")
    head = _commit(repo, "add")
    _assert_selected(_detect(repo, base, head), "control-plane-api")


def test_detect_deletion(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    (repo / "stoa-gateway" / "src" / "lib.rs").unlink()
    head = _commit(repo, "delete")
    _assert_selected(_detect(repo, base, head), "stoa-gateway")


def test_detect_move_between_components(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    _git(repo, "mv", "portal/src/app.tsx", "control-plane-ui/src/moved.tsx")
    head = _commit(repo, "move")
    _assert_selected(_detect(repo, base, head), "portal", "control-plane-ui")


def test_detect_move_to_docs(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    _git(repo, "mv", "stoa-go/main.go", "docs/main.go")
    head = _commit(repo, "move docs")
    _assert_selected(_detect(repo, base, head), "stoa-go")


def test_detect_non_ascii_name(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    (repo / "portal" / "café.ts").write_text("é\n", encoding="utf-8")
    head = _commit(repo, "non ascii")
    _assert_selected(_detect(repo, base, head), "portal")


@pytest.mark.parametrize("code", (2, 3))
def test_grep_status_other_than_zero_or_one_fails(tmp_path: Path, code: int) -> None:
    repo, base = _repo(tmp_path)
    (repo / "docs" / "note.md").write_text("note\n", encoding="utf-8")
    head = _commit(repo, "note")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    grep = bindir / "grep"
    grep.write_text(f"#!/bin/sh\nexit {code}\n", encoding="utf-8")
    grep.chmod(0o755)
    env = os.environ.copy()
    env.pop("GITHUB_OUTPUT", None)
    env["LC_ALL"] = "C"
    env["PATH"] = f"{bindir}{os.pathsep}{env['PATH']}"
    proc = subprocess.run(
        ["bash", str(CHANGES), base, head],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == code, proc.stderr
    assert f"grep exited {code}" in proc.stderr


@pytest.mark.parametrize(
    "rel",
    (
        ".github/scripts/ci-gate-changes.sh",
        ".github/scripts/ci-gate-aggregate.sh",
        "scripts/ci/tests/test_ci_gate_contract.py",
        ".github/workflows/notes.yml",
    ),
)
def test_gate_script_or_contract_test_selects_contract_job(tmp_path: Path, rel: str) -> None:
    repo, base = _repo(tmp_path)
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("contract\n", encoding="utf-8")
    head = _commit(repo, "contract")
    _assert_selected(_detect(repo, base, head), "gate-contract")


def test_contract_job_is_covered_by_aggregation() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci-gate.yml").read_text(encoding="utf-8")
    aggregate = AGGREGATE.read_text(encoding="utf-8")
    changes = CHANGES.read_text(encoding="utf-8")
    assert "\n  gate-contract:" in workflow
    assert "needs.changes.outputs.gate-contract == 'true'" in workflow
    assert "- gate-contract" in workflow.split("name: ci-gate", 1)[1]
    assert "gate-contract" in aggregate
    assert r"^\.github/scripts/ci-gate-.*\.sh$" in changes
    assert r"scripts/ci/tests/test_ci_gate_contract\.py" in changes
    assert r"|^\.github/workflows/" in changes
    results, outputs = _baseline({"gate-contract"})
    assert _aggregate(_needs(results, outputs)).returncode == 0
    results["gate-contract"] = "failure"
    failed = _aggregate(_needs(results, outputs))
    assert failed.returncode != 0
    assert "gate-contract" in failed.stdout


def test_actions_directory_selects_stoa_operator(tmp_path: Path) -> None:
    repo, base = _repo(tmp_path)
    action = repo / ".github" / "actions" / "setup-rust-env" / "action.yml"
    action.parent.mkdir(parents=True)
    action.write_text("name: setup\n", encoding="utf-8")
    head = _commit(repo, "action")
    _assert_selected(
        _detect(repo, base, head),
        "control-plane-api",
        "stoa-gateway",
        "control-plane-ui",
        "portal",
        "stoa-operator",
    )
