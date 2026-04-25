# FIX-PLAN — CI-1 Phase 2d (Switch Final)

**Branche** : `refactor/ci-1-phase-2d-switch`
**Status** : DRAFT — awaiting validation before execution
**Refs** : CAB-2166, CI-1-REWRITE-PLAN.md §F

---

## TL;DR

Phase 2d retires the legacy `claude-issue-to-pr.yml` and rewires `claude-issue-to-pr-v2.yml` to events. Net delta: **delete 797 LOC, modify 544 LOC down to ~440** (drop `prepare` job ~38 LOC + adjust references), add ~30 LOC of triggers / ticket extraction.

The hand-off is non-trivial because (a) the kill-switch variable name changes (`DISABLE_L1_V2_SMOKE` → `DISABLE_L1_IMPLEMENT`), (b) 49 `needs.prepare.outputs.*` references must be retargeted, (c) v2's chained `needs:` model differs from the legacy event-driven model.

**Three arbitrage points need user confirmation before Phase 2 (execution):**

| # | Decision | Plan recommendation |
|---|---|---|
| A1 | Trigger `types:` for `issues:` | `[labeled, assigned]` — match legacy exactly. The user-prompt sketch said `[opened, edited, labeled]` which would (i) lose the `assigned` path, (ii) fire Council on every issue open/edit (noise). |
| A2 | v2 filename post-switch | **Rename** `claude-issue-to-pr-v2.yml` → `claude-issue-to-pr.yml` (canonical name). Path-filter glob `claude-issue-to-pr*.yml` in `ai-factory-scripts-tests.yml` continues to match. Alternative: keep `-v2` suffix forever. |
| A3 | Pre-merge state of `vars.DISABLE_L1_IMPLEMENT` | **Leave it `true`** until post-merge soak. Use `workflow_dispatch` (kept) to smoke-test the new wiring on a test issue. Flip to `false` only after 1 dispatch + 1 event-driven run land cleanly. |

---

## A. Legacy retirement (Option A confirmed)

**Decision: Option A (suppression via `git rm`).** Rationale:

- `git revert <merge-sha>` cleanly restores the legacy intact if rollback is needed (file content is in git history, atomic restoration).
- An archived rename (Option B) clutters the workflows directory and risks accidental re-activation by anyone editing it without context.
- Recovery for read-only inspection: `git show <pre-2d-sha>:.github/workflows/claude-issue-to-pr.yml`.

**Concrete commands**:

```bash
git rm .github/workflows/claude-issue-to-pr.yml
git mv .github/workflows/claude-issue-to-pr-v2.yml .github/workflows/claude-issue-to-pr.yml   # if A2 = rename
```

---

## B. Triggers events delta

### B.1 Legacy `on:`

```yaml
on:
  issues:
    types: [labeled, assigned]
  issue_comment:
    types: [created]
```

### B.2 v2 today

```yaml
on:
  workflow_dispatch:
    inputs:
      issue_number: { required: true }
      run_implement: { default: false }
```

### B.3 Phase 2d target (proposed)

```yaml
on:
  issues:
    types: [labeled, assigned]      # ← matches legacy. NOT [opened, edited, labeled].
  issue_comment:
    types: [created]
  workflow_dispatch:                  # ← kept for smoke tests + manual replay
    inputs:
      issue_number: { required: true }
      run_implement: { default: false }
```

**Why not `[opened, edited, labeled]`** (user-prompt sketch): legacy specifically gates Council on `label.name == 'claude-implement'` OR `action == 'assigned'`. Adding `opened` would fire Council on every new issue (mass-noise risk), and `edited` would re-fire Council on every issue body edit. The `assigned` path is the human "claim this for AI" entry-point and was missing from the user's sketch.

---

## C. `prepare` job removal — full reference map

`prepare` exists only because `workflow_dispatch` doesn't carry `github.event.issue.*`. With events restored, every reference can be retargeted.

| `needs.prepare.outputs.X` | Count | Replacement |
|---|---:|---|
| `.number` | 21 | `github.event.issue.number` |
| `.title` | 8 | `github.event.issue.title` |
| `.body` | 7 | `github.event.issue.body` |
| `.url` | 2 | `github.event.issue.html_url` (note: `.url` is API URL, legacy used `html_url`) |
| `.ticket-id` | 11 | New per-job `Extract ticket ID` step (~5 LOC), see §C.1 |
| **Total** | **49** | |

### C.1 Ticket extraction step (new, per job)

Each of the 3 surviving jobs (council-validate, plan-validate, implement) gains an early step:

```yaml
- name: Extract ticket ID
  id: extract
  env:
    ISSUE_TITLE: ${{ github.event.issue.title || inputs.issue_title }}
    ISSUE_BODY: ${{ github.event.issue.body || inputs.issue_body }}
  run: |
    set -uo pipefail
    source "${GITHUB_WORKSPACE}/scripts/ci/gh_helpers.sh"
    TICKET=$(extract_ticket_id "$ISSUE_TITLE $ISSUE_BODY")
    echo "ticket-id=${TICKET}" >> "$GITHUB_OUTPUT"
```

References then become `${{ steps.extract.outputs.ticket-id }}`. Total LOC added across 3 jobs: ~15. Net win vs `prepare`: -23 LOC (38 → 15).

For the `workflow_dispatch` path, since title/body aren't in the event payload, we need to either:
- **Option C.1.a**: Keep a tiny "Fetch issue (dispatch only)" step gated on `github.event_name == 'workflow_dispatch'` that uses `gh issue view`. ~10 LOC per job that needs it. **Recommended.**
- **Option C.1.b**: Drop dispatch entirely once events are live. Simpler, but loses the smoke replay capability.

**Recommendation**: C.1.a. Keeping dispatch gives us a debug knob and was used heavily in Phase 2b smokes.

### C.2 Job dependency model change (chained → event-driven)

v2 today chains: `prepare → council-validate → plan-validate → implement` via `needs:`.

Legacy uses **event-driven** (each event fires the matching job; jobs don't depend on each other within a single run). Phase 2d target matches legacy:

| Job | Today (v2) | Phase 2d target |
|---|---|---|
| `council-validate` | `needs: prepare` | (no `needs:`) |
| `plan-validate` | `needs: [prepare, council-validate]` + `if: needs.council-validate.result == 'success'` | (no `needs:`) — fires on its own `/go` event |
| `implement` | `needs: [prepare, plan-validate]` + `if: needs.plan-validate.result == 'success' && inputs.run_implement == true` | (no `needs:`) — fires on its own `/go-plan` event |

This is structurally a bigger change than "drop prepare". Each `if:` filter must encode the full event signature.

---

## D. `if:` guards delta per job

### D.1 `council-validate`

**Legacy**:
```yaml
if: |
  vars.DISABLE_L1_IMPLEMENT != 'true' &&
  (
    (github.event_name == 'issues' && github.event.label.name == 'claude-implement') ||
    (github.event_name == 'issues' && github.event.action == 'assigned')
  )
```

**Phase 2d target**:
```yaml
if: |
  vars.DISABLE_L1_IMPLEMENT != 'true' &&
  (
    (github.event_name == 'issues' && github.event.label.name == 'claude-implement') ||
    (github.event_name == 'issues' && github.event.action == 'assigned') ||
    (github.event_name == 'workflow_dispatch')
  )
```

### D.2 `plan-validate`

**Legacy**:
```yaml
if: |
  vars.DISABLE_L1_IMPLEMENT != 'true' &&
  github.event_name == 'issue_comment' &&
  contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.comment.author_association) &&
  (
    github.event.comment.body == '/go' ||
    github.event.comment.body == '/approve' ||
    startsWith(github.event.comment.body, '/go ') ||
    startsWith(github.event.comment.body, '/approve ')
  )
```

**Phase 2d target**: same, plus `(github.event_name == 'workflow_dispatch')` OR-branch.

### D.3 `implement`

**Legacy**:
```yaml
if: |
  vars.DISABLE_L1_IMPLEMENT != 'true' &&
  github.event_name == 'issue_comment' &&
  contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.comment.author_association) &&
  (
    github.event.comment.body == '/go-plan' ||
    startsWith(github.event.comment.body, '/go-plan ')
  )
```

**Phase 2d target**: same, plus `(github.event_name == 'workflow_dispatch' && inputs.run_implement == true)`.

### D.4 Author association guard — preserved

`contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), github.event.comment.author_association)` is the fork-safety defense. Present in legacy plan-validate + implement. **Currently absent from v2**. **Must be added back.** Without it, anyone with a fork can comment `/go-plan` and trigger implementation on the upstream repo — credential exfil + supply-chain risk.

---

## E. Other deltas

### E.1 Kill-switch variable

| | Var | State today |
|---|---|---|
| Legacy expects | `vars.DISABLE_L1_IMPLEMENT` | `true` (per v2 file comment, prod) |
| v2 today | `vars.DISABLE_L1_V2_SMOKE` | unset / false |
| Phase 2d | `vars.DISABLE_L1_IMPLEMENT` (renamed back) | **must stay `true` through merge**, flip post-soak |

`DISABLE_L1_V2_SMOKE` becomes orphan post-2d. Repo var cleanup: delete it after switch is validated.

### E.2 Concurrency group

| | Group |
|---|---|
| Legacy | `claude-issue-${{ github.event.issue.number }}` |
| v2 today | `ci-v2-issue-${{ inputs.issue_number }}` |
| Phase 2d target | `claude-issue-${{ github.event.issue.number || inputs.issue_number }}` |

Match legacy prefix so the group serializes per-issue across event-driven and dispatch paths.

### E.3 Stage 1 verification missing in v2

Legacy `plan-validate` job has a 30-LOC "Verify Stage 1 Council" step that early-exits if neither `council-validated` label nor a `Council Score` comment exists. v2 today relies only on `label-guard` for `plan-validated` (idempotency check), not on `council-validated` presence.

**Risk without it**: A user can comment `/go` on a fresh issue (no Stage 1 ever ran) and Stage 2 fires immediately, validating a plan against a ticket that was never deemed pertinent. Legacy prevents this; v2 today does not.

**Recommendation**: Add a "Verify Stage 1 Council" step to v2's `plan-validate` job, mirroring the legacy logic:
- Read labels via `gh issue view`. If `council-validated` present → proceed.
- Fallback: scan comments for `Council Score`. If found → proceed.
- Else → `exit 0` with notice "Not an L1 council-validated issue".

~20 LOC. Reuses `gh_helpers.sh:has_label()` if it exists, else inline.

### E.4 Permissions — unchanged

Both files declare:
```yaml
permissions:
  contents: write
  pull-requests: write
  issues: write
  id-token: write
```

No change. Phase 2d preserves this.

### E.5 `claude_args` allowedTools

Legacy `plan-validate` calls `anthropics/claude-code-action@v1` (unpinned). v2's plan-validate uses the `council-run` composite, which pins SHA. Switch is a wash — composite is the cleaner path.

Legacy `implement` uses `claude_args: --allowedTools Bash,Read,Write,Edit,Glob,Grep,WebFetch`. v2 implement uses the same string. **OK, identical.**

---

## F. Pause marker

`docs/ops/ai-factory-pause.md` content draft (committed in commit 1):

```markdown
# AI-Factory Migration Pause — CI-1 Phase 2d Switch

**Status**: ACTIVE — DO NOT submit new claude-implement issues
**Started**: <merge timestamp, ISO 8601>
**Expected end**: <T+2-24h depending on soak signal>

## Why
CI-1 rewrite Phase 2d switch is in progress. The legacy `claude-issue-to-pr.yml`
has been replaced by the rewritten workflow (formerly `-v2`). During the
soak window, do not:
- Apply `claude-implement` label to new issues (Council won't run reliably until
  `vars.DISABLE_L1_IMPLEMENT` is flipped to `false`).
- Comment `/go` or `/go-plan` on existing in-flight issues — wait for soak.

## What to expect
- Slack notifications may be delayed.
- Linear sync may be skipped on transient errors.
- Issues already in the legacy pipeline at switch time will not auto-resume —
  manual `workflow_dispatch` may be needed.

## When unblocked
This file is deleted (or marked RESOLVED) once §H validation passes.
```

Removed via `git rm` in a final commit after validation.

---

## G. Phase 2 — execution plan (commit-by-commit)

| # | Commit | Files | Goal |
|---|---|---|---|
| 1 | `docs(ops): announce AI-Factory pause for CI-1 phase 2d` | `docs/ops/ai-factory-pause.md` (new) | Pause marker visible. |
| 2 | `ci(ai-factory): rewire workflow to events, drop prepare job` | `claude-issue-to-pr-v2.yml` | Triggers, `if:` guards, `prepare` removal, ticket extraction step, Stage 1 verification, author_association guard. |
| 3 | `ci(ai-factory): retire legacy claude-issue-to-pr workflow` | `git rm claude-issue-to-pr.yml` + `git mv claude-issue-to-pr-v2.yml claude-issue-to-pr.yml` (if A2=rename) | Single-commit cutover. |
| 4 | `docs: update .github/README.md post phase 2d` | `.github/README.md` | Reflect single workflow, remove v2 references. |

Commits 1-2 keep the workflow deactivable (kill-switch still active). Commit 3 is the cutover. Commit 4 is cosmetic.

PR opens after commit 4. CI runs `ai-factory-scripts-tests.yml` (path-filter triggered by `claude-issue-to-pr*.yml` change) → must pass before merge.

---

## H. Validation post-switch

### H.1 Pre-merge gates

- [ ] Phase 2c CI green: `action-validator` + `yamllint` + `pytest` all pass on the PR.
- [ ] `vars.DISABLE_L1_IMPLEMENT` confirmed `true` in repo (no surprise runs at merge time).
- [ ] Pause marker landed in commit 1.
- [ ] Stage 1 verification step + author_association guard present in commit 2 (per §D.4 and §E.3).

### H.2 Post-merge soak (kill-switch ON)

1. **Smoke 1** — `workflow_dispatch` on a known-good test issue (CAB-XXXX, smaller estimate). Run `council-validate` only (`run_implement=false`). Verify:
   - Label `council-validated` applied to GitHub issue.
   - Linear `council:ticket-{go|fix|redo}` label applied to CAB-XXXX.
   - Slack notification received.
   - HEGEMON state push delivered.
   - Job summary written.
2. **Smoke 2** — Same test issue, `workflow_dispatch` with `run_implement=true`. Verify the implement chain end-to-end (Council → wait-for-label → plan → implement → PR). Expect a real PR to land on the test issue.

If either smoke fails: `git revert` (see §I) before flipping the kill-switch.

### H.3 Live activation (kill-switch OFF)

3. **Set** `vars.DISABLE_L1_IMPLEMENT=false` in repo settings.
4. **Trigger 1** — apply `claude-implement` label to a known issue. Council fires from `issues` event, not dispatch. Same checklist as Smoke 1.
5. **Trigger 2** — comment `/go` on the same issue. Plan-validate fires from `issue_comment` event. Verify `plan-validated` label + Linear sync.
6. **Trigger 3** — comment `/go-plan`. Implement fires. Verify PR creation + Slack/Linear/HEGEMON.

Soak window: **24h** from Trigger 3, monitoring Slack + Linear for unexpected runs or missed notifications.

### H.4 Done criteria

- [ ] Smokes 1+2 green.
- [ ] Triggers 1+2+3 green on a real CAB-XXXX issue.
- [ ] No unexpected runs (forks, edits, etc.) in 24h.
- [ ] Pause marker deleted (commit + push).
- [ ] `vars.DISABLE_L1_V2_SMOKE` repo variable deleted.
- [ ] Linear CAB-2166 → Done with SHAs of all 4 phases.

---

## I. Rollback procedure

**Trigger conditions** (any one):
- Smokes 1 or 2 fail with non-recoverable error.
- Live triggers fire on unintended events (forks, mass-edit, etc.).
- Slack/Linear/HEGEMON integration regression vs legacy.

**Steps** (all from a clean main checkout):

```bash
# 1. Identify the merge commit
MERGE_SHA=$(git log --merges --oneline main -1 | grep -oE '^[a-f0-9]+')

# 2. Revert (creates a new commit that restores legacy + reverts v2 changes atomically)
git revert -m 1 "$MERGE_SHA"

# 3. Push (no force; revert is a forward-moving commit)
git push origin main

# 4. Set kill-switch back ON to be safe
gh variable set DISABLE_L1_IMPLEMENT --body 'true'

# 5. Update pause marker
# Mark as "RESOLVED:reverted" with timestamp + revert SHA
# Or git rm if pause is no longer relevant

# 6. Verify legacy is back
ls -la .github/workflows/claude-issue-to-pr.yml
git log --oneline -3 .github/workflows/claude-issue-to-pr.yml
```

The revert is the only destructive op and creates a new commit (no force-push, no history rewrite).

---

## J. Open questions for user (Phase 1 sign-off)

1. **A1 (triggers)** — Confirm `[labeled, assigned]` instead of the prompt's `[opened, edited, labeled]`?
2. **A2 (filename)** — Rename `claude-issue-to-pr-v2.yml` → `claude-issue-to-pr.yml`, or keep v2 suffix?
3. **A3 (kill-switch)** — Keep `DISABLE_L1_IMPLEMENT=true` through merge, flip post-soak?
4. **§E.3 (Stage 1 verification)** — Add the missing guard back to plan-validate (yes recommended), or accept the gap?
5. **§D.4 (author_association)** — Confirmed re-add to plan-validate + implement (defense-in-depth, was lost in v2 rewrite)?
6. **§C.1.a vs C.1.b** — Keep `workflow_dispatch` for smoke replay, or drop it post-switch?

After sign-off → I execute Phase 2 (4 commits, push, PR, then run §H validation).
