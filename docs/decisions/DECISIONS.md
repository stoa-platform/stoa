# Decision Log

Chronological log of notable technical decisions. For major architectural decisions, see [ADRs in stoa-docs](https://docs.gostoa.dev/architecture/adr/).

## 2026-02

| Date | Decision | Context |
|------|----------|---------|
| 2026-02-05 | ADRs live in stoa-docs, not stoa | Single source of truth for architecture decisions (ADR-030) |
| 2026-02-05 | Retire .stoa-ai/ in favor of native Claude Code features | Skills, rules, hooks replace templates and custom scripts |
| 2026-02-05 | CLAUDE.md hierarchy: root (compact) + rules (modular) + component (lazy) | Reduce context window usage, improve relevance (ADR-030) |
| 2026-02-04 | Use SQLAlchemy column references in upsert, not string keys | Avoid silent failures on column name mismatches |
| 2026-02-04 | E2E auth: capture both OIDC client tokens per persona | react-oidc-context uses sessionStorage, Playwright misses it |
| 2026-02-04 | Demo data seed via `make seed-demo` | Reproducible demo environment with 3 APIs, 2 apps, metrics |

## 2026-01

| Date | Decision | Context |
|------|----------|---------|
| 2026-01-30 | Gateway Adapter Pattern (ADR-035) | Declarative reconciliation for multi-vendor gateways |
| 2026-01-24 | Stack = Python everywhere backend | No Node.js on server side, consistency |
| 2026-01-24 | AI Factory model: architect supervises Claude Code | Autonomous execution with human checkpoints |
