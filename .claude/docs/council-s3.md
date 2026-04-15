<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
description: Council Stage 3 — automated 4-axis code review gate (scripts/council-review.sh)
globs: "scripts/council-review.sh,scripts/council-prompts/**,tests/bats/council-review.bats,.claude/skills/council/SKILL.md,.github/workflows/council-gate.yml"
---

# Council Stage 3 — Automated Code Review

## Overview

Stage 3 is the **post-code-change** Council gate. While S1 validates ticket pertinence and S2 validates the implementation plan, **S3 validates the actual diff** before it reaches main.

It runs `scripts/council-review.sh`, which evaluates a git diff via 4 independent Anthropic API calls and returns a binary verdict.

```
S1 (ticket pertinence)  →  S2 (plan validation)  →  implementation  →  S3 (code review)  →  merge
     council:ticket-*           council:plan-*                         council-review.sh         PR merged
```

S3 is the **only Council stage that reads code instead of prose**. It is the last checkpoint before `git push` / PR merge.

## Invocation

```bash
# Review the default range (origin/main..HEAD)
scripts/council-review.sh --ticket CAB-XXXX

# Review an arbitrary range
scripts/council-review.sh --diff origin/main..feat/my-branch --ticket CAB-XXXX

# Include a Trivy report to enrich the attack_surface axis
scripts/council-review.sh --ticket CAB-XXXX --trivy-report trivy.json

# Mock mode (no API calls, uses fixtures in scripts/council-prompts/fixtures/)
MOCK_API=1 scripts/council-review.sh --ticket CAB-XXXX
```

See `scripts/council-review.sh --help` for the full CLI.

## Exit Codes

| Code | Meaning | Next action |
|------|---------|-------------|
| **0** | `APPROVED` — global score >= 8.0 (or empty diff) | Proceed to push / merge |
| **1** | `REWORK` — global score < 8.0 | Address the blockers/warnings listed per axis, re-run |
| **2** | Technical failure — missing deps, gitleaks block, >= 2 axes errored, etc. | Fix the infra/env issue, re-run |

Exit 2 is **never a verdict**, always an operational failure. Treat it like a CI outage.

## The 4 Axes

Each axis is a dedicated Anthropic call with its own prompt in `scripts/council-prompts/<axis>.md`. The axes run **in parallel** (Step 3c orchestration), each scoring 0–10 with `blockers`, `warnings`, `summary`.

| Axis | Role | Prompt file |
|------|------|-------------|
| `conformance` | Code respects repo conventions (style, naming, structure) | `scripts/council-prompts/conformance.md` |
| `debt` | No shortcuts, TODOs, test gaps, premature abstractions | `scripts/council-prompts/debt.md` |
| `attack_surface` | Security: input validation, authn/z, secrets, SSRF, PII, CORS, deps | `scripts/council-prompts/attack_surface.md` |
| `contract_impact` | Cross-component contracts (API/CRD/events) — **skipped** if `docs/stoa-impact.db` is stale | `scripts/council-prompts/contract_impact.md` |

### Scoring

1. Each axis returns `score` ∈ {0..10}
2. `aggregate_scores` averages the non-errored axes
3. Result:
   - `APPROVED` if `avg >= 8.0` and `errors < 2`
   - `REWORK` if `avg < 8.0` and `errors < 2`
   - `error` (exit 2) if `errors >= 2` or all axes failed

### contract_impact skip logic

If `docs/stoa-impact.db` is missing or older than `DB_STALE_DAYS` (default **7 days**), the `contract_impact` axis is **skipped** and `expected_count=3`. The verdict is then averaged over the 3 remaining axes and the JSONL history entry sets `db_fresh: false`.

All other axes are **always expected** — a missing or empty result file for `conformance`, `debt`, or `attack_surface` counts as an error (never a silent skip).

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ANTHROPIC_API_KEY` | — | Required for real API calls (unset when `MOCK_API=1`) |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-5` | Model used for all 4 axes |
| `ANTHROPIC_MAX_TOKENS` | `1024` | Per-call response cap |
| `ANTHROPIC_TIMEOUT_S` | `30` | Per-call HTTP timeout |
| `LINEAR_API_KEY` | — | Optional — enables `--ticket CAB-XXXX` context fetch from Linear GraphQL |
| `LINEAR_TIMEOUT_S` | `10` | Linear GraphQL HTTP timeout |
| `MOCK_API` | — | Set to `1` to use fixtures in `scripts/council-prompts/fixtures/` — no network |
| `COUNCIL_DISABLE` | — | Set to `1` to short-circuit to APPROVED with `status: BYPASSED` (kill-switch) |
| `COUNCIL_DAILY_CAP_EUR` | `5` | Hard daily budget from `council-history.jsonl` — exit 2 when reached |
| `COUNCIL_FORCE_DEDUP` | — | Set to `1` to skip SHA dedup (force fresh review of an already-seen diff) |
| `COUNCIL_HISTORY_FILE` | `<repo>/council-history.jsonl` | Append-only audit + dedup + cost ledger |
| `TMPDIR` | `/tmp` | Parent of the per-run temp directory |

All Anthropic/Linear credentials come from Vault (`stoa/shared/linear_token`, `stoa/k8s/anthropic_api_key`) in production. Never commit them.

## JSONL History Schema

Each run appends one line to `council-history.jsonl`:

```json
{
  "timestamp": "2026-04-11T18:30:00Z",
  "ticket": "CAB-2047",
  "status": "APPROVED",
  "global_score": 8.75,
  "axes_evaluated": 4,
  "db_fresh": true,
  "model": "claude-sonnet-4-5",
  "tokens": 14230,
  "input_tokens": 12100,
  "output_tokens": 2130,
  "cost_eur": 0.062724,
  "diff_lines": 412,
  "diff_truncated": false,
  "duration_ms": 4821,
  "diff_sha": "a1b2c3d4e5f6..."
}
```

| Field | Type | Notes |
|-------|------|-------|
| `status` | string | `APPROVED` \| `REWORK` \| `error` \| `BYPASSED` |
| `global_score` | number | Average of valid axes (0 when `status=error`) |
| `axes_evaluated` | integer | 0–4 (3 when DB stale) |
| `db_fresh` | bool | `false` when `contract_impact` was skipped |
| `tokens` | integer | `input_tokens + output_tokens` (0 in MOCK_API mode) |
| `cost_eur` | number | Sonnet 4.5 pricing: €2.76/MTok in, €13.80/MTok out |
| `diff_lines` | integer | Lines in the diff (post-truncation if applied) |
| `diff_truncated` | bool | `true` when the diff exceeded `MAX_DIFF_LINES` (10000) |
| `duration_ms` | integer | Wall-clock time from start to verdict |
| `diff_sha` | string | SHA-256 of the canonical diff — used for dedup |

The file is append-only. Rotation is handled in CAB-2050.

## Cost Guardrails

Three independent safeguards, all introduced in Step 2a:

1. **`COUNCIL_DISABLE=1`** — emergency kill-switch. Script exits 0 with `status: BYPASSED`, logs to history, **does not call the API**.
2. **Daily cap** (`COUNCIL_DAILY_CAP_EUR`, default €5) — before each run, the script sums `cost_eur` across today's UTC entries in `council-history.jsonl`. If the sum exceeds the cap, the run exits **2** with an explanatory log line and never calls the API.
3. **SHA dedup** — the script computes SHA-256 of the diff and checks history for an existing entry with the same `diff_sha`. On a hit, it replays the prior verdict (exit 0/1) and does **not** re-call the API. Bypass with `COUNCIL_FORCE_DEDUP=1`.

All three are verified by the Step 2a commit and protected by bats tests (Step 4). In MOCK_API mode, cost is always 0 and the guardrails are no-ops.

## Pre-flight

Before any API call, S3 runs these **Étape 0** checks (Step 1):

1. Required deps present: `git`, `jq`, `curl`, `sqlite3`, `gitleaks`, `shasum`/`sha256sum`
2. `gitleaks detect --no-banner --staged=false --source=<tmpdiff>` — **any** secret in the diff → exit 2
3. Portable `stat` helper (GNU vs BSD)
4. `git diff --numstat` — count lines, compare against `MAX_DIFF_LINES`=10000
5. Truncation: diffs > 10k lines are truncated at 10k lines, `diff_truncated=true` in history

A gitleaks hit is a **hard stop**. Never bypass — fix the secret or use `.gitleaks.toml` allowlist.

## Tests

Unit tests live in `tests/bats/council-review.bats` and use bats-core. They source `council-review.sh` directly (guarded by `[[ "${BASH_SOURCE[0]}" == "${0}" ]]`) and call the pure helpers against fixture tmpdirs.

Coverage:

| Helper | Scenarios |
|--------|-----------|
| `aggregate_scores` | APPROVED (avg >= 8), REWORK (avg < 8), 3 ok + 1 error, 2 errors → exit 2, `contract_impact` skipped, all-errored, score exactly 8.0, missing `conformance` counts as error |
| `sum_usage_tokens` | 4 raws summed, no raws → `0 0`, malformed raw → 0 |
| `compute_cost_eur` | 1M input, 1M output, realistic (12k/2k), zero |

Run:

```bash
bats tests/bats/council-review.bats
```

See `tests/bats/README.md` for the bats convention.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `exit 2` + `gitleaks: secret detected` | Real secret or false positive in diff | Remove the secret or update `.gitleaks.toml` allowlist |
| `exit 2` + `daily cap reached` | `cost_eur` sum today ≥ `COUNCIL_DAILY_CAP_EUR` | Wait for UTC midnight, or raise cap intentionally in CI `vars` |
| `exit 0` but no API call in logs | SHA dedup hit on an existing `council-history.jsonl` entry | Expected. `COUNCIL_FORCE_DEDUP=1` to force a fresh review |
| `axes_evaluated: 3` and `db_fresh: false` | `docs/stoa-impact.db` missing or older than 7 days | Run `docs/scripts/post-change-learn.sh` to refresh, or accept — it's a designed skip |
| `exit 2` + `>=2 axes failed` | API outage, prompt parse error, or rate-limit | Check `${tmpdir}/<axis>.raw` files — re-run after upstream is healthy |
| Wrong verdict on a real diff | Prompt tuning needed | Edit `scripts/council-prompts/<axis>.md`, re-run against the same diff with `COUNCIL_FORCE_DEDUP=1` |
| MOCK_API returns unexpected score | Stale fixtures | Update `scripts/council-prompts/fixtures/<axis>.json` |
| History file fills disk | Not yet rotated | CAB-2050 implements rotation — for now, truncate after review |

## FAQ

**Q: Does S3 replace S1/S2?**
No. S1 checks whether the ticket is worth doing at all (pertinence). S2 checks whether the plan is sound (design). S3 checks whether the code delivers the plan cleanly (implementation). All three are composable and complementary.

**Q: Is my code sent to Anthropic?**
Yes, the diff content is posted to the Messages API. Per Anthropic ToS, API traffic is **not used for training**. For extra safety, gitleaks runs pre-flight to block any secret from leaving the machine.

**Q: Why 4 axes and not 1 big prompt?**
Isolation. Independent axes produce more reliable scores, parallelize cleanly, and let you tune one prompt without affecting the others. The `contract_impact` axis in particular is opt-in based on DB freshness.

**Q: Can I override the 8.0 threshold?**
Not without changing the script. The threshold is hard-coded in `aggregate_scores` so the verdict is binary and reproducible. Calibration happens through prompt tuning, not threshold drift.

**Q: What if I disagree with the verdict?**
Read the per-axis `blockers` and `warnings` in the run output. If they're spurious, tune the prompt (`scripts/council-prompts/<axis>.md`) and re-run with `COUNCIL_FORCE_DEDUP=1`. If you still disagree, override at the PR level with a human review — S3 is a gate, not an oracle.

**Q: Can I run S3 locally before pushing?**
Yes — that's the intended flow for CAB-2048 (pre-push hook extension). Today you can invoke `scripts/council-review.sh` manually on any branch.

## References

- Skill: `.claude/skills/council/SKILL.md` — S1/S2 workflow
- Script: `scripts/council-review.sh` — v0.7.0 (Step 4)
- Prompts: `scripts/council-prompts/{conformance,debt,attack_surface,contract_impact}.md`
- Tests: `tests/bats/council-review.bats`
- Impact DB: `docs/stoa-impact.db` (`docs/DEPENDENCIES.md`, `docs/SCENARIOS.md`)
- Tickets: CAB-2046 (MEGA) → CAB-2047 (script) / CAB-2048 (pre-push) / CAB-2049 (CI) / CAB-2050 (rotation) / CAB-2051 (shadow)
