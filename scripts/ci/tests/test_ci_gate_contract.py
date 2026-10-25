"""Contract tests for the ci-gate aggregator and change detector."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

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


# Ceiling for `secrets: inherit`. A new occurrence fails. This set may only shrink.
ALLOWED_SECRET_INHERIT = frozenset(
    {
        ".github/workflows/control-plane-api-ci.yml:deploy",
        ".github/workflows/control-plane-api-ci.yml:docker",
        ".github/workflows/control-plane-api-ci.yml:notify",
        ".github/workflows/control-plane-ui-ci.yml:deploy",
        ".github/workflows/control-plane-ui-ci.yml:docker",
        ".github/workflows/control-plane-ui-ci.yml:notify",
        ".github/workflows/e2e-nightly.yml:e2e",
        ".github/workflows/promote-to-prod.yml:notify",
        ".github/workflows/promote-to-prod.yml:promote-api",
        ".github/workflows/promote-to-prod.yml:promote-gw",
        ".github/workflows/promote-to-prod.yml:promote-portal",
        ".github/workflows/promote-to-prod.yml:promote-ui",
        ".github/workflows/release-please.yml:trigger-goreleaser",
        ".github/workflows/stoa-gateway-ci.yml:deploy",
        ".github/workflows/stoa-gateway-ci.yml:docker",
        ".github/workflows/stoa-gateway-ci.yml:notify",
        ".github/workflows/stoa-portal-ci.yml:deploy",
        ".github/workflows/stoa-portal-ci.yml:docker",
        ".github/workflows/stoa-portal-ci.yml:notify",
    }
)
PYYAML_PIN = "6.0.3"
_SECRETS_KEY = re.compile(r"^\s*secrets\s*:")
_SECRET_EXPR = re.compile(r"secrets\.[A-Za-z_][A-Za-z0-9_]*")
_EVENT_EQ = re.compile(r"github\.event_name\s*==\s*['\"]([A-Za-z0-9_]+)['\"]")
_ALLOWED_EVENTS = frozenset({"push", "workflow_dispatch"})
_FORBIDDEN_TRIGGER = re.compile(r"(?m)^[ \t]*(pull_request_target|workflow_run)[ \t]*:")


def _load_workflow(text: str) -> dict:
    loaded = yaml.safe_load(text) or {}
    if not isinstance(loaded, dict):
        raise AssertionError("workflow root must be a mapping")
    return loaded


def gate_job_secret_findings(text: str) -> tuple[list[str], list[int]]:
    regex_lines = [
        number
        for number, line in enumerate(text.splitlines(), 1)
        if _SECRETS_KEY.match(line)
    ]
    jobs = _load_workflow(text).get("jobs") or {}
    yaml_jobs = [
        str(name)
        for name, job in jobs.items()
        if isinstance(job, dict) and "secrets" in job
    ]
    return yaml_jobs, regex_lines


def inherit_sites(root: Path) -> set[str]:
    sites: set[str] = set()
    for path in sorted((root / ".github" / "workflows").glob("*.yml")):
        jobs = _load_workflow(path.read_text(encoding="utf-8")).get("jobs") or {}
        relative = path.relative_to(root).as_posix()
        for name, job in jobs.items():
            if isinstance(job, dict) and job.get("secrets") == "inherit":
                sites.add(f"{relative}:{name}")
    return sites


def _strings(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, str):
        found.append(node)
    elif isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str):
                found.append(key)
            found.extend(_strings(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_strings(item))
    return found


def if_requires_push_or_dispatch(expression: object) -> bool:
    if not isinstance(expression, str) or not expression.strip():
        return False
    for part in expression.split("||"):
        events = _EVENT_EQ.findall(part)
        if not events or any(event not in _ALLOWED_EVENTS for event in events):
            return False
    return True


def secret_expr_violations(root: Path) -> list[str]:
    gate = root / ".github" / "workflows" / "ci-gate.yml"
    jobs = _load_workflow(gate.read_text(encoding="utf-8")).get("jobs") or {}
    violations: list[str] = []
    for job in jobs.values():
        if not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if not isinstance(uses, str) or not uses.startswith("./.github/workflows/"):
            continue
        path = root / uses[2:]
        relative = path.relative_to(root).as_posix()
        called = _load_workflow(path.read_text(encoding="utf-8")).get("jobs") or {}
        for name, body in called.items():
            if not isinstance(body, dict):
                continue
            if not any(_SECRET_EXPR.search(text) for text in _strings(body)):
                continue
            if not if_requires_push_or_dispatch(body.get("if")):
                violations.append(f"{relative}:{name}")
    return violations


def _trigger_names(node: object) -> set[str]:
    names: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"pull_request_target", "workflow_run"}:
                names.add(str(key))
            names.update(_trigger_names(value))
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, str) and item in {"pull_request_target", "workflow_run"}:
                names.add(item)
            else:
                names.update(_trigger_names(item))
    elif node in {"pull_request_target", "workflow_run"}:
        names.add(str(node))
    return names


def forbidden_triggers(root: Path) -> list[str]:
    hits: list[str] = []
    for path in sorted((root / ".github" / "workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        names = set(_FORBIDDEN_TRIGGER.findall(text))
        loaded = _load_workflow(text)
        names.update(_trigger_names(loaded.get(True, loaded.get("on"))))
        relative = path.relative_to(root).as_posix()
        hits.extend(f"{relative}:{name}" for name in sorted(names))
    return hits


def test_r_inh_1_ci_gate_has_no_secrets_key() -> None:
    text = (ROOT / ".github" / "workflows" / "ci-gate.yml").read_text(encoding="utf-8")
    jobs, lines = gate_job_secret_findings(text)
    assert jobs == []
    assert lines == []
    assert f"PyYAML=={PYYAML_PIN}" in text


@pytest.mark.parametrize(
    "snippet",
    (
        "    secrets: inherit\n",
        "    secrets:\n      TOKEN: value\n",
    ),
)
def test_r_inh_1_rejects_secrets_key(snippet: str) -> None:
    text = (ROOT / ".github" / "workflows" / "ci-gate.yml").read_text(encoding="utf-8")
    modified = text.replace("  gate-contract:\n", "  gate-contract:\n" + snippet, 1)
    jobs, lines = gate_job_secret_findings(modified)
    assert jobs == ["gate-contract"]
    assert lines


def test_r_inh_2_current_inherits_match_allowlist() -> None:
    assert inherit_sites(ROOT) == ALLOWED_SECRET_INHERIT


def test_r_inh_2_new_inherit_fails(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "extra.yml").write_text(
        "name: extra\n"
        "on: [push]\n"
        "jobs:\n"
        "  leak:\n"
        "    uses: ./.github/workflows/other.yml\n"
        "    secrets: inherit\n",
        encoding="utf-8",
    )
    assert inherit_sites(tmp_path) - ALLOWED_SECRET_INHERIT == {
        ".github/workflows/extra.yml:leak"
    }


def test_r_inh_3_called_workflows_gate_secret_expressions() -> None:
    assert secret_expr_violations(ROOT) == []


@pytest.mark.parametrize(
    ("guard", "violates"),
    (
        ("", True),
        ("github.event_name == 'pull_request'", True),
        ("github.event_name == 'push' || github.event_name == 'pull_request'", True),
        ("github.event_name == 'push' || github.event_name == 'workflow_dispatch'", False),
        ("github.event_name == 'push' && github.ref == 'refs/heads/main'", False),
    ),
)
def test_r_inh_3_secret_expression_requires_push_or_dispatch(
    tmp_path: Path, guard: str, violates: bool
) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci-gate.yml").write_text(
        "name: CI Gate\n"
        "on: [pull_request]\n"
        "jobs:\n"
        "  called:\n"
        "    uses: ./.github/workflows/called.yml\n",
        encoding="utf-8",
    )
    if_line = f"    if: {guard}\n" if guard else ""
    (workflows / "called.yml").write_text(
        "name: called\n"
        "on:\n"
        "  workflow_call:\n"
        "jobs:\n"
        "  leak:\n"
        f"{if_line}"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        '      - run: "echo ${{ secrets.TOKEN }}"\n',
        encoding="utf-8",
    )
    found = secret_expr_violations(tmp_path)
    assert found == ([".github/workflows/called.yml:leak"] if violates else [])


def test_r_trig_repository_has_no_forbidden_triggers() -> None:
    assert forbidden_triggers(ROOT) == []


@pytest.mark.parametrize("trigger", ("pull_request_target", "workflow_run"))
def test_r_trig_forbidden_trigger_fails(tmp_path: Path, trigger: str) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "bad.yml").write_text(
        "name: bad\n"
        "on:\n"
        f"  {trigger}:\n"
        "jobs:\n"
        "  a:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo ok\n",
        encoding="utf-8",
    )
    assert forbidden_triggers(tmp_path) == [f".github/workflows/bad.yml:{trigger}"]

