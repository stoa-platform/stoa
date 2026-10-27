"""Static contract for .github/workflows/linear-reopen-on-close.yml (CAB-2301).

Bounded to this single workflow: triggers, permissions, secrets, the way
pull request metadata reaches shell steps (no `${{ }}` expression in any
run block), how Linear requests are built (`query:` is one constant string
literal, values only as declared jq --arg variables, body sent on stdin only)
and the fail-closed `gh` lookup, including its integer guard.
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
EXPECTED_IF = "github.event.pull_request.merged == false && vars.DISABLE_LINEAR_REOPEN != 'true'"
# A Linear request body: `jq -n`, zero or more `--arg name "$VAR"`, then one
# single-quoted program (no quote break-out possible), piped to `linear`.
JQ_FEED = re.compile(r"""jq -n((?: --arg \w+ "\$\w+")*) '(\{[^']*\})'\s*\|\s*linear\b""")
JQ_ARG = re.compile(r'--arg (\w+) "\$\w+"')
# The jq program itself: `query:` is ONE string literal whose only escape is
# \" (so no `\(...)` interpolation), followed directly by `variables:` made of
# `name: $name` pairs. No `+`, no other jq expression can fit this shape.
JQ_PROGRAM = re.compile(
    r'\{\s*query:\s*"((?:[^"\\]|\\")*)",\s*'
    r"variables:\s*\{\s*(\w+:\s*\$\w+(?:,\s*\w+:\s*\$\w+)*)\s*\}\s*\}"
)
GRAPHQL_VAR = re.compile(r"\$(\w+)")
# Any curl option that can carry a request body, in `-d x`, `-dX`, `-d"x"` or
# `--opt=x` form. The only one allowed is the exact `--data-binary @-`.
BODY_OPTION = re.compile(
    r"""(?:^|\s)(-d|--data(?:-raw|-urlencode|-binary|-ascii)?|--json|-F|--form)(?=[\s="'$@]|$)(\s*=?\s*\S*)"""
)
# One curl command, backslash continuations included.
CURL_COMMAND = re.compile(r"(?:^|[\s$(])curl\b(?:[^\n]*\\\n)*[^\n]*")
GH_CASE_GUARD = re.compile(
    r"""case "\$MERGED_PRS" in\n\s*''\|\*\[!0-9\]\*\)[^\n]*\bexit 1\b[^\n]*\n\s*esac"""
)
LINEAR_PIPE = re.compile(r"\|\s*linear\b")
GH_FAIL_CLOSED = re.compile(r"if ! MERGED_PRS=\$\(gh pr list [^\n]*\); then\n[^\n]*\n\s*exit 1\b")
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
        return dict.fromkeys(on)
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


def jq_program_ok(args: str, program: str) -> bool:
    """`query:` is a single constant literal; every value is a declared variable."""
    match = JQ_PROGRAM.fullmatch(program.strip())
    if match is None:
        return False
    query, pairs = match.groups()
    variables = {}
    for pair in pairs.split(","):
        key, value = (part.strip() for part in pair.split(":"))
        if value != "$" + key:
            return False
        variables[key] = value
    declared = set(JQ_ARG.findall(args))
    return set(GRAPHQL_VAR.findall(query)) == set(variables) == declared


def unsafe_linear_feeds(script: str) -> int:
    """Number of `| linear` pipes not fed by a constant jq -n program."""
    safe = sum(1 for args, program in JQ_FEED.findall(script) if jq_program_ok(args, program))
    return len(LINEAR_PIPE.findall(script)) - safe


def linear_transport_ok(script: str) -> bool:
    """Exactly one call site to api.linear.app, body on stdin only."""
    if script.count("api.linear.app") != 1:
        return False
    commands = CURL_COMMAND.findall(script)
    if len(commands) != 1 or "api.linear.app" not in commands[0]:
        return False
    options = [(opt, rest.strip()) for opt, rest in BODY_OPTION.findall(commands[0])]
    return options == [("--data-binary", "@-")]


def gh_fail_closed(script: str) -> bool:
    lookup = GH_FAIL_CLOSED.search(script)
    if not lookup:
        return False
    # A successful lookup must still return an integer before it is compared.
    guard = GH_CASE_GUARD.search(script, lookup.end())
    compare = script.find('[ "$MERGED_PRS" -gt 0 ]', lookup.end())
    if guard is None or compare == -1 or guard.start() > compare:
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


@pytest.mark.parametrize(
    "program",
    [
        # value glued into the query text by concatenation
        """'{query: ("query { a(id: \\"" + $identifier + "\\") }"), variables: { identifier: $identifier }}'""",
        # value glued into the query text by jq string interpolation
        """'{query: "query { a(id: \\($identifier)) }", variables: { identifier: $identifier }}'""",
        # variable used in the query but never declared as data
        """'{query: "query($other: String!) { a }", variables: { identifier: $identifier }}'""",
        # variables value that is not the declared argument
        """'{query: "query($identifier: String!) { a }", variables: { identifier: ($identifier + "x") }}'""",
    ],
)
def test_oracle_non_literal_query_is_rejected(program):
    feed = f'X=$(jq -n --arg identifier "$TICKET_ID" {program} | linear)'
    assert unsafe_linear_feeds(feed) > 0


def test_oracle_escaped_quote_in_literal_is_accepted():
    feed = (
        """X=$(jq -n --arg identifier "$TICKET_ID" '{query: "query($identifier: String!) """
        """{ s(name: \\"Todo\\", id: $identifier) }", variables: { identifier: $identifier }}' | linear)"""
    )
    assert unsafe_linear_feeds(feed) == 0


@pytest.mark.parametrize(
    "script",
    [
        'curl -s https://api.linear.app/graphql -d "$BODY" --data-binary @-',
        'curl -s https://api.linear.app/graphql --data-binary @- --data-urlencode="t=$PR_TITLE"',
        'curl -s https://api.linear.app/graphql --data-binary @- -d"$X"',
        'curl -s https://api.linear.app/graphql --data-binary @- --json "$X"',
        "curl -s https://api.linear.app/graphql --data-binary=@-",
    ],
)
def test_oracle_inline_curl_body_is_rejected(script):
    assert not linear_transport_ok(script)


def test_oracle_stdin_only_curl_is_accepted():
    assert linear_transport_ok(
        "curl -s -X POST https://api.linear.app/graphql \\\n  --data-binary @-"
    )


GOOD_GH = """if ! MERGED_PRS=$(gh pr list --repo "$GH_REPO" --json number --jq 'length'); then
  echo "::error::lookup failed"
  exit 1
fi
case "$MERGED_PRS" in
  ''|*[!0-9]*) echo "::error::unexpected gh output"; exit 1 ;;
esac
if [ "$MERGED_PRS" -gt 0 ]; then
  exit 0
fi"""


def test_oracle_fail_closed_gh_is_accepted():
    assert gh_fail_closed(GOOD_GH)


@pytest.mark.parametrize(
    "script",
    [
        'MERGED_PRS=$(gh pr list --repo "$GH_REPO" --json number --jq length || echo 0)',
        GOOD_GH.replace("--jq 'length')", "--jq 'length' || echo 0)"),
        GOOD_GH.replace("exit 1\nfi", "exit 0\nfi"),
        # integer guard removed
        re.sub(r"case .*?esac\n", "", GOOD_GH, flags=re.S),
        # integer guard that does not fail
        GOOD_GH.replace("exit 1 ;;", "exit 0 ;;"),
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
