---
name: extract
description: Extract a reusable pattern from the current session into HEGEMON Pattern Library. Atomic operation (write + git add + commit + Notion sync).
argument-hint: "<pattern name or description>"
---

# HEGEMON Pattern Extraction — $ARGUMENTS

> **IP Guard**: Patterns describe **methodology and approach**, never verbatim proprietary code, client names, pricing, or sensitive business data. Anonymize all examples. See `hegemon/CLAUDE.md` anonymization rules.

## Step 1: Identify the Pattern

From the current session's work, identify what is reusable:

1. **What recurring problem was solved?** (not a one-off fix)
2. **Is this transferable** to other projects (PRAXIS, ATHLOS, OIKOS)?
3. **Does a similar pattern already exist?** Check `hegemon/patterns/` directory

If the answer to #1 or #2 is "no", this is NOT a pattern — it's a project-specific solution. Skip extraction.

If a similar pattern exists, **update it** (add to Reuse Log) instead of creating a new one.

## Step 2: Categorize

Determine the pattern category:

| Category | Examples | Directory |
|----------|----------|-----------|
| `architecture` | System design, infrastructure patterns, integration patterns | `patterns/architecture/` |
| `workflow` | Development process, CI/CD, session management, estimation | `patterns/workflow/` |
| `validation` | Review processes, quality gates, Council patterns | `patterns/validation/` |
| `prompt` | Effective prompt structures, agent delegation patterns | `patterns/prompt/` |
| `communication` | Stakeholder management, reporting, documentation patterns | `patterns/communication/` |

## Step 3: Assign Pattern ID

Read existing patterns to find the next available ID:

```bash
ls hegemon/patterns/*/HEG-PAT-*.md | sort -t- -k3 -n | tail -1
```

Next ID = highest existing + 1. Format: `HEG-PAT-XXX` (zero-padded to 3 digits).

## Step 4: Write the Pattern File

Create the pattern file using the HEGEMON template. The file MUST include ALL sections:

```markdown
# HEG-PAT-XXX: [Pattern Name]

## Metadata
- **Origin**: [Project] / [Ticket or context]
- **Category**: [architecture | workflow | prompt | validation | communication]
- **Supervision Tier**: [AUTOPILOT | CO-PILOT | COMMAND]
- **Created**: [YYYY-MM-DD]
- **Last Updated**: [YYYY-MM-DD]

## Problem
[What recurring problem does this pattern solve? 2-3 sentences.]

## Solution
[The reusable approach — methodology, decision trees, workflow structures.
NOT verbatim code. Describe the pattern abstractly enough to apply across projects.]

## Constraints
[When NOT to use this pattern. Preconditions. Limitations.]

## Reuse Log
| Date | Project | Outcome | Adaptations |
|------|---------|---------|-------------|
| [today] | [origin project] | Extracted | Initial extraction |
```

Write the file to: `hegemon/patterns/<category>/HEG-PAT-XXX-<kebab-case-name>.md`

## Step 5: Atomic Git Commit

This MUST be a single atomic operation — never leave an uncommitted pattern file.

```bash
cd <hegemon-repo-path>
git add patterns/<category>/HEG-PAT-XXX-<name>.md
git commit -m "extract(patterns): HEG-PAT-XXX <pattern-name> from <project>"
git push origin main
```

## Step 6: Notion Sync

Create an entry in the HEGEMON Pattern Library Notion database:

```
notion-create-pages({
  title: "HEG-PAT-XXX: <Pattern Name>",
  properties: {
    "Pattern ID": "HEG-PAT-XXX",
    "Category": "<category>",
    "Origin Project": "<project>",
    "Supervision Tier": "<tier>",
    "Reuse Count": 1,
    "Status": "validated",
    "Git Path": "patterns/<category>/HEG-PAT-XXX-<name>.md"
  }
})
```

If Notion MCP is unavailable, log a TODO in `hegemon/memory.md` for manual sync.

## Step 7: Update Project Extract Log

Append to `hegemon/projects/<project>/extracts.md`:

```markdown
### HEG-PAT-XXX: <Pattern Name> (YYYY-MM-DD)
- **Ticket**: <ticket-id or context>
- **Category**: <category>
- **Transfer potential**: HIGH | MEDIUM | LOW
- **Learning**: <1-2 sentence insight from this extraction>
```

## Step 8: Report

```
Pattern extracted: HEG-PAT-XXX — <Pattern Name>
Category: <category>
Supervision Tier: <tier>
Git: hegemon/patterns/<category>/HEG-PAT-XXX-<name>.md
Notion: synced | TODO (manual sync needed)
Project log: updated
```

## Rules

- **One pattern per extraction** — don't bundle multiple patterns
- **Methodology, not code** — describe the approach, not implementation details
- **Anonymize everything** — no client names, no pricing, no internal metrics values
- **Update > Create** — if a similar pattern exists, update its Reuse Log instead
- **Atomic commits** — pattern file must be committed immediately, never left unstaged
- **Notion is secondary** — if sync fails, the git file is still the source of truth
