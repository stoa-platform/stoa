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

