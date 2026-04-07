---
name: memory-consolidate
description: Consolidate memory files — remove stale facts, resolve contradictions, verify paths. Inspired by Claude Code's autoDream pattern.
user_invocable: true
---

# Memory Consolidation — autoDream Pattern

CAB-2005: Inspired by Claude Code's `autoDream` process revealed in the March 2026 source leak.
During idle periods, autoDream merges disparate observations, removes logical contradictions,
and converts vague insights into verified facts.

This skill performs the same operation on STOA's memory system.

## Step 1: Read All Memory Files

Read the memory index and all referenced topic files:
1. `~/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/MEMORY.md` (index)
2. All `.md` files referenced in MEMORY.md (topic files)
3. `memory.md` (project root — session state)

## Step 2: Verify File References

For each file path mentioned in any memory file (backtick-quoted paths like `path/to/file.ext`):
1. Check if the file still exists in the codebase
2. If NOT: flag as stale, note the memory file and line
3. If YES but content has changed significantly: flag as potentially outdated

Use Glob and Grep to verify existence. Do NOT read every referenced file — just check existence.

## Step 3: Detect Contradictions

Scan for contradictions across memory files:
- **Version conflicts**: e.g., "ADR numbering: next ADR-048" in one file vs "ADR-060" in another
- **Status conflicts**: item marked DONE in one file but IN PROGRESS in another
- **Port/URL conflicts**: different ports or URLs for the same service
- **Date conflicts**: timeline inconsistencies

## Step 4: Detect Stale Facts

Flag facts that are likely outdated:
- References to cycles older than 2 cycles ago still marked "CURRENT"
- TODO items with dates more than 2 weeks in the past
- "Active" items that haven't been updated in 30+ days
- Infrastructure references (IPs, service names) that may have changed

## Step 5: Apply Fixes

For each issue found:
- **Stale path**: Remove or update the reference
- **Contradiction**: Keep the more recent/accurate version, remove the other
- **Outdated fact**: Update if current state is clear, otherwise flag for human review
- **Stale TODO**: Move to completed or remove if no longer relevant

## Step 6: Compact MEMORY.md

Ensure MEMORY.md stays under 120 lines:
- Move completed ticket details to `completed-tickets.md`
- Move resolved infra details to `infra-status.md`
- Keep index entries under ~150 chars each

## Step 7: Report

Output a summary:
```
Memory Consolidation Report:
- Files scanned: N
- Stale paths removed: N
- Contradictions resolved: N
- Stale facts updated: N
- MEMORY.md lines: N/120
- Items flagged for human review: N (list)
```

## Rules

- NEVER delete a memory file entirely — consolidate into existing files
- NEVER change facts about infrastructure (IPs, credentials, service names) without verification
- Flag uncertain changes for human review rather than guessing
- This skill is safe to run via `/loop 30m memory-consolidate` for periodic maintenance
- Keep the consolidation under 2 minutes — don't read every file in the codebase
