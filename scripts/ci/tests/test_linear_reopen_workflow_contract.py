"""Static contract for .github/workflows/linear-reopen-on-close.yml (CAB-2301).

Bounded to this single workflow: triggers, permissions, secrets and the way
pull request metadata reaches shell steps. No network, no PR code executed.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "linear-reopen-on-close.yml"

ALLOWED_SECRETS = {"LINEAR_API_KEY"}
ALLOWED_PERMISSIONS = {"contents": "read", "pull-requests": "read"}
EXPR = re.compile(r"\$\{\{(.*?)\}\}", re.S)
UNTRUSTED = re.compile(r"\bgithub\.(event|head_ref)\b")
SECRET_REF = re.compile(r"\bsecrets\.([A-Za-z_][A-Za-z0-9_]*)|\bsecrets\[")


def load(text: str) -> dict:
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise ValueError("workflow is not a mapping")
    # YAML 1.1 loaders turn the `on` key into True; keep it readable.
    if True in doc and "on" not in doc:
        doc["on"] = doc.pop(True)
    if "on" not in doc:
        raise ValueError("workflow has no `on` key")
    return doc


def events(doc: dict) -> dict:
    on = doc["on"]
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {name: None for name in on}
    if isinstance(on, dict):
        return on
    raise ValueError(f"unreadable `on`: {on!r}")


def run_blocks(doc: dict):
    for job_id, job in (doc.get("jobs") or {}).items():
        for index, step in enumerate(job.get("steps") or []):
            if "run" in step:
                yield job_id, step.get("name", index), step["run"]


def untrusted_in_run(doc: dict) -> list[str]:
    """Steps whose shell text interpolates untrusted event data directly."""
    found = []
    for job_id, name, script in run_blocks(doc):
        for expr in EXPR.findall(script):
            if UNTRUSTED.search(expr):
                found.append(f"{job_id}/{name}: ${{{{{expr.strip()}}}}}")
    return found


def secret_names(text: str) -> set[str]:
    names = set()
    for match in SECRET_REF.finditer(text):
        if match.group(1) is None:
            raise ValueError("dynamic secrets[...] reference is not classifiable")
        names.add(match.group(1))
    return names


@pytest.fixture(scope="module")
def source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def doc(source: str) -> dict:
    return load(source)


def test_triggers_only_on_closed_pull_requests(doc):
    assert events(doc) == {"pull_request": {"types": ["closed"]}}


def test_no_privileged_or_queue_triggers(doc):
    assert "pull_request_target" not in events(doc)
    assert "merge_group" not in events(doc)
    assert "workflow_run" not in events(doc)


def test_permissions_are_read_only_and_exact(doc):
    assert doc.get("permissions") == ALLOWED_PERMISSIONS
    for job in doc["jobs"].values():
        assert "permissions" not in job


def test_job_runs_only_for_unmerged_close(doc):
    (job,) = doc["jobs"].values()
    condition = re.sub(r"\s+", " ", str(job.get("if", "")))
    assert "github.event.pull_request.merged == false" in condition
    assert "||" not in condition


def test_no_checkout_and_no_third_party_actions(doc):
    for job in doc["jobs"].values():
        assert "uses" not in job, "reusable workflow call"
        for step in job.get("steps") or []:
            assert "uses" not in step, step.get("name")


def test_only_contracted_secrets(source, doc):
    assert secret_names(source) == ALLOWED_SECRETS
    for job in doc["jobs"].values():
        assert job.get("secrets") != "inherit"


def test_event_data_reaches_shell_only_through_env(doc):
    assert untrusted_in_run(doc) == []


# --- Oracles on synthetic fixtures (no real values) -------------------------

M1_BEFORE = """
on:
  pull_request:
    types: [closed]
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - run: |
          TITLE="${{ github.event.pull_request.title }}"
"""

M1_AFTER = """
on:
  pull_request:
    types: [closed]
jobs:
  j:
    runs-on: ubuntu-latest
    steps:
      - env:
          PR_TITLE: ${{ github.event.pull_request.title }}
        run: |
          TITLE="$PR_TITLE"
"""


def test_oracle_direct_interpolation_is_rejected():
    assert untrusted_in_run(load(M1_BEFORE))


def test_oracle_env_form_is_accepted():
    assert untrusted_in_run(load(M1_AFTER)) == []


@pytest.mark.parametrize(
    "on_block",
    ["on: pull_request", "on: [pull_request]", "on:\n  pull_request:\n    types: [closed]"],
)
def test_oracle_on_key_forms_are_read(on_block):
    assert "pull_request" in events(load(on_block + "\njobs: {}\n"))


def test_oracle_dynamic_secret_is_not_classifiable():
    with pytest.raises(ValueError):
        secret_names("x: ${{ secrets[format('{0}', 'A')] }}")


def test_oracle_invalid_yaml_fails_explicitly():
    with pytest.raises(yaml.YAMLError):
        load("on: [pull_request\n")
