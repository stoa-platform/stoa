# Context Compiler — AI Factory Integration

## Overview

The Context Compiler is a feedback loop that predicts impact before coding and learns from actual changes after merge. It is integrated into the AI Factory CI workflows and runs automatically at key lifecycle points.

## Automated Flow

```
Ticket Linear /go
    |
[Hook 1] context-pack job in claude-linear-dispatch.yml
    |     -> build-context.sh generates impact analysis
    |     -> artifact uploaded, impact score passed to Council
    |     -> CRITICAL (>=31) posts warning on Linear ticket
    |
Council validation (Stage 1)
    |
Queue -> Contabo Workers implement (with impact context)
    |
PR opened
    |
[Hook 4] (FUTURE) PR impact comment on claude-auto-review.yml
    |
Merge to main
    |
[Hook 2] context-compiler-learn.yml
    |     -> post-change-learn.sh compares predicted vs actual
    |     -> DB enriched with precision/recall metrics
    |     -> Results committed with [skip ci]
    |
Friday 18:00 UTC
    |
[Hook 3] weekly-impact-review job in claude-self-improve.yml
    |     -> discover-cochanges.sh (50 last commits)
    |     -> regenerate-docs.py
    |     -> dashboard.sh snapshot
    |     -> Results committed with [skip ci]
```

## Hooks

### Hook 1: Pre-Coding Context Pack

**Workflow**: `.github/workflows/claude-linear-dispatch.yml` — `context-pack` job

**Trigger**: `repository_dispatch` event (`linear-ticket-started`)

**What it does**:
1. Extracts component from ticket payload (field `component`, or `[scope]` / `type(scope)` from title)
2. Runs `build-context.sh` with component and intent
3. Uploads context pack as workflow artifact (7-day retention)
4. If Impact Score >= 31 (CRITICAL), posts warning comment on Linear ticket
5. Passes `impact_score` and `impact_level` to the Council job

**Outputs**:
- `impact_score` — numeric score (formula: contracts*2 + P0*5 + P1*2 + untyped*3 + risks*1)
- `impact_level` — LOW / MEDIUM / HIGH / CRITICAL
- `should_block` — `true` if CRITICAL

**Graceful degradation**: If DB, scripts, or file-map are missing, the job outputs score=0 and skips silently.

### Hook 2: Post-Merge Learning

**Workflow**: `.github/workflows/context-compiler-learn.yml`

**Trigger**: Push to `main` (excluding docs, learning data, and `.claude/` paths)

**What it does**:
1. Extracts `CAB-XXXX` ticket reference from commit message
2. Runs `post-change-learn.sh --commit HEAD --ticket CAB-XXXX`
3. Script compares predicted components (from context pack) with actual changed components
4. Calculates precision, recall, F1-score
5. Stores results in `change_log` table in `stoa-impact.db`
6. Generates report in `docs/learning/`
7. Commits DB + report with `[skip ci]` to avoid infinite loops

**Metrics tracked**: True Positives, False Positives, False Negatives per change.

### Hook 3: Weekly Discovery

**Workflow**: `.github/workflows/claude-self-improve.yml` — `weekly-impact-review` job

**Trigger**: Cron Friday 18:00 UTC (same as self-improve)

**What it does**:
1. Runs `discover-cochanges.sh --commits 50` to find component pairs that co-change without contracts
2. Runs `regenerate-docs.py` to update `DEPENDENCIES.md` and `SCENARIOS.md` from DB
3. Generates dashboard snapshot in `docs/learning/weekly-dashboard-YYYYMMDD.txt`
4. Commits all updates with `[skip ci]`

### Hook 4: PR Impact Comment (FUTURE)

**Status**: Not implemented — `claude-auto-review.yml` does not exist yet.

**Planned behavior**: When a PR is opened, analyze modified files, query the impact DB for affected scenarios and contracts, and post an impact analysis comment on the PR.

**Implementation path**: When `claude-auto-review.yml` is created, add a step that:
1. Lists files modified in the PR (`gh pr diff --name-only`)
2. Maps files to components
3. Queries `stoa-impact.db` for scenarios and untyped contracts
4. Posts a markdown comment with the impact report

## Kill Switch

All hooks respect `DISABLE_CONTEXT_COMPILER=true` (GitHub repo variable). When set:
- Hook 1: `context-pack` job is skipped entirely (Council still runs)
- Hook 2: `learn` job is skipped
- Hook 3: `weekly-impact-review` job is skipped

## Database

**Location**: `docs/stoa-impact.db` (SQLite, committed to repo)

Key tables:
- `components` — platform components with repo paths
- `contracts` — inter-component contracts (typed/untyped)
- `scenarios` — end-to-end scenarios with priority
- `scenario_steps` — which components participate in which scenarios
- `risks` — open risks by severity
- `change_log` — post-change learning results (precision, recall, F1)
- `cochange_pairs` — co-change frequency data

## Scripts

| Script | Purpose | Used By |
|--------|---------|---------|
| `docs/scripts/build-context.sh` | Generate context pack for a component/ticket | Hook 1, manual |
| `docs/scripts/post-change-learn.sh` | Compare predicted vs actual changes | Hook 2 |
| `docs/scripts/discover-cochanges.sh` | Find missing contracts from co-change patterns | Hook 3 |
| `docs/scripts/dashboard.sh` | Impact system health dashboard | Hook 3, manual |
| `docs/scripts/regenerate-docs.py` | Regenerate DEPENDENCIES.md and SCENARIOS.md | Hook 3 |

## Manual Usage

The scripts remain available for manual use in local sessions:

```bash
# Before a MEGA ticket
docs/scripts/build-context.sh --component control-plane-api --intent "add audit-log endpoint"

# After merge
docs/scripts/post-change-learn.sh --commit HEAD --ticket CAB-XXXX

# Weekly review
docs/scripts/discover-cochanges.sh --commits 50
docs/scripts/dashboard.sh
```

## Accuracy Tracking

The dashboard (`docs/scripts/dashboard.sh`) reports Context Compiler accuracy from the last 20 changes:
- **Precision**: % of predicted components that were actually modified
- **Recall**: % of actually modified components that were predicted
- **F1-Score**: harmonic mean of precision and recall

Target: F1 > 0.7. Below 0.5 indicates the DB needs contract updates.
