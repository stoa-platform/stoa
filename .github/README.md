# `.github/` — STOA AI-Factory CI surface

Scope: composite actions, scripts and workflows that power the STOA
AI-Factory pipeline (Council → Plan → Implement) and the static-tests
harness that validates them.

## Composite actions (`.github/actions/`)

AI-Factory composites (Phase 2b of CI-1 rewrite — see
[`CI-1-REWRITE-PLAN.md`](./CI-1-REWRITE-PLAN.md)):

| Action | Purpose |
|---|---|
| [`council-run/`](./actions/council-run/) | Run a Council stage (S1/S2) via `anthropics/claude-code-action` and surface a structured score + verdict. |
| [`council-sync-linear/`](./actions/council-sync-linear/) | Apply Linear labels and comments based on Council output. |
| [`council-notify-slack/`](./actions/council-notify-slack/) | Post Council outcome to the engineering Slack channel. |
| [`detect-partial-pr/`](./actions/detect-partial-pr/) | Detect `claude-pr-*` branches when an implement run hits `max_turns`. |
| [`hegemon-state-push/`](./actions/hegemon-state-push/) | Push HEGEMON state files generated during a run. |
| [`label-guard/`](./actions/label-guard/) | Refuse to start work on issues missing the gate labels. |
| [`wait-for-label/`](./actions/wait-for-label/) | Poll an issue until a labelling step (Council) lands. |
| [`write-summary/`](./actions/write-summary/) | Render a markdown summary of an issue-to-PR run. |

Pre-existing (out of CI-1 scope):
[`e2e-setup`](./actions/e2e-setup/),
[`setup-node-env`](./actions/setup-node-env/),
[`setup-python-env`](./actions/setup-python-env/),
[`setup-rust-env`](./actions/setup-rust-env/).

## Scripts (`scripts/ci/`)

AI-Factory helpers (Phase 2a of CI-1 rewrite):

| Script | Lang | Purpose |
|---|---|---|
| `parse_council_report.py` | Python | Extract `score`/`verdict`/`mode` from a Claude execution-output JSON, with a regex fallback for legacy markdown comments. |
| `linear_apply_label.py` | Python | Idempotent Linear label add/remove via GraphQL. |
| `detect_pr_for_issue.py` | Python | Find an open PR linked to a given issue (used to recover from `max_turns`). |
| `map_score_to_label.py` | Python | Map a numeric Council score to the `council:*` label set. |
| `gh_helpers.sh` | Bash | Source-able helpers around `gh` (ticket id parsing, guards). |
| `wait_for_label.sh` | Bash | Poll an issue for a label with bounded retries. |

Pre-existing (out of CI-1 scope): `check-service-ports.sh`,
`coverage-ratchet.sh`, `perf-baseline.sh`, `perf-gate.sh`,
`test-perf-gate.sh`.

### Running tests locally

All AI-Factory script tests live in
[`scripts/ci/tests/`](../scripts/ci/tests/) and run via `pytest`.
Bash helpers are covered through `pytest`+`subprocess` (Phase 2a
decision K1) — there is no separate `bats` runner.

```bash
cd <repo-root>
python -m pip install pytest pytest-cov
pytest scripts/ci/tests/ -v --cov=scripts/ci --cov-report=term-missing
```

`scripts/ci/tests/conftest.py` puts `scripts/ci/` on `sys.path`,
so tests can `import parse_council_report` etc. without a package
install.

## Workflow tests harness

[`workflows/ai-factory-scripts-tests.yml`](./workflows/ai-factory-scripts-tests.yml)
runs three jobs on every PR that touches the AI-Factory surface:

| Job | What it checks |
|---|---|
| `action-validator` | Schema-validates every composite under `.github/actions/` and the `claude-issue-to-pr.yml` workflow via [mpalmer/action-validator](https://github.com/mpalmer/action-validator) `v0.9.0`. |
| `yamllint` | YAML hygiene over the AI-Factory scope using [`.yamllint`](../.yamllint) (line-length warning at 200, `truthy` disabled, etc.). |
| `pytest scripts/ci/tests` | Runs the full Python + bash test suite. Coverage is reported but not gated in Phase 2c. |

The trigger is path-filtered (`scripts/ci/**`,
`.github/actions/**`, `claude-issue-to-pr.yml`,
`ai-factory-scripts-tests.yml`, `.yamllint`) so unrelated PRs do not
run it.

## Issue-to-PR workflow

[`workflows/claude-issue-to-pr.yml`](./workflows/claude-issue-to-pr.yml)
is the Level-1 AI-Factory pipeline (Council S1 → /go → Council S2 →
/go-plan → implement). It is event-driven plus a controlled
`workflow_dispatch` smoke/replay path.

Triggers:
- `issues:[labeled, assigned]` — Council S1 fires when the
  `claude-implement` label is applied or the issue is assigned.
- `issue_comment:[created]` — `/go` (or `/approve`) fires Council S2;
  `/go-plan` fires implementation. Both gated by
  `author_association in {OWNER, MEMBER, COLLABORATOR}` (fork-safety).
- `workflow_dispatch` with `stage = council | plan | implement` for
  smoke/replay. Bypasses the kill-switch.

Kill-switch: set `vars.DISABLE_L1_IMPLEMENT=true` in repo variables to
disable real-event triggers. Dispatch path stays open so operators can
run controlled smokes/replays.

### Running the harness locally

The closest local equivalent runs each tool directly:

```bash
# yamllint (matches the CI scope)
pip install yamllint
yamllint -c .yamllint \
  .github/actions/ \
  .github/workflows/claude-issue-to-pr.yml \
  .github/workflows/ai-factory-scripts-tests.yml \
  .yamllint

# action-validator (linux/amd64 binary; pick the matching asset for macOS)
curl -fsSL "https://github.com/mpalmer/action-validator/releases/download/v0.9.0/action-validator_linux_amd64" \
  -o /tmp/action-validator
chmod +x /tmp/action-validator
for f in .github/actions/*/action.yml \
         .github/workflows/claude-issue-to-pr.yml \
         .github/workflows/ai-factory-scripts-tests.yml; do
  /tmp/action-validator "$f" || echo "FAIL: $f"
done

# pytest
pytest scripts/ci/tests/ -v
```

[`act`](https://github.com/nektos/act) can also drive the workflow
locally (`act pull_request -W .github/workflows/ai-factory-scripts-tests.yml`)
but is not part of the contract — fidelity to GitHub's runtime is not
guaranteed for SHA-pinned third-party actions.

### Known scope limitations

- `yamllint` and `action-validator` only inspect AI-Factory paths.
  Other workflows in `.github/workflows/` use schema dialects that
  `action-validator` rejects despite running fine on GitHub. Bringing
  them in-scope is a separate decision (post Phase 2d).
- Coverage is informational. Phase 2d will decide whether to ratchet.
