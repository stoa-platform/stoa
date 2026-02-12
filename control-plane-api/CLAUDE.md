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
