# Migration 107 — Audit immutability + pseudonymization (DRAFT)

**Status: DRAFT. DO NOT APPLY TO PRODUCTION UNTIL SIGN-OFF.**

This migration is the concrete artefact for [CAB-2226](https://linear.app/hlfh-workspace/issue/CAB-2226) — joint sign-off of ADR-068 (audit immutability + hash chain) and ADR-069 (GDPR ↔ DORA reconciliation via pseudonymization).

## Why this file exists

The audit of 2026-05-11 (`docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md`) found that `audit_events` is declared "immutable" in the model docstring but is mutated by `erase_user_pii()` (`control-plane-api/src/services/audit_service.py:420-461`). This breaks DORA Art.11 (5-year integrity) silently while satisfying GDPR Art.17.

ADR-068 + ADR-069 (drafts in `docs/audits/2026-05-11-uac-subscription-mcp/adrs-drafts/`) reconcile the conflict by:

1. Forbidding UPDATE / DELETE on `audit_events` via a PostgreSQL trigger.
2. Routing GDPR erasure requests through a separate `pseudonymized_audit_erasures` table.
3. Exposing a `audit_events_redacted` view that applies redaction at read time.
4. Preparing a per-tenant hash chain (`audit_chain_heads` + `row_hash` column) for integrity proof.

This migration **creates the schema**. It does **not** rewrite application code (`erase_user_pii`, audit insert path, hash chain computation) — those are separate PRs, also blocked on sign-off.

## What the migration changes

| Object | Type | Purpose |
|--------|------|---------|
| `audit_events.row_hash` | column (BYTEA, nullable) | Per-tenant hash chain link |
| `audit_chain_heads` | table | Serializes per-tenant chain inserts |
| `audit_events_immutable()` | trigger function | Raises on UPDATE/DELETE of audit_events |
| `audit_events_no_update` | trigger | Wires immutability on UPDATE |
| `audit_events_no_delete` | trigger | Wires immutability on DELETE |
| `pseudonymized_audit_erasures` | table | GDPR Art.17 records, DPO-controlled |
| `_audit_is_redacted(event_id, actor_id)` | SQL helper | Redaction predicate, STABLE |
| `audit_events_redacted` | view | Default read surface with redaction |
| `pgcrypto` | extension | sha256/digest for view pseudonyms |

## What the migration deliberately does NOT do

- **Backfill `row_hash` for existing rows.** Trigger only enforces on new inserts; existing rows tolerate NULL. Backfill is a separate break-glass operation under DPO/Compliance sign-off, with documented batch hash, count, and operator.
- **Rewrite `erase_user_pii()`.** Without that rewrite, applying this migration to a live system breaks the existing GDPR erasure path (the trigger refuses the UPDATE). A code-side PR must land in lock-step.
- **Enable hash-chain computation in audit_service.py inserts.** Schema only.
- **Add SQLAlchemy models for the new tables.** Comes with the code PR.
- **Drop `row_hash` on downgrade.** Preserved for safety; explicit drop under a separate procedure if needed.

## Sign-off pre-requisites (CAB-2226)

This migration is **non-mergeable** until all of the following are recorded on CAB-2226:

- [ ] **Security** sign-off: SQL-level review of the immutability trigger and trigger exception path.
- [ ] **Compliance** sign-off: pseudonymization model satisfies DORA Art.11 retention vs GDPR Art.17 erasure.
- [ ] **DPO** sign-off (non-delegable): `pseudonymized_audit_erasures` workflow, redaction_map shape, pseudonymization_key disposition (default proposal: retrievable with dual-control per ENISA; DPO may override).
- [ ] **Legal** sign-off: legal-basis taxonomy, jurisdictional coverage, retention default for the auxiliary table.
- [ ] **CP-API WG** sign-off: alembic + ORM model addition path agreed; `erase_user_pii` rewrite scoped as a follow-up PR with lock-step deploy ordering.
- [ ] **Platform Ops** sign-off: break-glass procedure for the three trigger exceptions (retention purge, schema migration, disaster-recovery restore) documented as runbook.

## Lock-step deploy ordering

When sign-off is complete, deployment must follow this order:

1. **PR A — code-side (separate, blocked by sign-off):** rewrite `erase_user_pii()` to insert into `pseudonymized_audit_erasures` instead of UPDATE; route audit reads through the new view; add hash-chain computation in audit_service insert path; add SQLAlchemy models.
2. **PR B — this migration:** apply `107_audit_immutability_pseudonymization` to all environments (dev → staging → prod).
3. **PR C — backfill (separate):** compute `row_hash` for existing rows in `created_at` order per tenant. Break-glass procedure, audited operator.

PR A must be MERGED and DEPLOYED to a given environment before PR B is applied there. Otherwise the trigger will reject in-flight erasure UPDATEs and break tenant-facing functionality.

## How to test this migration locally (after sign-off, NOT before)

```bash
cd control-plane-api
# Bring up a disposable Postgres
docker run -d --name stoa-audit-test -e POSTGRES_PASSWORD=test -p 5433:5432 postgres:16
# Apply existing migrations to head
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5433/postgres \
  alembic upgrade 106_drop_api_catalog_full_unique
# Apply this draft
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5433/postgres \
  alembic upgrade 107_audit_immutability_pseudonymization
# Smoke: try to UPDATE — must raise P0001
DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:5433/postgres \
  python -c "import asyncio; from sqlalchemy.ext.asyncio import create_async_engine; \
    asyncio.run(create_async_engine('postgresql+asyncpg://postgres:test@localhost:5433/postgres').execute('UPDATE audit_events SET actor_email=NULL'))"
# Expect: asyncpg.exceptions.RaiseError: audit_events is append-only (ADR-068)
```

## Companion documents

- **Audit**: `docs/audits/2026-05-11-uac-subscription-mcp/AUDIT-RESULTS.md` (Axe C, controls 5/6/7/10/11)
- **Plan**: `docs/plans/2026-05-11-uac-subscription-mcp-corrective.md` §5.4 (P0-4)
- **Decision record**: `docs/decisions/2026-05-11-uac-subscription-mcp-corrective.md` C5 + §3.3 Q4 + Q5
- **ADR-068 draft**: `docs/audits/2026-05-11-uac-subscription-mcp/adrs-drafts/adr-068-audit-log-actor-resource-doctrine.md`
- **ADR-069 draft**: `docs/audits/2026-05-11-uac-subscription-mcp/adrs-drafts/adr-069-gdpr-dora-audit-reconciliation.md`
