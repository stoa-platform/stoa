"""Static contract for .github/workflows/linear-reopen-on-close.yml (CAB-2301).

Bounded to this single workflow: triggers, permissions, secrets, the way
pull request metadata reaches shell steps (no `${{ }}` expression in any
run block), how Linear requests are built (constant query text, values only
as jq --arg data, body sent on stdin) and the fail-closed `gh` lookup.
No network, no PR code executed.
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
EXPECTED_IF = (
    "github.event.pull_request.merged == false"
    " && vars.DISABLE_LINEAR_REOPEN != 'true'"
)
# A Linear request body: `jq -n`, zero or more `--arg name "$VAR"`, then one
# single-quoted program (no quote break-out possible), piped to `linear`.
JQ_FEED = re.compile(r"""jq -n(?: --arg \w+ "\$\w+")* '\{[^']*\}'\s*\|\s*linear\b""")
LINEAR_PIPE = re.compile(r"\|\s*linear\b")
GH_FAIL_CLOSED = re.compile(
    r"if ! MERGED_PRS=\$\(gh pr list [^\n]*\); then\n[^\n]*\n\s*exit 1\b"
)
GH_CALL = re.compile(r"(?:^|[\s$(])gh\s")
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


def expressions_in_run(doc: dict) -> list[str]:
    """Any `${{ }}` expression inside shell text (event, env, steps, inputs...).

    Values must reach the shell through `env:` only, so no expression of any
    kind is allowed in a run block.
    """
    found = []
    for job_id, name, script in run_blocks(doc):
        for expr in EXPR.findall(script):
            found.append(f"{job_id}/{name}: ${{{{{expr.strip()}}}}}")
    return found


def unsafe_linear_feeds(script: str) -> int:
    """Number of `| linear` pipes not fed by a constant jq -n program."""
    return len(LINEAR_PIPE.findall(script)) - len(JQ_FEED.findall(script))


def linear_transport_ok(script: str) -> bool:
    """Exactly one call site to api.linear.app, body on stdin only."""
    if script.count("api.linear.app") != 1:
        return False
    if "--data-binary @-" not in script:
        return False
    return re.search(r"(?:^|\s)(?:-d|--data|--data-raw|--data-urlencode)\s", script) is None


def gh_fail_closed(script: str) -> bool:
    if not GH_FAIL_CLOSED.search(script):
        return False
    for line in script.splitlines():
        if GH_CALL.search(line) and "||" in line:
            return False
    return True


def reopen_step(doc: dict) -> dict:
    (job,) = doc["jobs"].values()
    steps = [st for st in job.get("steps") or [] if "api.linear.app" in st.get("run", "")]
    assert len(steps) == 1, "exactly one step talks to Linear"
    return steps[0]


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
    condition = re.sub(r"\s+", " ", str(job.get("if", ""))).strip()
    assert condition == EXPECTED_IF


def test_no_checkout_and_no_third_party_actions(doc):
    for job in doc["jobs"].values():
        assert "uses" not in job, "reusable workflow call"
        for step in job.get("steps") or []:
            assert "uses" not in step, step.get("name")


def test_only_contracted_secrets(source, doc):
    assert secret_names(source) == ALLOWED_SECRETS
    for job in doc["jobs"].values():
        assert job.get("secrets") != "inherit"


def test_no_expression_in_any_run_block(doc):
    assert expressions_in_run(doc) == []


def test_linear_requests_are_constant_jq_programs(doc):
    script = reopen_step(doc)["run"]
    assert LINEAR_PIPE.findall(script), "no Linear request found"
    assert unsafe_linear_feeds(script) == 0


def test_linear_body_travels_on_stdin_only(doc):
    assert linear_transport_ok(reopen_step(doc)["run"])


def test_gh_lookup_uses_workflow_token_and_fails_closed(doc):
    step = reopen_step(doc)
    assert (step.get("env") or {}).get("GH_TOKEN") == "${{ github.token }}"
    assert gh_fail_closed(step["run"])


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
    assert expressions_in_run(load(M1_BEFORE))


def test_oracle_env_form_is_accepted():
    assert expressions_in_run(load(M1_AFTER)) == []


@pytest.mark.parametrize("expr", ["env.PR_TITLE", "steps.extract.outputs.ticket_id", "inputs.x"])
def test_oracle_any_expression_in_run_is_rejected(expr):
    text = M1_AFTER.replace('TITLE="$PR_TITLE"', 'TITLE="${{ ' + expr + ' }}"')
    assert expressions_in_run(load(text))


GOOD_FEED = """X=$(jq -n --arg identifier "$TICKET_ID" '{
    query: "query($identifier: String!) { a }",
    variables: { identifier: $identifier }
  }' | linear)"""


def test_oracle_constant_jq_feed_is_accepted():
    assert unsafe_linear_feeds(GOOD_FEED) == 0


@pytest.mark.parametrize(
    "feed",
    [
        'X=$(echo "{\\"query\\": \\"a $PR_TITLE\\"}" | linear)',
        """X=$(jq -n '{query: "a '"$PR_TITLE"'"}' | linear)""",
        'Q="{\\"query\\": \\"$PR_TITLE\\"}"; printf %s "$Q" | linear',
    ],
)
def test_oracle_interpolated_linear_body_is_rejected(feed):
    assert unsafe_linear_feeds(feed) > 0


def test_oracle_inline_curl_body_is_rejected():
    script = 'curl -s https://api.linear.app/graphql -d "$BODY" --data-binary @-'
    assert not linear_transport_ok(script)


GOOD_GH = """if ! MERGED_PRS=$(gh pr list --repo "$GH_REPO" --json number --jq 'length'); then
  echo "::error::lookup failed"
  exit 1
fi"""


def test_oracle_fail_closed_gh_is_accepted():
    assert gh_fail_closed(GOOD_GH)


@pytest.mark.parametrize(
    "script",
    [
        'MERGED_PRS=$(gh pr list --repo "$GH_REPO" --json number --jq length || echo 0)',
        GOOD_GH.replace("--jq 'length')", "--jq 'length' || echo 0)"),
        GOOD_GH.replace("exit 1", "exit 0"),
    ],
)
def test_oracle_fail_open_gh_is_rejected(script):
    assert not gh_fail_closed(script)


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
