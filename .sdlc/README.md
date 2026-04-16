# .sdlc/ — STOA Spec-Driven Development (Level 1)

> **Scope**: Level 1 only. Structure + templates + kill-criteria.
> No tooling enforcement (no spec→code generation, no spec-anchored checks).
> See `docs/adr/adr-063-sdd-l1-impact-mcp.md` in `stoa-docs` for the full decision.

## What this folder is

A lightweight convention for MEGA ticket formalization. Each MEGA gets a directory
under `specs/` with a requirement file (the "why" and acceptance criteria) and one
or more task files (the "how"). The format borrows from
[cc-sdd](https://github.com/gotalab/cc-sdd) `v3.0.2` — **no tool install required**.

## Layout

```
.sdlc/
├── README.md                 # this file
├── KILL-CRITERIA.md          # abandonment conditions
├── context/
│   ├── architecture.md       # link map to ADRs + component DAG pointer
│   └── conventions.md        # coding + review + commit conventions
├── templates/
│   ├── requirement-template.md
│   └── task-template.md
└── specs/
    └── MEGA-<ID>/
        ├── requirement.md
        └── tasks/
            └── T-<NNN>-<slug>.md
```

## When to create a spec

- Ticket is tagged `MEGA` (21+ points, 2-4 phases) **and**
- Impact Score ≥ HIGH (16+) or Council S2 passed

Smaller tickets do not need a spec directory. The Linear ticket is enough.

## Workflow mapping

The existing STOA MEGA lifecycle (Audit → Council → Plan → Execute → Verify) maps to
SDD phases with **no new gates**:

| STOA phase         | SDD artifact                       |
|--------------------|------------------------------------|
| Audit + Council    | `requirement.md` (problem + DoD)   |
| Plan               | `tasks/T-*.md` (one per sub-PR)    |
| Execute            | task `state: in_progress → done`   |
| Verify (`/verify-mega`) | all tasks `done`, binary DoD in requirement checked |

## Opt-in, not mandatory

A MEGA without a `.sdlc/specs/MEGA-<ID>/` entry is valid. Adoption is measured
over 2 weeks (see `KILL-CRITERIA.md`). If adoption fails, this folder is removed
and the convention abandoned.
