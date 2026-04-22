# Step 1-2 proof contract — Declaration + Catalogue

**WS 4 of CAB-2148**. Scenario: `Customer API / Referentiel Client` only.

## Step 1 — Declaration

Surface: UAC source + catalog repo (GitHub `stoa-platform/stoa-catalog`). Ops actions: `stoactl` + repo commit.

**Expected artefacts**
- UAC contract file committed to catalog repo, with stable source reference (path + commit SHA).
- `stoactl` output confirming registration.
- Same contract visible via Console catalog view, fed from the same source.

**Acceptable claims**
- "Contract shown is the same file committed in Git — no manual edit between source and display."
- "Declaration is repeatable: a fresh reset produces the same catalog state."
- "Source of truth is a Git repo, not a UI form."

**Forbidden claims**
- "Declaration validates against a regulatory framework." — not enforced.
- "Declaration triggers automated policy generation." — only registration ships.
- "Catalog is populated from the Control Plane database." — runtime reads from GitHub (gotcha `gateway_catalog_github_source`).

**Degraded mode**: prepared snapshot as backup only. Never the primary path.

## Step 2 — Catalogue

Surface: catalog runtime + Console UI. Ops actions: observer only.

**Expected artefacts**
- Customer API entry in Console catalog view, wording explainable from the UAC source.
- Version / timestamp marker proving the entry is the one just declared.
- Sync delay within the per-run documented demo budget.

**Acceptable claims**
- "Catalog reflects what was committed in Git — `Define once, expose everywhere` at declaration level."
- "Operators and consumers see the same artefact, not a UI-only duplicate."
- "A missing catalog entry traces back to the Git history of the catalog repo."

**Forbidden claims**
- "Catalog enforces contract validation at consumer time." — enforcement lives in the gateway.
- "Catalog shows compliance status per contract." — no compliance engine wired here.
- "Catalog is synced in real time." — delay is non-zero and observable.

**Degraded mode**: pre-captured evidence if sync exceeds budget. Named openly as a gap, never glossed over.

## Oracle of success + cross-links

Artefact on screen maps 1:1 to a file + commit SHA in the catalog repo. No manual edit between Git commit and Console display. Fresh reset reproduces the same catalog state, no carry-over. See mode split: `../mode-a-vs-mode-b.md`. Steps 3-4: `./step-3-4-subscription-call.md`. Step 5: `../step-5-governance-contract.md`.
