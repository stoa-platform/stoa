# STOA PR Guardian — Runbook

Operational surface for the PR Guardian: how to disable, skip, test, iterate,
debug. Anything requiring a decision beyond "run the playbook" belongs in
ADR-065 (stoa-docs), not here.

- **Workflow**: `.github/workflows/pr-guardian.yml`
- **Skill**: `.claude/skills/pr-guardian/SKILL.md`
- **Policy**: `docs/ai/pr-guardian-policy.md`
- **ADR**: [ADR-065](https://github.com/stoa-platform/stoa-docs/blob/main/docs/architecture/adr/adr-065-pr-guardian.md)

---

## Disable globally

Set the repository variable `DISABLE_PR_GUARDIAN=true` on the GitHub repo.

```bash
gh variable set DISABLE_PR_GUARDIAN --body "true" --repo stoa-platform/stoa
```

Effect: workflow triggers on PR events but every job exits early. Visible in
the Actions tab as "skipped". Re-enable by setting the variable to `false`
or deleting it:

```bash
gh variable delete DISABLE_PR_GUARDIAN --repo stoa-platform/stoa
```

Propagation: instant on the next PR event.

## Skip a specific PR

Three ways, pick one:

| Method | When to use |
|---|---|
| Label `skip-guardian` | You disagree with the Guardian on this PR, but keep it enabled elsewhere. |
| Label `wip` | PR is work-in-progress, feedback not useful yet. |
| Convert PR to draft | You want CI to skip reviews entirely, including `claude-review.yml`. |

Add a label:

```bash
gh pr edit <PR_NUM> --add-label skip-guardian
```

Remove the label (or mark PR ready for review) and the Guardian runs again
on the next `synchronize` event, or trigger a manual `gh pr ready`.

## Bot authors — skipped automatically

The workflow condition excludes any author whose login ends with `[bot]`:
Dependabot, Renovate, release-please, github-actions. No action required.

## Fork PRs — skipped automatically

Secrets (ANTHROPIC_API_KEY, Slack webhooks) are not available to fork
workflows by GitHub policy. The Guardian skips fork PRs with a workflow
condition, no comment posted. Internal reviewer owns the call on fork PRs.

## Large diffs — handled automatically

Any PR whose diff exceeds 1000 lines triggers a single comment:

> **STOA PR Guardian — skipped**
> Diff too large for guardian review (N lines > 1000 cap). Human review
> required. Consider splitting this PR per CLAUDE.md rule.

No Slack alert. The split recommendation is the actionable step.

---

## Test locally

You can dry-run the Guardian on any accessible PR without triggering the
workflow. Useful for policy tuning and historical PR replay.

Requirements:

- `gh` authenticated as a user with read access to the repo
- Optional `SLACK_WEBHOOK_STOA_REVIEWS` if you want to test the Slack path
- Claude Code CLI with the skill loaded (it is, if you are on `main`)

Invocation:

```bash
cd ~/hlfh-repos/stoa
claude-code chat "/pr-guardian 2378"
```

Dry-run without Slack (safe default):

```bash
SLACK_WEBHOOK_STOA_REVIEWS= claude-code chat "/pr-guardian 2378"
```

The skill will fetch the PR diff, run the three axes, and emit comments
to your terminal. It will NOT post to GitHub unless you confirm via the
shell prompt.

### Replay on a merged PR

Historical PRs still have fetchable diffs via `gh pr diff`. Replay works
identically — useful when tuning the policy against real past decisions.

```bash
claude-code chat "/pr-guardian 2378"
# Where 2378 is any PR number, open or merged.
```

### Three-PR calibration run

When the policy changes, run the Guardian on three reference PRs to
verify it still behaves as expected:

| PR shape | Expected verdict |
|---|---|
| Small refactor, no secrets, no ADR-touching files | `GO` |
| Known historical security regression | `NO-GO` on `[SEC]` |
| PR with ≥ 3 AI code smell flags (loose fixtures, swallowed exceptions) | `NO-GO` on `[SMELL]` threshold |

Record the verdicts in the PR description of whatever policy change you
are proposing.

---

## Iterate on the policy

The rubric lives in one file: `docs/ai/pr-guardian-policy.md`.

1. Edit the policy file on a branch.
2. Open a PR. The Guardian runs on that PR using the OLD policy (from
   `main`), not the PR version — this is intentional: policy changes are
   reviewed by humans, not self-reviewed.
3. Run the three-PR calibration locally (see above) using the PR branch
   to see how the new policy behaves.
4. Merge. Next PR event picks up the new policy automatically.

No workflow restart, no secret rotation, no infra change.

---

## Known failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Comment says "Guardian unavailable" | Claude action failed (API rate limit, transient 5xx, secret missing) | Check Actions logs; wait for next `synchronize` or push a trivial commit to retry |
| No Guardian comment on a PR that should have one | Kill-switch on, PR is draft, label `skip-guardian`/`wip` present, author is bot, PR is from a fork | Check the job condition in Actions logs; the `if:` evaluated to false |
| Duplicate Guardian comments | `Remove previous Guardian comment` step failed (rate limit, permissions) | Delete the stale one manually; the idempotence step runs best-effort |
| NO-GO posted but no Slack alert | `SLACK_WEBHOOK_STOA_REVIEWS` secret missing or empty | Set the secret; skill logs `::warning::Slack webhook missing` |
| "ADR_LOADER_FETCH_FAILED" in summary | GitHub rate limit, stoa-docs outage, or branch rename | Confidence drops to `low`; verdict still computed from available data |
| Guardian flags a file that was not in the diff | Stale cache or skill bug | Re-run via empty push; if persistent, open an issue against this repo |

## Inspect a run

Actions tab → STOA PR Guardian → pick the PR number in the concurrency group.

Useful fields in the run log:

- Step `Diff size guard` → the computed diff line count
- Step `Run STOA PR Guardian` → the Claude invocation output (execution file)
- Step `Post fallback comment on Guardian failure` → only runs on failure
- `::notice::AI Factory` line → model, outcome, PR number

Raw Claude execution:

```bash
gh run view <RUN_ID> --log | grep -A 200 'Run STOA PR Guardian'
```

---

## Costs

Per PR run:

- Sonnet 4.6, max 20 turns, `--allowedTools Read,Glob,Grep,Bash`
- Typical run: one PR, ≤ 1000-line diff, three ADRs loaded
- Expected cost: low-single-digit cents per PR (monitor via `/token-report`)

Cost controls already in place:

- Concurrency cancel on resync (no duplicate runs for quick pushes)
- Bot/draft/fork skip (no wasted runs on auto-PRs)
- 1000-line diff guard (oversize diffs do not invoke Claude at all)

If token cost trends concerning:

1. Tighten the `max-turns` in the workflow (start: 20, floor: 10)
2. Switch the static ADR list to just the one the diff touches
3. Disable during active refactor sprints via `DISABLE_PR_GUARDIAN=true`

---

## Relationship to other workflows

| Workflow | Relationship |
|---|---|
| `claude-review.yml` | Complementary. Generic vibe check. No plan to retire. |
| `council-gate.yml` | Upstream of the Guardian — runs Stage 3 diff review at push time (pre-PR). Guardian runs at PR time (post-push). Different surfaces, different latencies. |
| `context-compiler-learn.yml` | Independent. Runs on post-merge, not PR-time. |

The Guardian is **one layer** of the review stack. It is not the last line
of defence and it is not the first — it catches a narrow set of failure
modes cheaply, and hands off to humans on everything else.
