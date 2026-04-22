---
name: rewrite
description: Force a full-file rewrite (Write) instead of patch (Edit) when Edit keeps failing or diff is large. Context rot mitigation — use when Edit has failed ≥2× on same file, or when estimated diff >30% of file size.
argument-hint: "<file_path> [intent — what should change]"
---

# Rewrite — $ARGUMENTS

> Invoked when Edit (patch) is the wrong tool. Research shows search/replace fails 20-30% on evolved code, and accumulated failed patches poison the context (Liu et al. "Lost in the Middle"; Databricks Mosaic). See `feedback_rewrite_after_fail.md`.

## When to use this skill

Triggered automatically via the hook `post-edit-failure-tracker.sh` at 2 consecutive Edit failures. Also invoke manually when:
- Diff estimated >30% of the file size
- Refactoring where structure changes, not just content
- File is small-to-medium (≤800 lines) and a clean rewrite is cheaper than hunting for correct search/replace anchors
- User says "just rewrite it"

**Do NOT use** for:
- Single-line changes (use Edit)
- Files >1500 lines (split first, or delegate to subagent)
- Files you haven't read yet in this session (read first, understand first)

## Workflow

### Step 1 — Parse arguments
Split `$ARGUMENTS` into:
- `FILE_PATH` (first token, absolute path)
- `INTENT` (remainder — what the rewrite should accomplish)

If `INTENT` is empty, ask the user: "What should the rewrite accomplish? (e.g. 'fix the auth middleware bug', 'add tenant filtering')". Do NOT guess the intent from context alone.

### Step 2 — Read the current file
Always `Read` the full file before rewriting. If >1500 lines, stop and suggest splitting or subagent delegation instead.

### Step 3 — Check pollution signal
```bash
jq --arg path "$FILE_PATH" '[.[] | select(.path == $path)] | .[0]' .claude/state/edit-attempts.json
```
If `consecutive_fails ≥ 2`, the rewrite is warranted. If `total ≥ 5` but `consecutive_fails < 2`, consider whether a subagent with fresh context would be better than an inline rewrite (Main context already has noise).

### Step 4 — Rewrite strategy

Preserve by default:
- Public API surface (exported symbols, function signatures if referenced elsewhere)
- Import structure and file-level conventions
- Comments that explain non-obvious WHY (delete comments that explain WHAT)
- Type annotations, docstrings where they exist

Change per INTENT:
- Fix the bug described
- Refactor the internal logic
- Simplify control flow

### Step 5 — Write the file
Use the `Write` tool with the full new content. Never emit partial content or placeholders like `// ... rest unchanged`.

### Step 6 — Verify
Run the relevant check for the file type:
- `.py`: `ruff check <file> && ruff format --check <file>` (or let the post-edit-format hook run)
- `.rs`: `rustfmt --check <file>` + `cargo check -p <crate>` if feasible
- `.ts|.tsx|.js|.jsx`: `npx prettier --check <file>`
- `.go`: `go vet ./... && gofmt -l <file>`

If the file has tests nearby (`*_test.*`, `*.test.*`, `*.spec.*`), run them.

### Step 7 — Reset the tracker
```bash
jq --arg path "$FILE_PATH" 'del(.[] | select(.path == $path))' .claude/state/edit-attempts.json > /tmp/et.json && mv /tmp/et.json .claude/state/edit-attempts.json
```
Removes the failure counter for this file so the next session starts clean.

## Anti-patterns

- Do NOT rewrite a file whose purpose you don't understand. Read + grep callers first.
- Do NOT rewrite while the main context is >70% full — delegate to a subagent instead (the pollution bias applies to rewrites too).
- Do NOT bundle unrelated changes into the rewrite. Stick to the stated INTENT.
- Do NOT remove comments that carry historical/compliance context (e.g. "kept for backwards compat with X", "regression for CAB-XXXX") — these have load-bearing information.
- Do NOT rewrite test files without running them after — silent test deletion is a known failure mode.
