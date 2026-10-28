"""Regression tests for CAB-2331 (option A): the two bot-PR workflows are retired.

Context
-------
`context-compiler-learn.yml` and `claude-self-improve.yml` opened pull requests
with GITHUB_TOKEN and then dispatched the required checks themselves (F4).
Both have been disabled since April 2026, and `main` now requires six checks
(including `ci-gate` and `purged-paths-guard`) that cannot be dispatched that
way, so the mechanism can no longer reach its goal. Option A removes the two
workflows instead of extending them.

These tests pin the decision:
  1. the two workflow files are gone;
  2. no workflow grants `actions: write` to GITHUB_TOKEN any more (that
     permission only existed for the F4 dispatch job);
  3. the public docs stop pointing at the removed workflows;
  4. the manual re-run path of the required checks (`workflow_dispatch`,
     `pr_number`) is kept, because it is useful independently of bots.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"

RETIRED = ("context-compiler-learn.yml", "claude-self-improve.yml")

DOCS_THAT_MUST_NOT_REFERENCE_RETIRED = (
    "CLAUDE.md",
    "docs/CONTEXT-COMPILER.md",
    "docs/ai/pr-guardian-runbook.md",
)


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} is not a mapping"
    return data


def _actions_write_grants(data: dict) -> list[str]:
    grants: list[str] = []
    top = data.get("permissions")
    if isinstance(top, dict) and top.get("actions") == "write":
        grants.append("<workflow>")
    for name, job in (data.get("jobs") or {}).items():
        perms = (job or {}).get("permissions")
        if isinstance(perms, dict) and perms.get("actions") == "write":
            grants.append(name)
    return grants


@pytest.mark.parametrize("name", RETIRED)
def test_retired_bot_workflow_is_absent(name: str) -> None:
    assert not (WORKFLOWS / name).exists(), f"{name} must be removed (CAB-2331 option A)"


def test_no_workflow_grants_actions_write() -> None:
    offenders = {
        wf.name: grants
        for wf in sorted(WORKFLOWS.glob("*.yml"))
        if (grants := _actions_write_grants(_load(wf)))
    }
    assert offenders == {}, f"GITHUB_TOKEN must not get actions: write: {offenders}"


@pytest.mark.parametrize("rel", DOCS_THAT_MUST_NOT_REFERENCE_RETIRED)
def test_docs_do_not_reference_retired_workflows(rel: str) -> None:
    text = (ROOT / rel).read_text(encoding="utf-8")
    stale = [name for name in RETIRED if name in text]
    assert stale == [], f"{rel} still references retired workflows: {stale}"


def test_manual_rerun_path_of_required_checks_is_kept() -> None:
    required = _load(WORKFLOWS / "required-checks.yml")
    guard = _load(WORKFLOWS / "regression-guard.yml")
    # PyYAML parses the bare `on:` key as boolean True.
    on_required = required.get("on", required.get(True))
    on_guard = guard.get("on", guard.get(True))
    assert "workflow_dispatch" in on_required
    assert "workflow_dispatch" in on_guard
    assert "pr_number" in (on_guard["workflow_dispatch"] or {}).get("inputs", {})
