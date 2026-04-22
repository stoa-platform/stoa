# CAB-2147 Phase 1.5 — Spike Report

**Date:** 2026-04-22
**Scope:** Three open questions raised by Council Path A re-plan + ADR `2026-04-22-cab-2147-e2e-tenant-prefix.md`.
**Outcome:** All three resolved. Architecture simpler than the ADR assumed. Harness diag (task #10) still pending.

---

## Spike A — Multi-tenant user model in CP-API

**Question:** Does CP-API support a user being member of >1 tenant today?

**Answer: No.** CP-API auth model is **single-tenant-per-user**.

**Evidence:**
- `control-plane-api/src/auth/dependencies.py:53` — `User.tenant_id: str | None` (scalar)
- `dependencies.py:233-234` — `tenant_id = (raw_tenant_id[0] if raw_tenant_id else None)` — even if KC sends a list (group mapper), only first wins
- `control-plane-api/src/auth/rbac.py:215` — `if user.tenant_id != tenant_id:` strict equality check
- No `tenant_users` / `TenantMembership` / `UserTenantLink` join table in `control-plane-api/src/models/`

**Implication for ADR:** The "personas dual-membership" idea in the Path A ADR is **infeasible without a schema change**. Need to revise the ADR with one of:

| Option | Cost | Verdict |
|--------|------|---------|
| **A1** Add multi-tenant user table | Schema migration + auth refactor + RBAC rewrite | Out of scope (>10 pts on its own) |
| A2 Swap existing personas to `tenant_id=e2e-<x>` via KC group mapping | Loses prod tenant access for personas | Breaks any prod work that uses these personas |
| **A3 (recommended)** Provision NEW e2e personas in prod KC realm: `parzival-e2e@e2e-high-five.io`, etc. | Phase 2 grows by ~3 pts (7 KC users + group mappings) | Clean, no schema change, no prod impact |

---

## Spike B — Portal catalog query scope

**Question:** Does `/v1/portal/apis` union across user's tenants, or scope to a "primary" tenant?

**Answer: Catalog is GLOBAL by default**, not tenant-scoped at all.

**Evidence:** `control-plane-api/src/routers/portal.py:291-337`

```python
@router.get("/apis", response_model=PortalAPIsResponse)
async def list_portal_apis(user: User = Depends(get_current_user), ...):
    # Comment: "Returns APIs from all tenants the user has access to."
    tenant_ids = UNIVERSE_TENANTS.get(universe) if universe else None
    apis, total = await repo.get_portal_apis(
        ..., tenant_ids=tenant_ids, ...
    )
```

`tenant_ids=None` when no `universe` query param → no tenant filter at all. The query returns ALL `portal_published=true` APIs across the whole platform.

`UNIVERSE_TENANTS = {"oasis": ["high-five", "oasis", "ioi"], "enterprise": ["demo"]}` (line 70-72) — if Portal UI passes `?universe=oasis`, only those 3 tenants surface. **Grep on portal/ for `universe=oasis`: 0 matches.** Portal UI does not pass it. So in practice the catalog is fully global.

**Implication for plan:**
- Any persona will see APIs from `e2e-*` tenants in Portal catalog **without** dual-membership or new universe entry, as long as APIs are `portal_published=true` AND `audience='public'`.
- Family B (12 portal-catalog tests) is unblocked by the seeder writing into `e2e-*` tenants. Existing personas work.
- For Console RBAC tests (Family A/C), the persona's `tenant_id` claim DOES matter — Console enforces tenant scoping. This is where Option A3 (new e2e personas) is needed.

---

## Spike C — Kafka consumer behavior on E2E tag

**Question:** Do Kafka consumers honor `e2e=true` tag, or do we need consumer-side filters?

**Answer: NON-ISSUE. Seeder doesn't emit Kafka events at all.**

**Evidence:**
- `control-plane-api/scripts/seeder/steps/{tenants,gateway,apis,plans,consumers,mcp_servers,prospects,security_posture}.py` — all use `session.execute(text("INSERT INTO ..."))` raw SQL
- `grep -r "kafka_service\|publish_event\|publish_lifecycle" control-plane-api/scripts/seeder/` → **0 matches**
- The seeder bypasses the FastAPI router layer entirely (HTTP routers are where `kafka_service.publish_event(...)` is called)

**Implication for plan:** The Council's biggest Archi concern (Kafka topic pollution: `stoa.api.lifecycle`, `stoa.tenant.lifecycle`, `stoa.audit.trail`, etc.) **is unfounded**. The seeder writes only to PostgreSQL.

**Consumers downstream are not at risk:**
- `error_snapshot_consumer.py`, `security_alert_consumer.py`, `chat_metering_consumer.py`, `billing_metering_consumer.py`, `sync_engine.py`, `git_sync_worker.py` — all consume Kafka topics that the seeder never produces to.
- `stoa-gateway/src/events/notifications.rs` (`stoa.api.lifecycle`) — only fires on gateway-side events, not DB writes.

**Caveat:** if a future enhancement adds Kafka publishes inside the seeder, this concern reopens. Phase 3 should add a unit test asserting `kafka_service` is never imported by any `scripts/seeder/steps/*.py`.

---

## Consolidated impact on Council adjustments and ADR

| # | Adjustment | Status after spikes |
|--:|------------|---------------------|
| 9 | ADR / decision log entry | **Done but needs revision** — dual-membership claim must change to "new e2e personas in prod KC realm" (Option A3) |
| 10 | Phase 3 seeds into `e2e-*` prefixed tenants | **Confirmed feasible** — seeder works at DB layer, no permission/visibility blockers |
| 11 | Idempotency contract tests | Still planned for Phase 3 |
| 14 | `e2e=true` annotation on audit rows | **Mostly moot** — seeder doesn't trigger audit events. Keep annotation on the few rows that DO end up in audit (e.g., manual KC client creation if logged) |

## Recommended revisions

### To ADR `docs/decisions/2026-04-22-cab-2147-e2e-tenant-prefix.md`

1. **Replace dual-membership section (Scope rule #2)** with: "Phase 2 provisions 7 NEW Keycloak users in the prod realm (`parzival-e2e@e2e-high-five.io`, etc.) with `tenant_id=e2e-<x>` group/role mapping. Existing prod personas are untouched."
2. **Update Phase 2 cost estimate** from 5-8 pts to **6-9 pts** (+3 pts for KC user provisioning + Vault secret entries for new persona passwords).
3. **Add Spike C finding to "Negative consequences" section**, downgrading the Kafka concern: "Seeder operates at PostgreSQL layer only; no Kafka events emitted. Consumers downstream are unaffected."

### To inventory `docs/audits/cab-2147-seed-inventory/README.md`

1. **Phase 2 grows to 6-9 pts** — add KC user provisioning sub-step.
2. **Phase 3 personas section**: tests authenticate as `parzival-e2e` (not `parzival`) when `E2E_USE_E2E_PERSONAS=1`. Add new env-vars to `e2e-tests.yml` Vault step: `secret/data/e2e/personas/parzival-e2e username|password`, etc.
3. **Drop Council adjustment #14 from active scope** (or scope it down to 1-line: "if a future seeder step starts using kafka_service, it MUST tag events with `e2e=true`").

### Re-score implication

If we apply these revisions, Archi 50x50 likely moves 7 → 8 (Kafka concern cleared). New persona avg = (7+8+8+7+8+**8**+7+8)/8 = **7.625**. Final score: 7.625 - 1.0 = **6.625** → still **Fix** but cleaner. The verdict stays Fix because CRITICAL impact modifier (-1.0) is structural, not addressable by Phase 1.5.

---

## Outstanding work

**Task #10 (harness diag)** — pending. The 6 Console tests rendering Login-with-Keycloak in retry traces are still unexplained. Until that's diagnosed, even the new e2e personas may hit the same bug. Phase 2 can't safely start until either:
- (a) harness root cause identified and fixed (likely a SSO consent step in `auth.setup.ts:263-267` that fails silently for some personas), or
- (b) the bug is shown to be persona-specific and the new e2e personas would not trigger it.

Time-box: 4h hard limit per Council #2. Next session.
