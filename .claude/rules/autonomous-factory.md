---
description: Autonomous AI Factory levels, kill-switches, Council gate, Slack notifications, n8n integration
globs: ".github/workflows/**"
---

# Autonomous AI Factory — Continuous Improvement Loop

## Overview

The STOA AI Factory operates in 5 levels of autonomy. Each level builds on the previous.
Council validation is the gate between "detecting work" and "doing work".

## Levels

| Level | Name | Trigger | Human Input | Status | Kill-Switch |
|-------|------|---------|-------------|--------|-------------|
| L1 | Interactive | `@claude` mention | Per-request | Active | `DISABLE_L1_INTERACTIVE` |
| L1 | Auto-Review | PR open/sync | Async | Active (hardened) | `DISABLE_L1_REVIEW` |
| L1 | Issue-to-PR | `claude-implement` label | `/go` on issue | Active (hardened) | `DISABLE_L1_IMPLEMENT` |
| L2 | Scheduled | Cron (daily/weekly) | Review digests | Active (hardened) | `DISABLE_L2_SCHEDULED` |
| L3 | Linear Pipeline | Ticket → In Progress | Go/No-Go on Slack | Active (hardened) | `DISABLE_L3_LINEAR` |
| L4 | Self-Improving | Weekly Friday 18:00 | Label `claude-implement` | Active (hardened) | `DISABLE_L4_SELF_IMPROVE` |
| L5 | Multi-Agent | workflow_dispatch | Batch approval | Ready (manual only) | `DISABLE_L5_MULTI_AGENT` |

## Kill-Switches

Every level has a kill-switch via GitHub repository variables (`Settings → Secrets and Variables → Actions → Variables`). Set any variable to `true` to disable that level without code changes.

| Variable | Scope | Effect |
|----------|-------|--------|
| `DISABLE_L1_INTERACTIVE` | L1 Interactive | Stops `@claude` mention responses |
| `DISABLE_L1_REVIEW` | L1 Auto-Review | Stops PR auto-review on open/sync |
| `DISABLE_L1_IMPLEMENT` | L1 Issue-to-PR | Stops Council + `/go` implementation flow |
| `DISABLE_L2_SCHEDULED` | L2 Scheduled | Stops all daily/weekly cron tasks |
| `DISABLE_L3_LINEAR` | L3 Linear Pipeline | Stops Linear → Council → PR pipeline |
| `DISABLE_L4_SELF_IMPROVE` | L4 Self-Improving | Stops weekly retrospective analysis |
| `DISABLE_L5_MULTI_AGENT` | L5 Multi-Agent | Stops parallel ticket implementation |

To disable ALL autonomous activity at once, set each variable to `true`. There is no single master switch — this is intentional so levels can be toggled independently.

## Hardening (H24)

All workflows include these safety measures:
- **`continue-on-error: true`** on all Claude Code Action steps — failures are non-blocking
- **Fallback comments** — if Claude fails, a fallback issue/comment is posted with a link to workflow logs
- **Diff truncation** (L1 Review) — PR diffs are truncated to 500 lines to prevent context overflow
- **Council gate** (L1 Issue-to-PR) — `council-validated` label required before `/go` triggers implementation
- **Ask mode enforcement** — rule changes (`.claude/rules/`) are always Ask mode, never auto-merged
- **Timeouts** — every job has an explicit `timeout-minutes` (15-60)
- **Concurrency groups** — prevent parallel runs on the same issue/PR
- **Council dedup guards** — label-based state machine prevents double Council runs (see below)

### Council Label State Machine

Labels track the Council pipeline state on each GitHub issue. Guards at each stage prevent re-runs:

```
[no labels]
  → council-validated    (S1 passed — ticket pertinence)
  → ship-fast-path       (optional — Ship ≤5pts, S2 will be skipped)
  → plan-validated       (S2 passed — plan validation, or auto-set by fast-path)
```

| Guard | Workflow | Prevents |
|-------|----------|----------|
| Skip S1 if `council-validated` exists | L1 (issue-to-pr) | Re-labeling `claude-implement` re-runs Council |
| Skip S2 if `plan-validated` exists | L1 (issue-to-pr) | Re-commenting `/go` re-runs plan validation |
| Skip issue creation if ticket label exists | L3 (linear-dispatch) | n8n re-dispatch creates duplicate issues |
| Skip issue creation if ticket label exists | L3.5 (autopilot-scan) | Daily scan creates duplicate issues |

**Cross-workflow dedup**: L3 and L3.5 both create issues with `{TICKET_ID}` as a label. Before creating, they search for open issues with that label. If found, the new Council report is posted as a comment on the existing issue instead.

## H24 Scaling — Progressive Velocity Control

### Model Routing (Tiered)

All implementation workflows use `scripts/ai-ops/model-router.sh` for cost-optimized model selection:

| Estimate | Mode | Model | Max Turns | Est. Cost/Ticket |
|----------|------|-------|-----------|-----------------|
| ≤3 pts | Ship | Sonnet | 25 | ~$7 |
| ≤8 pts | Any | Sonnet | 40 | ~$12 |
| >8 pts | Any | Sonnet | 60 | ~$16.50 |

Weighted average: ~$11/ticket. Haiku dropped from implementation routing (PR #737) — lacks capacity for branch creation, code gen, and PR workflows.

### Ship Fast Path (Skip Stage 2)

For Ship-mode tickets ≤5 pts, Stage 2 (plan validation) is skipped entirely:
- L3: `implement-fast` job runs directly after Council S1 (no `/go` needed)
- L1: `ship-fast-path` label triggers auto-skip of plan-validate step

Savings: ~$3/ticket (skips Sonnet S2 call) + ~5 min latency reduction.

### Velocity Cap (`AUTOPILOT_DAILY_MAX`)

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOPILOT_DAILY_MAX` | `5` | Max tickets/day for autopilot + self-feeding loop |
| `AUTOPILOT_TODAY_COUNT` | `YYYY-MM-DD:N` | Current day's counter (auto-managed) |

Progressive scaling phases:
| Phase | Duration | Daily Max | Monthly Est. |
|-------|----------|-----------|-------------|
| Ramp | Week 1 | 5 | ~$300 |
| Cruise | Week 2 | 8 | ~$400 |
| Full | Week 3 | 12 | ~$500 |
| Sustain | Week 4+ | 10 | ~$400 |

Adjust `AUTOPILOT_DAILY_MAX` via GitHub repo variables — no code change needed.

## Council Gate — Mandatory Validation

**Every autonomous action MUST pass Council validation before execution.**

### When Council Runs

**Two-Stage Gate** (L1 Issue-to-PR, L3 Linear Dispatch):
- **Stage 1** — Ticket Pertinence: "Is this ticket worth implementing?" → `council:ticket-*` labels
- **Stage 2** — Plan Validation: "Is this implementation plan correct?" → `council:plan-*` labels
- **Ship Fast Path** — ≤5pt Ship tickets skip Stage 2 entirely

| Trigger | Stage | Council Mode | Model | Threshold | Approval |
|---------|-------|-------------|-------|-----------|----------|
| Issue labeled `claude-implement` | Stage 1 | Full (4 personas, detailed) | Sonnet | >= 8.0 | `/go` → Stage 2 |
| `/go` on Stage 1 issue | Stage 2 | Full (4 personas, plan-focused) | Sonnet | >= 8.0 | `/go-plan` → implement |
| `/go` on Stage 1 (Ship ≤5pt) | Fast Path | Skipped | — | — | Auto → implement |
| Linear ticket → In Progress | Stage 1 | Full (4 personas, detailed) | Sonnet | >= 8.0 | `/go` → Stage 2 |
| `/go` on council-review issue | Stage 2 | Full (4 personas, plan-focused) | Sonnet | >= 8.0 | `/go-plan` → implement |
| Linear dispatch (Ship ≤5pt) | Fast Path | Skipped | — | — | Auto → implement |
| Multi-agent batch dispatch | Stage 1 only | Quick (4 personas, scores only) | Sonnet | >= 8.0 | `/go-batch` |
| Autopilot backlog scan | Stage 1 only | Quick (4 personas, scores only) | Haiku | >= 8.0 | Slack → `/go` |
| Scheduled CI auto-fix | Skip | — | — | N/A | Auto |
| Self-improvement proposal | Stage 1 only | Full (analysis, no code) | Sonnet | >= 8.0 | Label `claude-implement` |
| PR auto-review | Skip | — | — | N/A | Auto |
| Daily triage | Skip | — | — | N/A | Auto |

### Council-Free Actions (Auto-Approved)

These actions skip Council because they are read-only or trivially reversible:
- PR review comments (no code changes)
- Issue triage and labeling
- Daily/weekly digest generation
- CI failure diagnosis (without auto-fix)
- Plan sync (`/sync-plan`)

### Council Report Format (Slack)

Every Council report posted to Slack MUST include:

```
:emoji: Council: TICKET-ID — X.XX/10 [Go|Fix|Redo]

*Title of the change*

Context: <1-2 sentences on what and why>

| Persona | Score | Verdict |
|---------|-------|---------|
| Chucky | X/10 | Go |
| OSS Killer | X/10 | Go |
| Archi | X/10 | Fix |
| Saul | X/10 | Go |

Ship/Show/Ask: [mode]
Est. LOC: ~XXX
Files: N files in [component]

[Review & Approve] → link to GitHub issue
```

### Approval Flow (Two-Stage)

```
Stage 1: Ticket Pertinence
  Council validates ticket → Slack notification → council:ticket-* label on Linear
    ├── User comments `/go` → Stage 2 starts (plan validation)
    ├── User comments `/adjust <feedback>` → Council re-runs with feedback
    └── No response in 24h → Reminder sent, then auto-close after 72h

Stage 2: Plan Validation (L1 + L3 only)
  Council validates plan → Slack notification → council:plan-* label on Linear
    ├── User comments `/go-plan` → Implementation starts
    ├── User comments `/adjust <feedback>` → Plan re-validated with feedback
    └── No response in 24h → Reminder sent

Batch flows (L3.5 Autopilot, L5 Multi-Agent): Stage 1 only → `/go` starts implementation directly.
```

## Notification Library

All AI Factory notifications use `scripts/ai-ops/ai-factory-notify.sh` — a centralized shell library sourced by every workflow step. Zero extra Claude tokens (pure bash + jq).

### Usage

```yaml
- name: Notify
  env:
    SLACK_WEBHOOK: ${{ secrets.SLACK_WEBHOOK_URL }}
  run: |
    source scripts/ai-ops/ai-factory-notify.sh
    notify_council "CAB-1350" "Title" "8.5" "Go" "https://..." "42"
```

### Functions

| Function | Signature | Purpose |
|----------|-----------|---------|
| `notify_council` | `TICKET TITLE SCORE VERDICT ISSUE_URL [ISSUE_NUM] [MODE] [LOC] [FILES]` | Council report + approve button |
| `notify_implement` | `TICKET STATUS [PR_NUM] [PR_URL] [ISSUE_NUM] [PIPELINE] [DURATION_SECS] [FILES] [LOC]` | Implementation result |
| `notify_error` | `WORKFLOW JOB [TICKET] [EXEC_FILE] [DURATION_SECS]` | Vercel-style error with log excerpt + retry button |
| `notify_scan` | `TOTAL CREATED [CAPPED]` | Autopilot scan summary |
| `notify_scheduled` | `TASK STATUS [DETAIL]` | Daily/weekly task results |
| `notify_plan` | `TICKET TITLE SCORE VERDICT ISSUE_URL [ISSUE_NUM]` | Plan validation (Stage 2) |
| `linear_comment` | `TICKET STATUS [PR_NUM] [PR_URL] [PIPELINE] [DURATION_SECS] [FILES] [LOC] [MODE]` | Rich markdown report on Linear |
| `write_job_summary` | `TICKET STATUS [PR_NUM] [MODEL] [PIPELINE] [DURATION_SECS] [ERROR_EXCERPT]` | GHA audit trail |
| `_react_slack` | `EMOJI MESSAGE_TS` | Add emoji reaction to a Slack message (internal, no-op if Bot API unconfigured) |

All optional `[params]` degrade gracefully — omit or pass empty string. Duration in seconds (formatted by `_format_duration`). Linear links are deterministic URLs (no API call).

### Env Vars (all optional, graceful degradation)

| Variable | Source | Used By |
|----------|--------|---------|
| `SLACK_WEBHOOK` | `secrets.SLACK_WEBHOOK_URL` | All `notify_*` functions |
| `SLACK_BOT_TOKEN` | `secrets.SLACK_BOT_TOKEN` | `_send_slack_bot()`, `_react_slack()` |
| `SLACK_CHANNEL_ID` | `secrets.SLACK_CHANNEL_ID` | `_send_slack_bot()`, `_react_slack()` |
| `SLACK_THREAD_TS` | Env var (captured or from n8n payload) | `_send_slack()` — threads all notifications under this ts |
| `LINEAR_API_KEY` | `secrets.LINEAR_API_KEY` | `linear_comment()` only |
| `N8N_WEBHOOK` | `vars.N8N_APPROVE_WEBHOOK_URL` | `notify_council` approve button |
| `HMAC_SECRET` | `secrets.APPROVE_HMAC_SECRET` | `notify_council` approve button |
| `GITHUB_RUN_ID` | Auto-set by GHA | All functions (run link) |
| `GITHUB_STEP_SUMMARY` | Auto-set by GHA | `write_job_summary` |

### Duration Tracking Pattern

Every implementation job records start time before the Claude action:
```yaml
- name: Record Start Time
  run: echo "IMPL_START=$(date +%s)" >> "$GITHUB_ENV"
```
Then computes duration in the notification step: `DURATION=$(( $(date +%s) - ${IMPL_START:-$(date +%s)} ))`

### Rules

- Every workflow step that previously had inline `curl $SLACK_WEBHOOK` now uses `source ... && notify_*`
- `write_job_summary` is called in ALL 8 Claude workflows for persistent audit trail
- Notifications are best-effort: `SLACK_WEBHOOK` unset = silent skip, never fails the parent step
- Linear comments only on implementation success/failure (not Council, not scheduled — too noisy)
- Implementation failures use `notify_error` (Vercel-style) instead of `notify_implement` for richer diagnostics
- PR stats (`FILES`, `LOC`) extracted via `gh pr diff "$PR_NUM" --stat | tail -1`
- Deprecated scripts: `slack-notify.sh`, `council-slack-report.sh`, `daily-digest.sh` (use library instead)

### Threading & Reactions (Phase 3)

All notifications from a pipeline run are threaded under the initial message using `SLACK_THREAD_TS`:

| Pipeline | Threading Source | Reaction Sequence |
|----------|-----------------|-------------------|
| L3 (council → implement-fast) | n8n `slack_thread_ts` or captured from Council ts | :mag: → :hammer_and_wrench: → :rocket: → :tada: / :x: |
| L3 (plan-validate, implement) | Each captures its own ts (separate workflow runs) | :white_check_mark: (plan), :hammer_and_wrench: → :rocket: → :tada: / :x: (impl) |
| L1 (council, plan, implement) | Each captures its own ts (separate workflow runs) | :mag: (council), :white_check_mark: (plan), :tada: / :x: (impl) |
| L3.5 (scan) | Each council + scan summary captures own ts | :mag: (per candidate), :satellite_antenna: (summary) |

**Env var fallback**: `_send_slack()` resolves thread_ts as `$2` (explicit) > `$SLACK_THREAD_TS` (env) > empty (no threading). Setting `SLACK_THREAD_TS` in the env automatically threads all `notify_*` calls without changing their signatures.

**Reactions**: `_react_slack EMOJI TS` adds an emoji reaction via `reactions.add` API. No-op if `SLACK_BOT_TOKEN` or `SLACK_CHANNEL_ID` is unset. Non-blocking — failures are logged as warnings.

### Progress Streaming Milestones

Implementation jobs post thread-reply milestones via `_reply_slack()`:

| Milestone | When | Message |
|-----------|------|---------|
| Implementation Starting | After Record Start Time, before Claude action | `:hammer_and_wrench: Implementation started — {model} / {turns} turns` |
| PR Created | After Detect Partial Success, before Close the Loop | `:rocket: PR #{num} created — CI running` |

Both milestones use `continue-on-error: true` and are non-blocking. Thread parent is `SLACK_THREAD_TS` (from n8n dispatch or captured from previous step).

## Slack `/stoa` Slash Command

n8n workflow (`scripts/ai-ops/n8n-stoa-slash-command.json`) handles `/stoa` commands from Slack:

| Command | Tier | Action |
|---------|------|--------|
| `/stoa help` | all | Ephemeral help text (available commands + access level) |
| `/stoa status` | all | Fetch 5 recent GHA workflow runs, format, send via `response_url` |
| `/stoa scan` | admin | Trigger `claude-autopilot-scan.yml` via `workflow_dispatch` |
| `/stoa implement CAB-XXXX` | admin | Validate ticket format, trigger `repository_dispatch linear-ticket-started` |

**Setup** (manual): Slack App → Slash Commands → `/stoa` → Request URL: `https://hlfh.app.n8n.cloud/webhook/stoa-slash-command`

**Pattern**: Immediate 200 ACK (Slack requires <3s) → deferred response via `response_url` POST.

### Access Control Tiers

3-tier access system in `n8n-slack-interactive.json` and `n8n-stoa-slash-command.json`:

| Tier | Env Variable | Permissions |
|------|-------------|-------------|
| `admin` | `SLACK_ADMIN_USERS` | All actions (scan, implement, approve, merge) |
| `allowed` | `SLACK_ALLOWED_USERS` | Approve + merge only |
| `readonly` | (everyone else) | 403 forbidden |

**Backward compatible**: Empty `SLACK_ADMIN_USERS` = all allowed users are admins (existing behavior preserved).

## GitHub Labels for Automation

| Label | Trigger | What Happens |
|-------|---------|-------------|
| `claude-implement` | Added to issue | Council validates → Slack → wait for `/go` → implement |
| `council-review` | Auto-added | Issue has a Council report pending review |
| `ship-fast-path` | Auto-added by S1 | Ship ≤5pt ticket, Stage 2 skipped |
| `self-improve` | Auto-added | Self-improvement proposal |
| `daily-digest` | Auto-added | Daily triage digest |
| `weekly-audit` | Auto-added | Weekly audit report |
| `ci-failure` | Auto-added | CI failure requiring human intervention |
| `coverage-drop` | Auto-added | Test coverage regression |

### Linear Council Labels

| Label | Stage | Score Range | Color | Description |
|-------|-------|-------------|-------|-------------|
| `council:ticket-go` | Stage 1 (Pertinence) | >= 8.0 | green (#0e8a16) | Ticket validated |
| `council:ticket-fix` | Stage 1 (Pertinence) | 6.0 - 7.9 | amber (#e4b400) | Ticket needs adjustments |
| `council:ticket-redo` | Stage 1 (Pertinence) | < 6.0 | red (#d73a49) | Ticket rejected |
| `council:plan-go` | Stage 2 (Plan) | >= 8.0 | teal (#006b75) | Plan validated |
| `council:plan-fix` | Stage 2 (Plan) | 6.0 - 7.9 | dark amber (#b45309) | Plan needs revision |
| `council:plan-redo` | Stage 2 (Plan) | < 6.0 | dark red (#8b0000) | Plan rejected |

## n8n Integration

### Linear → GitHub Pipeline

n8n workflow (`scripts/ai-ops/n8n-linear-to-claude.json`):
1. Linear webhook fires when ticket status → "In Progress"
2. n8n filters for "In Progress" only
3. n8n dispatches `repository_dispatch` to GitHub Actions
4. n8n posts "Pipeline Started" to Slack

### Dispatch Payload Schema

The `repository_dispatch` `client_payload` includes phase-aware fields:

```json
{
  "ticket_id": "CAB-1350",
  "ticket_title": "Traceparent injection",
  "ticket_description": "...",
  "priority": 2,
  "estimate": 5,
  "mega_id": "CAB-1290",
  "phase_hint": 1,
  "component": "gateway"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `ticket_id` | Yes | Linear issue identifier (e.g., `CAB-1350`) |
| `ticket_title` | Yes | Issue title |
| `ticket_description` | Yes | Full issue description + DoD |
| `priority` | Yes | Linear priority (1=Urgent, 4=Low) |
| `estimate` | No | Story points |
| `mega_id` | No | Parent MEGA ticket ID. If present, the dispatched agent checks `.claude/claims/<mega_id>.json` for phase ownership before starting. Prevents L3-dispatched agents from conflicting with local instances. |
| `phase_hint` | No | Suggested phase number within the MEGA. The agent uses this to claim the correct phase instead of scanning all MEGAs. |
| `component` | No | Target component (api, gateway, ui, portal, e2e). Used to select the right CI quality gate. |

**n8n enrichment**: When a ticket has a `parent` in Linear, n8n resolves the parent ID and includes it as `mega_id`. The `phase_hint` is extracted from the ticket's position in the parent's sub-issues list.

### Setup Requirements

1. **n8n**: Import `n8n-linear-to-claude.json`
2. **Linear**: Configure webhook pointing to n8n webhook URL
3. **GitHub**: Add PAT as n8n HTTP Header Auth credential
4. **Slack**: Set `SLACK_WEBHOOK` environment variable in n8n

## Cost Control

| Guard | Value | Why |
|-------|-------|-----|
| Model routing | `model-router.sh` — Sonnet tiers by estimate, MODE-aware | ~60% savings on small tickets |
| Ship fast-path | Skip S2 for ≤5pt Ship tickets | ~$3 + 5min saved per ticket |
| Ship turn budget | Ship ≤3pt → 20 turns (vs 25 default) | Tighter budget for trivial changes |
| Velocity cap | `AUTOPILOT_DAILY_MAX` (default 5) | Daily budget ceiling |
| Velocity tracking | Autopilot scan increments `AUTOPILOT_TODAY_COUNT` after creating issues | Prevents exceeding daily cap |
| Precise matching | Ticket ID regex with word boundaries | Prevents CAB-1 matching CAB-123 |
| Max turns per agent | 20/25/40/60 (tiered by estimate + mode) | Prevent runaway costs |
| Default model | Sonnet (code gen), Haiku (council scan) | Right model per task |
| Council threshold | 8.0 (all levels) | Harmonized — no per-level exceptions |
| Max parallel agents | 3 | Cost caps at ~3x single agent |
| Timeout per job | 15-60 min | Hard stop on runaway jobs |
| Skip Council S2 for | Ship-mode ≤5 pts | Avoid unnecessary plan validation |
| Schedule frequency | Daily/weekly (not hourly) | Control API usage |
| Kill-switch model | `CLAUDE_DEFAULT_MODEL` repo var | Revert all tiers to Sonnet |

## Security

- `ANTHROPIC_API_KEY`: GitHub repo secret, never logged
- `SLACK_WEBHOOK_URL`: GitHub repo secret
- Claude runs on GitHub-hosted runners (code stays on GitHub infra)
- No `--dangerously-skip-permissions` in any workflow
- Council prevents unauthorized changes (human gate)
- All PRs still go through standard CI + security scan
