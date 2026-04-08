# Spec: Docker Seeder — Unified Seed Service with Environment Profiles

> Spec-driven development (CAB-2005). No ticket yet — will create after Council validation.

## Problem

Database seeding is fragmented across 7+ scripts (`seed-demo-data.py`, `seed_demo_tenant.py`, `seed_demo_prospects.py`, `seed-all.sh`, traffic seeders, Alembic embedded seeds) with no environment awareness. There is no way to say "seed for staging" vs "seed for dev" — everything produces the same demo data. New contributors must discover and chain scripts manually.

## Goal

A single Docker Compose service `stoa-seeder` that seeds the correct data for the target environment via `SEED_PROFILE={dev|staging|prod}`. Seeding is idempotent, profile-aware, and runnable with one command: `make seed-dev`.

## API Contract

No REST API. This is a CLI/Docker entrypoint.

```
python -m scripts.seeder --profile {dev|staging|prod} [--dry-run] [--check] [--reset] [--step STEP]

Exit codes:
  0 = success (all steps completed)
  1 = error (fatal failure, partial state possible)
  2 = partial (some steps skipped, non-fatal)

Environment variables:
  SEED_PROFILE          = dev | staging | prod (default: dev)
  DATABASE_URL          = postgresql+asyncpg://... (required)
  CONTROL_PLANE_URL     = http://control-plane-api:8000 (for HTTP-based steps)
  KEYCLOAK_URL          = http://keycloak:8080 (for KC-dependent steps)

Flags:
  --dry-run   Log planned operations without writing
  --check     Verify expected data exists, exit 0 if complete, 1 if missing
  --reset     Delete seed data before re-creating (blocked in prod profile)
  --step X    Run only step X (e.g., --step tenants)
```

## Acceptance Criteria

- [ ] AC1: `python -m scripts.seeder --profile dev` creates tenants, APIs, plans, consumers, MCP servers, tools, prospects, and gateway registrations in the database. All data is queryable via the Control Plane API.
- [ ] AC2: `python -m scripts.seeder --profile staging` creates a reduced dataset (2 tenants, 5 APIs, 3 plans, 5 consumers, 1 MCP server). No prospects, no traffic, no error snapshots.
- [ ] AC3: `python -m scripts.seeder --profile prod` creates only the admin tenant and gateway registration. No demo data.
- [ ] AC4: Running the seeder twice with the same profile produces no errors and no duplicate rows (idempotent upsert).
- [ ] AC5: `--dry-run` logs all planned INSERT/upsert operations to stdout without writing to the database. Row count before and after is identical.
- [ ] AC6: `--check` exits 0 if all expected rows for the profile exist, exits 1 with a list of missing entities.
- [ ] AC7: `--reset` with `--profile prod` exits 1 with error "Reset is not allowed in prod profile".
- [ ] AC8: `--reset` with `--profile dev` deletes seed data (tagged `source=seeder`) then re-creates it.
- [ ] AC9: `docker compose --profile seed-dev up stoa-seeder` runs the dev seeder after API and Keycloak are healthy, then exits 0.
- [ ] AC10: `--step tenants` runs only the tenants step, skipping all others.
- [ ] AC11: Each seeder step logs structured output: `[STEP] tenants: created 3 / skipped 0 / failed 0`.
- [ ] AC12: Steps execute in dependency order: `tenants → gateway → apis → plans → consumers → mcp_servers → prospects`. Running `--step consumers` when tenants don't exist exits 1 with "Missing dependency: tenants".
- [ ] AC13: All seeder-created rows carry a `source` field (or metadata) with value `seeder`, verifiable by `--check`.
- [ ] AC14: `--reset` with `--profile staging` succeeds with a warning log: "WARNING: Resetting staging seed data".

## Edge Cases

| Case | Input | Expected | Priority |
|------|-------|----------|----------|
| DB not reachable | `DATABASE_URL` points to down host | Exit 1, clear error "Cannot connect to database" within 10s | Must |
| Alembic migrations not applied | Tables don't exist | Exit 1, error "Run alembic upgrade head first" | Must |
| Partial previous run | Some seed data exists | Upsert/skip existing, create missing (idempotent) | Must |
| Unknown profile | `--profile qa` | Exit 1, error "Unknown profile: qa. Valid: dev, staging, prod" | Must |
| Unknown step | `--step foo` | Exit 1, error "Unknown step: foo. Valid: tenants, apis, ..." | Must |
| KC not reachable (dev) | Keycloak down | Skip KC-dependent steps, log warning, exit 2 (partial) | Should |
| Concurrent seeder runs | Two `stoa-seeder` containers | Both succeed (upsert idempotency) | Should |
| `--reset --step tenants` | Partial reset | Only delete+recreate tenant data, leave other steps untouched | Should |
| Step without dependency | `--step consumers` with no tenants | Exit 1, "Missing dependency: tenants" | Must |
| `--reset staging` | Reset staging data | Allowed with WARNING log, deletes `source=seeder` rows | Must |

## Out of Scope

- Keycloak realm import (handled by KC container's `KEYCLOAK_IMPORT` at boot)
- OpenSearch seeding (stays in `seed-error-snapshot.py` — different data store)
- Traffic generation (stays in `scripts/traffic/` — runtime activity, not seed data)
- LDAP/federation seeding (stays in `deploy/demo-federation/` — optional profile)
- E2E test fixtures (`e2e/fixtures/data-seeder.ts` — Playwright context, independent lifecycle)
- Alembic embedded seeds (migrations 048/057/074/075/091 — schema-level, not demo data)

## Security Considerations

- [ ] No auth required (seeder runs inside the Docker network, same trust boundary as migrations)
- [ ] `--reset` in prod is blocked at code level (not just docs)
- [ ] No PII — all seed data uses fake names/emails (`admin@demo.gostoa.dev`, `alice@demo.gostoa.dev`)
- [ ] `source=seeder` tag on all created rows enables safe targeted deletion
- [ ] DATABASE_URL from env var, never hardcoded

## Architecture Decisions (Council)

1. **SQLAlchemy-only**: All steps use async SQLAlchemy direct DB access. No dependency on Control Plane API running. KC-dependent steps set `provisioning_status=ready` to bypass async provisioning (same pattern as `seed_demo_tenant.py`).
2. **Module placement**: `control-plane-api/scripts/seeder/` — couplage DB normal, pas de seeding cross-component.
3. **Step ordering**: Topological — `tenants → gateway → apis → plans → consumers → mcp_servers → prospects`. `--step X` validates dependencies exist before running.
4. **Docker image**: Reuses `control-plane-api` Dockerfile (acceptable overhead vs maintaining a separate image).

## Dependencies

- PostgreSQL running + Alembic migrations applied (tables exist)
- Keycloak healthy (optional — graceful degradation if down, sets `provisioning_status=ready`)

## Notes

### Existing scripts to consolidate

| Current Script | Becomes Step | Profile |
|----------------|-------------|---------|
| `cp-api/scripts/seed_demo_tenant.py` | `tenants` + `mcp_servers` + `consumers` | dev |
| `scripts/seed-demo-data.py` | `apis` + `plans` + `consumers` | dev, staging |
| `cp-api/scripts/seed_demo_prospects.py` | `prospects` | dev only |
| Alembic 057/091 gateway seed | `gateway` | dev, staging, prod |

### Data volume per profile

| Profile | Tenants | APIs | Plans | Consumers | MCP Servers | Prospects | ~Rows |
|---------|---------|------|-------|-----------|-------------|-----------|-------|
| dev | 3 | 10+ | 4 | 5+ | 3 | 12 | ~500 |
| staging | 2 | 5 | 2 | 5 | 1 | 0 | ~100 |
| prod | 1 | 0 | 0 | 0 | 0 | 0 | ~10 |

### Docker Compose integration

The `stoa-seeder` service uses `profiles:` so it never runs on plain `docker compose up`. It requires explicit `--profile seed-dev` (or staging/prod).

### Tagging strategy

All seeder-created rows include a `source` or `metadata` field value of `seeder` (or `demo_seed` for backward compatibility with existing seeders). This enables `--reset` to target only seeder data without touching user-created data.
