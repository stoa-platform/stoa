# Control Plane API

## Overview
FastAPI backend powering the STOA Console and Portal. Handles tenant management, API catalog, subscriptions, gateway deployments, RBAC, and GitOps orchestration.

## Tech Stack
- Python 3.11, FastAPI 0.109, SQLAlchemy 2.0 (async), Pydantic v2
- PostgreSQL (asyncpg), Alembic for migrations
- Keycloak (OIDC + RBAC), Kafka (aiokafka), Vault (hvac)
- OpenTelemetry instrumentation, Prometheus metrics

## Directory Structure
```
src/
├── main.py              # FastAPI app entry point
├── config.py            # Settings (Pydantic BaseSettings)
├── database.py          # Async SQLAlchemy engine/session
├── adapters/            # Gateway integrations (webmethods, stoa, template)
├── auth/                # Keycloak OIDC + RBAC dependencies
├── core/                # PII masking, config
├── features/            # Feature modules (error_snapshots)
├── middleware/           # HTTP logging, metrics, rate limiting
├── models/              # SQLAlchemy ORM models
├── repositories/        # Data access layer (CRUD)
├── routers/             # 38+ API endpoint modules
├── schemas/             # Pydantic request/response schemas
├── services/            # Business logic (keycloak, argocd, kafka, etc.)
└── workers/             # Background tasks (sync_engine, health_worker)
```

## Development
```bash
pip install -r requirements.txt
uvicorn src.main:app --reload          # Dev server
pytest --cov=src --cov-fail-under=70   # Tests + coverage
ruff check . && black --check .        # Lint
mypy src/                              # Type check
```

## Local Test Setup
- Tests run without external services — conftest.py mocks Kafka, Keycloak, GitLab, ArgoCD
- `KAFKA_ENABLED=false` is set in conftest (prevents any Kafka connection attempt)
- `@pytest.mark.integration` tests are auto-skipped when `DATABASE_URL` is not set
- To run integration tests locally: `DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/stoa_test pytest -m integration`
- OpenSearch tests are always ignored: `--ignore=tests/test_opensearch.py`

## Migrations
```bash
cd alembic/
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Key Patterns
- Repository pattern for data access (`repositories/`)
- Adapter pattern for multi-gateway support (`adapters/`)
- Dependency injection via FastAPI `Depends()`
- RBAC via `auth/rbac.py` decorators

## Dependencies
- **Depends on**: PostgreSQL, Keycloak, Kafka, Vault, OpenSearch
- **Depended on by**: control-plane-ui, portal (via REST API), mcp-gateway (via core_api_client)

## Code Style
- Line length: 120
- ruff + black + isort + mypy

## Règles

Détail on-demand: `.claude/docs/code-style-python.md`, `testing-standards.md`, `gateway-adapters.md`.

- Ligne 120. Ruff E,W,F,I,B,C4,UP,ARG,SIM,S,DTZ,LOG,RUF. Black + isort (profile=black).
- mypy strict: `disallow_untyped_defs = true`. Type hints obligatoires.
- Async par défaut. Pydantic v2. Python 3.11.
- Coverage ≥ 70%: `pytest --cov=src --cov-fail-under=70 --ignore=tests/test_opensearch.py -q`.
- Test-first pour feat/fix. `test_regression_cab_XXXX_*` pour fix (regression-guard bloquant).
- Boundary Integrity: jamais mocker la boundary sous test. `httpx.MockTransport` > `AsyncMock`. FastAPI TestClient + DB in-memory > patch repo.
- Adapters gateway: implémenter les 16 méthodes de `GatewayAdapterInterface`. `AdapterResult(success=False)` pour unsupported, jamais raise. `httpx.AsyncClient` obligatoire. Tests ≥ 30.
- Alembic: `alembic revision --autogenerate -m "..."` puis `upgrade head`. COMMIT avant `ADD VALUE` sur enum.

## BASE_DOMAIN — derived URLs recompute on Settings instantiation

Per CAB-2199 / INFRA-1a S2, the module-level `_BASE_DOMAIN = os.getenv(...)` was
removed. `BASE_DOMAIN` is now a normal Pydantic field, and derived URLs
(`KEYCLOAK_URL`, `GATEWAY_URL`, `GATEWAY_ADMIN_PROXY_URL`, `ARGOCD_URL`,
`ARGOCD_EXTERNAL_URL`, `GRAFANA_URL`, `PROMETHEUS_URL`, `LOGS_URL`,
`VAULT_ADDR`, `CORS_ORIGINS`) are filled in by `_derive_urls_from_base_domain`
— a `model_validator(mode="before")` that uses `setdefault` (presence-based,
not truthiness-based).

**Implication for tests**: `Settings(BASE_DOMAIN="other.tld").KEYCLOAK_URL`
now returns `"https://auth.other.tld"`. Previously frozen at import time at
`"https://auth.gostoa.dev"` — silent test isolation bug.

**Behavior expansion**: an explicit empty-string override
(`Settings(KEYCLOAK_URL="")`) is now **preserved**, where the prior
frozen-default code would have always returned the f-string value. Other
explicit overrides (e.g. `KEYCLOAK_URL="https://kc.foo.io"`) win over
BASE_DOMAIN derivation as before.

If you add a new derived URL field, register it in the validator's `derived`
dict. **Do NOT add new `gostoa.dev` literals** outside the `BASE_DOMAIN`
default and the validator's fallback — Q6 multi-env-ready rule.

## OpenSearch — audit endpoint vs docs/embedding endpoint

Per CAB-2199 / INFRA-1a S3 (Christophe arbitrage 2026-04-29 §3.1 = Option A),
the former standalone `OpenSearchSettings` class (lived in
`src/opensearch/opensearch_integration.py`) is now `Settings.opensearch_audit`
— an `OpenSearchAuditConfig` sub-model in main Settings, mirroring the
`GitProviderConfig` pattern. Hydrated from flat env vars
(`OPENSEARCH_HOST/USER/PASSWORD/VERIFY_CERTS/CA_CERTS/TIMEOUT` + `AUDIT_*`)
by the `_hydrate_opensearch_audit` validator (mode="after").

This is the **audit-logger / search-service endpoint** (currently
`https://opensearch.gostoa.dev` in prod via Helm chart `env.OPENSEARCH_HOST`).

`Settings.OPENSEARCH_URL` (default `http://opensearch.stoa-system.svc...:9200`)
is a **separate** field for docs/embedding search. The two endpoints can —
and in prod often do — point at different OpenSearch clusters. **Do not
conflate.**

**Precedence rule**: explicit `Settings(opensearch_audit=OpenSearchAuditConfig(...))`
wins over the flat env fields. Absence of an explicit sub-model triggers
flat-field hydration. Detection compares `model_dump()` outputs to avoid
SecretStr-equality fragility.

**SecretStr boundary**: `opensearch_audit.password` is a `SecretStr` (CAB-2199
§3.1). Consumer code passing it to OpenSearch client must unwrap with
`.get_secret_value()` (see `src/opensearch/opensearch_integration.py`
`OpenSearchService.connect`).

**Long-term**: rename `OPENSEARCH_URL` → `DOCS_SEARCH_OPENSEARCH_URL` for
disambiguation (deferred to INFRA-1b or Bug Hunt). Phase 1a does not change
this.

**Legacy import compat**: `from src.opensearch.opensearch_integration import
get_settings` still works — the function now returns
`settings.opensearch_audit` (the sub-model) so legacy callers keep working.
The legacy class export `OpenSearchSettings` was removed from
`src/opensearch/__init__.py` — import `OpenSearchAuditConfig` from
`src.config` if you need the type.

## STOA_API_SNAPSHOT_* — error-snapshot config (renamed from STOA_SNAPSHOTS_*)

Per CAB-2199 / INFRA-1a S6 (Christophe arbitrage 2026-04-29 §3.3 = A1), the
error-snapshot Pydantic Settings env prefix was renamed from
`STOA_SNAPSHOTS_*` (plural) to `STOA_API_SNAPSHOT_*` (singular + `_API_`
namespace) to disambiguate from the unrelated `STOA_SNAPSHOT_*` (singular,
in-process ring buffer) on the Rust gateway.

**Legacy alias surface**: each field carries a per-field
`validation_alias=AliasChoices(NEW, OLD)` so the legacy `STOA_SNAPSHOTS_*`
prefix continues to resolve from process env, dotenv, or any other
pydantic-settings source. Legacy usage emits at boot:

- a `WARNING`-level deprecation log line (KEYS only, never values),
- a Prometheus Counter `stoa_deprecated_config_used_total{name="STOA_SNAPSHOTS_*"}`
  (one-shot per `(key, process)` via `_METRIC_EMITTED_KEYS` set + Lock).

**Conflict gate** (Phase 3-B hardened): setting both prefixes for the same
suffix with different values fails boot with `ValueError`. Behaviour:

- **Scoped to declared field suffixes.** The scanner enumerates
  `SnapshotSettings.model_fields` and only checks suffixes
  corresponding to real fields. Leftover env vars matching the prefix
  but no declared field (e.g. `STOA_SNAPSHOTS_FOO_REMOVED_LAST_RELEASE`)
  do NOT trigger spurious boot failures.
- **Honors the `_env_file=` runtime override.** Pydantic-Settings
  consumes that kwarg internally; `SnapshotSettings.__init__` stashes
  it in a `ContextVar` so the validator scans the same dotenv used
  for field resolution (not just the static cwd `.env`). Pass
  `_env_file=None` to disable the dotenv pass entirely.
- **Value-blind error format.** The `ValueError` message lists the
  source key names only — never the conflicting values. Eliminates the
  need for a substring-match secret heuristic at the error boundary
  (which had known false negatives like `DB_DSN`/`JWT_SIG_INPUT`).

Example error:

```
ValueError: Conflicting config for suffix 'STORAGE_BUCKET': sources
['env:STOA_API_SNAPSHOT_STORAGE_BUCKET', 'env:STOA_SNAPSHOTS_STORAGE_BUCKET']
have different values. Remove the legacy STOA_SNAPSHOTS_* key or align
both prefixes to the same value. (Values are intentionally omitted
from this message to avoid leaking secrets.)
```

**Defence-in-depth helpers** (`_is_secret_env_key`, `_redact_value`)
remain available in the module for any future log path that includes
values. They are NOT called by the Phase 3-B validator — the design
contract is "values never leave the process via this path".

**Sunset**: tracked on **CAB-2203** — the alias surface (per-field
`AliasChoices`, conflict scanner, masking helpers) can be removed once the
Prometheus Counter reads 0 in prod for 30 consecutive days. Evidence-driven,
no calendar (per HLFH policy `feedback_no_schedule_arbitrary_timers.md`).

**Migration**: rename ops env vars from `STOA_SNAPSHOTS_*` to
`STOA_API_SNAPSHOT_*`. Either prefix alone works; both with matching values
work; conflicting values fail boot.

**Schema metadata**: `SnapshotSettings.DEPRECATED_PREFIX_ALIASES: ClassVar[dict[str, str]]`
declares the alias mapping for the INFRA-1c CI gate to consume.

