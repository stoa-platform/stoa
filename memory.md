# STOA Memory

> Last updated: 2026-02-05 (Session 7 — Context Management Architecture Refactor)

## Active Sprint
- **Goal**: Revenue-ready demo by Feb 24, 2026
- **Branch**: main
- **Focus**: AI context management architecture (ADR-030)

## Session State

| Status | Ticket | Description | Evidence |
|--------|--------|-------------|----------|
| DONE | CAB-1044 | API Search HTTP 500 fix | commit 2c5672d8 |
| DONE | CAB-1040 | Gateway Routes HTTP 404 fix | commit 0c33e21d |
| DONE | CAB-1042 | Vault sealed fix | commit 8bbf71b9 |
| DONE | CAB-1041 | E2E BDD auth fix | commit 248f9d29 |
| DONE | — | CLI stoa v0.1.0 (5 commands, 55 tests, 84% coverage) | Session 2 |
| DONE | — | E2E tests 24/24 pass | Session 3 |
| DONE | CAB-1061 | Demo data seed script | Session 4 |
| DONE | CAB-1060 | Docs 20 pages (Docusaurus) | Session 5 |
| DONE | CAB-1062 | Docker image + CI deploy | PR #74, Session 6 |
| DONE | ADR-030 | AI context management architecture | Session 7 |
| DONE | — | Context refactor: CLAUDE.md 11KB→3KB + 8 rules + 8 component docs + 8 skills + hooks | Session 7 |
| NEXT | CAB-1066 | Landing gostoa.dev + Stripe | — |
| NEXT | — | Browser-based demo walkthrough | — |
| NEXT | — | Record video backup for demo | — |

## Decisions This Sprint
- 2026-02-04: Use column refs in SQLAlchemy upsert (not string keys)
- 2026-02-04: E2E auth requires dual OIDC client tokens (portal + console)
- 2026-02-05: ADRs live in stoa-docs, not stoa (ADR-030)
- 2026-02-05: Retire .stoa-ai/ — migrate to native Claude Code features (skills, rules, hooks)
- 2026-02-05: CLAUDE.md hierarchy: root (compact) + .claude/rules/ (modular) + component CLAUDE.md (lazy)

## Known Issues
- Loki behind oauth2-proxy — requires Grafana for direct queries
- Portal has 2 APIs in catalog; Console has 0 per tenant until seed
- ADR-027 numbering conflict: stoa/ has "Gateway Adapter Pattern", stoa-docs has "X.509 Header Auth"

## E2E Validation (Session 3 — 2026-02-04)
- **24/24 tests passed** (22.6s)
- Auth: 7/7 personas, Portal: 5/5, Console: 5/5, Gateway: 6/6, TTFTC: 1/1 (12.7s)
- Zero HTTP 500 errors across all endpoints
- All 4 bug fixes verified live

## Notes
- Demo: mardi 24 fevrier 2026
- Presentation "ESB is Dead" same day
- 2 design partners to close
- Stack = Python (not Node)
- Console tenants: "oasis", "oasis-gunters"
- Portal OIDC client: stoa-portal; Console OIDC client: control-plane-ui
- Demo seed: `make seed-demo` or `ANORAK_PASSWORD=xxx python3 scripts/seed-demo-data.py`
- Docs site: stoa-docs/ (Docusaurus 3.9), 20 pages
