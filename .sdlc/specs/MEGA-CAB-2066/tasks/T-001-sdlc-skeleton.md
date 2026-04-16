---
task_id: T-001
mega_id: CAB-2066
title: Create .sdlc/ skeleton with context, templates, kill-criteria
owner: "@PotoMitan"
state: done
blocked_by: []
pr: null                  # bundled in CAB-2066 MEGA PR
created_at: 2026-04-16
completed_at: 2026-04-16
---
# Create .sdlc/ skeleton

## Goal

Deliver the Level 1 convention: folder layout, templates, kill-criteria.
Covers AC #1 and #2 of `requirement.md`.

## Approach

- Create `.sdlc/{README.md,KILL-CRITERIA.md,context/*,templates/*,specs/}`.
- Reference existing `CLAUDE.md` and ADR numbering; do not duplicate.
- Pin cc-sdd v3.0.2 as the template inspiration; no runtime install.

## Done when

- [x] `.sdlc/` tree in place.
- [x] Kill-criteria review date set (2026-04-30).
- [x] No duplication with `CLAUDE.md` (pointer-style docs only).
