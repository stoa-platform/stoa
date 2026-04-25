# FIX-PLAN — CI-1 Phase 2d (Switch Final) — REV 2

**Branche** : `refactor/ci-1-phase-2d-switch`
**Status** : DRAFT v2 — incorporates user review of v1
**Refs** : CAB-2166, CI-1-REWRITE-PLAN.md §F

> **REV 2 changes vs v1**: keep `prepare` (don't drop it); kill-switch bypass for `workflow_dispatch`; replace `run_implement: bool` with `stage: choice`; gate label/Linear/comment side-effects on verdict (not just outcome) to fix the "label after Claude fail" bug; restore legacy auto-`/go-plan` in ship fast-path comment for event-chain parity.

---

## TL;DR

Phase 2d retires the legacy `claude-issue-to-pr.yml` and rewires `claude-issue-to-pr-v2.yml` to events. **`prepare` stays** as the input-normalization layer for events + dispatch. Three operational jobs (`council-validate`, `plan-validate`, `implement`) keep `needs: prepare` but **don't chain to each other** — each one fires from its own event (or dispatch with `stage=...`).

Net delta: delete 797 LOC (legacy) + modify ~100 LOC inside v2 (triggers, `if:` filters, label-gating, restore guards, fast-path parity). Rename `-v2.yml` → canonical `claude-issue-to-pr.yml`.

---

## A. Decisions confirmed

| | Decision | Confirmed |
|---|---|---|
| A1 | Trigger `types:` for `issues:` | `[labeled, assigned]` (legacy-exact) |
| A2 | v2 filename post-switch | rename `-v2.yml` → `claude-issue-to-pr.yml` |
| A3 | `vars.DISABLE_L1_IMPLEMENT` at merge | stays `true`; bypass for `workflow_dispatch` |
| A4 | `prepare` job | **kept** (reverse of v1) |
| A5 | Dispatch input | `stage: council|plan|implement` (not `run_implement: bool`) |
| A6 | Stage 1 verification in `plan-validate` | re-add with `outputs.validated` + step gating |
| A7 | `author_association` guard | re-add to `plan-validate` and `implement` |
| A8 | Label/Linear/comment side-effects | gate on `verdict ∈ {go, fix, redo}`, not just `outcome == success` |
| A9 | Ship fast-path auto-`/go-plan` | restore (legacy parity, currently missing in v2) |

---

## B. Triggers — final shape

```yaml
on:
  issues:
    types: [labeled, assigned]
  issue_comment:
    types: [created]
  workflow_dispatch:
    inputs:
      issue_number:
        description: 'Issue number'
        required: true
        type: string
      stage:
        description: 'Stage to dispatch (smoke/replay knob)'
        required: true
        type: choice
        default: council
        options: [council, plan, implement]
```

`stage` selection means dispatch fires exactly one job — no implicit chaining inside a single dispatch run. Smoke sequence becomes 3 separate dispatches, each verifiable independently.

**Concurrency**:

```yaml
concurrency:
  group: claude-issue-${{ github.event.issue.number || inputs.issue_number }}
  cancel-in-progress: false
```

(Matches legacy prefix; serializes per-issue across event + dispatch paths.)

**Permissions**: unchanged — `contents/pull-requests/issues/id-token: write`.

---

## C. `prepare` job — kept, generalized

`prepare` becomes the single normalization layer for both event and dispatch. It runs unconditionally for every workflow trigger and exposes `title/body/url/number/ticket-id`.

```yaml
jobs:
  prepare:
    if: |
      github.event_name == 'workflow_dispatch' ||
      vars.DISABLE_L1_IMPLEMENT != 'true'
    runs-on: ubuntu-latest
    timeout-minutes: 3
    outputs:
      title: ${{ steps.fetch.outputs.title }}
      body: ${{ steps.fetch.outputs.body }}
      url: ${{ steps.fetch.outputs.url }}
      number: ${{ steps.fetch.outputs.number }}
      ticket-id: ${{ steps.fetch.outputs.ticket-id }}
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd  # v6
      - name: Resolve issue payload
        id: fetch
        env:
          GH_TOKEN: ${{ github.token }}
          # Single source of truth: dispatch input takes precedence; otherwise
          # use the event's issue number (works for issues + issue_comment).
          ISSUE_NUMBER: ${{ inputs.issue_number || github.event.issue.number }}
        run: |
          set -uo pipefail
          source "${GITHUB_WORKSPACE}/scripts/ci/gh_helpers.sh"
          RAW=$(gh issue view "$ISSUE_NUMBER" --json title,body,url)
          TITLE=$(printf '%s' "$RAW" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["title"])')
          URL=$(printf   '%s' "$RAW" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["url"])')
          BODY=$(printf  '%s' "$RAW" | python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["body"] or "")')
          TICKET=$(extract_ticket_id "$TITLE $BODY")
          {
            echo "number=${ISSUE_NUMBER}"
            echo "title=${TITLE}"
            echo "url=${URL}"
            echo "ticket-id=${TICKET}"
            echo "body<<CI1_BODY_EOF"
            printf '%s\n' "$BODY"
            echo "CI1_BODY_EOF"
          } >> "$GITHUB_OUTPUT"
```

**Key changes vs current v2**:
- `if:` now allows `workflow_dispatch` to bypass kill-switch.
- `ISSUE_NUMBER` env resolves from dispatch input OR event payload (was dispatch-only).
- `outputs.number` is now derived from the resolved number, not bound to `inputs.issue_number` (which is empty on event triggers).
- All 49 existing `needs.prepare.outputs.*` references in v2 stay as-is — **no retargeting**.

---

## D. Per-job `if:` guards

The pattern for every operational job:

```yaml
if: |
  (
    github.event_name == 'workflow_dispatch' ||
    vars.DISABLE_L1_IMPLEMENT != 'true'
  ) &&
  needs.prepare.result == 'success' &&
  (
    <legacy event clause> ||
    (github.event_name == 'workflow_dispatch' && inputs.stage == '<job-stage>')
  )
```

The `vars.DISABLE_L1_IMPLEMENT` check is OR'd with the dispatch event so the kill-switch only blocks **real** events. `needs.prepare.result == 'success'` ensures we don't run downstream if `gh issue view` failed.

### D.1 `council-validate`

```yaml
needs: prepare
if: |
  (github.event_name == 'workflow_dispatch' || vars.DISABLE_L1_IMPLEMENT != 'true') &&
  needs.prepare.result == 'success' &&
  (
    (github.event_name == 'issues' && github.event.label.name == 'claude-implement') ||
    (github.event_name == 'issues' && github.event.action == 'assigned') ||
    (github.event_name == 'workflow_dispatch' && inputs.stage == 'council')
  )
```

### D.2 `plan-validate`

```yaml
needs: prepare
if: |
  (github.event_name == 'workflow_dispatch' || vars.DISABLE_L1_IMPLEMENT != 'true') &&
  needs.prepare.result == 'success' &&
  (
    (
      github.event_name == 'issue_comment' &&
      contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.comment.author_association) &&
      (
        github.event.comment.body == '/go' ||
        github.event.comment.body == '/approve' ||
        startsWith(github.event.comment.body, '/go ') ||
        startsWith(github.event.comment.body, '/approve ')
      )
    ) ||
    (github.event_name == 'workflow_dispatch' && inputs.stage == 'plan')
  )
```

**No `needs: council-validate`** — plan-validate fires on its own event (`/go` comment OR dispatch). Stage 1 is verified inside the job (§D.4), not via job dependency.

### D.3 `implement`

```yaml
needs: prepare
if: |
  (github.event_name == 'workflow_dispatch' || vars.DISABLE_L1_IMPLEMENT != 'true') &&
  needs.prepare.result == 'success' &&
  (
    (
      github.event_name == 'issue_comment' &&
      contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.comment.author_association) &&
      (
        github.event.comment.body == '/go-plan' ||
        startsWith(github.event.comment.body, '/go-plan ')
      )
    ) ||
    (github.event_name == 'workflow_dispatch' && inputs.stage == 'implement')
  )
```

`wait-for-label` composite (already in v2) handles Stage 2 verification.

### D.4 Stage 1 verification step (new, inside `plan-validate`)

Re-introduced from legacy. Runs as the FIRST step after checkout, before any Council work:

```yaml
- name: Verify Stage 1 Council
  id: verify-stage1
  env:
    GH_TOKEN: ${{ github.token }}
    ISSUE_NUMBER: ${{ needs.prepare.outputs.number }}
  run: |
    set -uo pipefail
    LABELS=$(gh issue view "$ISSUE_NUMBER" --json labels --jq '.labels[].name' 2>/dev/null || echo "")
    if echo "$LABELS" | grep -q "council-validated"; then
      echo "Stage 1 confirmed via label"
      echo "validated=true" >> "$GITHUB_OUTPUT"
      exit 0
    fi
    # Fallback: scan comments for Council Score (legacy parity)
    HAS_COMMENT=$(gh issue view "$ISSUE_NUMBER" --json comments \
      --jq '[.comments[].body | select(contains("Council Score"))] | length')
    if [ "${HAS_COMMENT:-0}" -gt 0 ]; then
      echo "Stage 1 confirmed via comment fallback"
      echo "validated=true" >> "$GITHUB_OUTPUT"
    else
      echo "::notice::No Stage 1 Council on this issue — skipping plan validation"
      echo "validated=false" >> "$GITHUB_OUTPUT"
    fi
```

All subsequent steps in `plan-validate` get `if: steps.verify-stage1.outputs.validated == 'true' && <existing guard>`. No silent `exit 0` — the job runs, but every operational step is no-op'd.

---

## E. Side-effect gating fix (label after Claude failure)

This was the bug surfaced in Phase 2b smokes: `council-validated` got applied even though the Council step failed.

### E.1 Root cause

Current v2 line 143:
```yaml
if: steps.council.outputs.outcome == 'success' || steps.guard.outputs.already-set == 'true'
```

`outcome == 'success'` is the action-step exit code, not the Council content quality. If `parse_council_report.py` runs but produces an empty verdict (e.g. Claude exhausted max-turns mid-rubric), `outcome` is `success` but verdict is `''`. The label gets applied to a non-validated issue.

### E.2 Fix — verdict-gated handshakes

Apply to **every** label/comment/Linear-sync side-effect:

| Site (v2 line) | Current `if:` | Replace with |
|---|---|---|
| Apply `council-validated` (143) | `outcome == success || already-set` | `(outcome == success && contains(fromJSON('["go","fix","redo"]'), verdict)) || already-set` |
| Apply `ship-fast-path` (153) | `outcome == success` | `outcome == success && verdict == 'go' && mode == 'ship'` (already derived from estimate) |
| `council-sync-linear` (170) | `outcome == success` | `outcome == success && contains(fromJSON('["go","fix","redo"]'), verdict)` |
| Apply `plan-validated` (292) | `plan.outcome == success` | `plan.outcome == success && contains(fromJSON('["go","fix","redo"]'), plan.verdict)` |
| Apply `plan-validated` via fast-path (231) | `fast-path.already-set == true` | unchanged (idempotent re-apply of an already-set fast-path label) |
| `council-sync-linear` plan (302) | `plan.outcome == success` | same fix as council site |

### E.3 Restore auto-`/go-plan` in ship fast-path

Legacy line 350 emits `/go-plan` in the auto-comment so the implement job fires from a comment event. v2 line 240 omits it — regression vs legacy.

Fix in commit 2:
```diff
- gh issue comment "$ISSUE_NUMBER" \
-   --body "Ship fast-path: Stage 2 skipped (small Ship-mode change). Auto-triggering implementation."
+ gh issue comment "$ISSUE_NUMBER" \
+   --body $'Ship fast-path: Stage 2 skipped (small Ship-mode change). Auto-triggering implementation.\n\n/go-plan'
```

The `$''` ANSI-C quoting interprets `\n` correctly so `/go-plan` is on its own line — required for `startsWith` matching against multi-line comment bodies.

---

## F. Pause marker (`docs/ops/ai-factory-pause.md`)

Unchanged from v1 plan — committed in commit 1, deleted post-validation. Content unchanged except the `Expected end` note now reflects the soak duration in §H (24h).

---

## G. Phase 2 — execution plan (commit-by-commit)

| # | Commit | Files | Goal |
|---|---|---|---|
| 1 | `docs(ops): announce AI-Factory pause for CI-1 phase 2d` | `docs/ops/ai-factory-pause.md` (new) | Pause marker visible. |
| 2 | `ci(ai-factory): rewire workflow to events with dispatch-stage smoke` | `.github/workflows/claude-issue-to-pr-v2.yml` | All §B + §C + §D + §E changes. |
| 3 | `ci(ai-factory): retire legacy + rename v2 to canonical name` | `git rm claude-issue-to-pr.yml` then `git mv claude-issue-to-pr-v2.yml claude-issue-to-pr.yml` | Single-commit cutover. |
| 4 | `docs: update .github/README.md post phase 2d` | `.github/README.md` | Reflect single workflow + dispatch usage. |

Commit 2 is large (~80 LOC delta in one file); to keep it reviewable, the diff should be ordered: triggers/concurrency → prepare bypass → council-validate guards → plan-validate guards + Stage 1 step → implement guards → label-gating fixes → fast-path /go-plan restore.

PR opens after commit 4. CI runs `ai-factory-scripts-tests.yml` (path-filter triggered) → must pass before merge.

---

## H. Validation post-switch

### H.1 Pre-merge gates

- [ ] `ai-factory-scripts-tests.yml` green on PR (action-validator + yamllint + pytest).
- [ ] `vars.DISABLE_L1_IMPLEMENT` confirmed `true` in repo at merge time.
- [ ] Commit 2 contains: bypass logic in 3 jobs + author_association in 2 jobs + Stage 1 verify step + verdict gating on 5 sites + `/go-plan` restored in fast-path.
- [ ] Pause marker landed in commit 1.

### H.2 Post-merge soak (kill-switch ON)

`DISABLE_L1_IMPLEMENT=true` blocks event triggers. Dispatch path is open thanks to the bypass.

1. **Smoke 1 — dispatch council**: dispatch on a known-good test issue (CAB-XXXX) with `stage=council`. Verify side-effects: `council-validated` label applied **only if** verdict ∈ {go,fix,redo}; Linear `council:ticket-*` label applied; Slack notification received; HEGEMON state push delivered; job summary written.
2. **Smoke 2 — dispatch plan**: same issue, `stage=plan`. Verify Stage 1 verification step lets it through (label was applied in Smoke 1). Plan validation runs; `plan-validated` label applied gated on plan verdict; Linear `council:plan-*` synced.
3. **Smoke 3 — dispatch implement**: same issue, `stage=implement`. Verify `wait-for-label` confirms `plan-validated`; implement runs; PR is created; Slack/Linear/HEGEMON deliver.
4. **Negative smoke** — dispatch `stage=plan` on an issue WITHOUT `council-validated`. Stage 1 verify step must skip cleanly (validated=false); no label/Linear write.

If any smoke fails: `git revert` (see §I) before flipping the kill-switch.

### H.3 Live activation (kill-switch OFF)

5. Set `vars.DISABLE_L1_IMPLEMENT=false`.
6. **Trigger 1** — apply `claude-implement` label to a real CAB issue. Council fires from `issues` event. Same side-effect checklist as Smoke 1.
7. **Trigger 2** — comment `/go` on the same issue from a MEMBER+. Plan-validate fires. Verify author_association rejection by simulating from a fork (or a non-MEMBER account if available — otherwise document the test as deferred).
8. **Trigger 3** — comment `/go-plan`. Implement fires.

Soak window: **24h** from Trigger 3.

### H.4 Done criteria

- [ ] Smokes 1–3 + negative smoke green.
- [ ] Triggers 1–3 green on a real CAB-XXXX issue.
- [ ] Author_association guard verified (negative test).
- [ ] No unexpected runs in 24h.
- [ ] Pause marker deleted.
- [ ] `vars.DISABLE_L1_V2_SMOKE` repo variable deleted.
- [ ] Linear CAB-2166 → Done with the 4 phase SHAs (2a, 2b, 2c, 2d).

---

## I. Rollback procedure

```bash
# 1. Identify the merge commit
MERGE_SHA=$(git log --merges --first-parent main -1 --format='%H')

# 2. Revert (creates a new forward commit; restores legacy file + reverts v2 changes atomically)
git revert -m 1 "$MERGE_SHA"

# 3. Push (no force; revert is forward-moving)
git push origin main

# 4. Set kill-switch back ON to be safe
gh variable set DISABLE_L1_IMPLEMENT --body 'true'

# 5. Update pause marker to RESOLVED:reverted with timestamp + revert SHA, or git rm

# 6. Verify legacy is back
ls -la .github/workflows/claude-issue-to-pr.yml
git log --oneline -3 -- .github/workflows/claude-issue-to-pr.yml
```

The revert is a forward commit; no force-push, no history rewrite. Safe under main branch protection.

---

## J. Sign-off

All 9 decisions in §A are confirmed via user review. Phase 1 is complete pending final ack on this REV 2.

**On user "GO"**: I execute commits 1–4, push, open PR, run §H.1 gates, then proceed to §H.2 smokes once merged.
