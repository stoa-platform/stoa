# Control Plane API

FastAPI backend powering the STOA Console and Portal. Handles tenant management, API catalog, subscriptions, gateway deployments, RBAC, and GitOps orchestration.

## Tech Stack

- Python 3.11, FastAPI 0.109, SQLAlchemy 2.0 (async), Pydantic v2
- PostgreSQL (asyncpg), Alembic for migrations
- Keycloak (OIDC + RBAC), Kafka (aiokafka)
- OpenTelemetry instrumentation, Prometheus metrics

## Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Keycloak instance (for auth)

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env              # Edit DATABASE_URL, KEYCLOAK_URL
cd alembic && alembic upgrade head # Run migrations
cd .. && uvicorn src.main:app --reload --port 8000
```

API docs at `http://localhost:8000/docs`.

## Commands

```bash
uvicorn src.main:app --reload          # Dev server
pytest tests/ --cov=src -q             # Tests
ruff check . && black --check .        # Lint
mypy src/                              # Type check
```

## Project Structure

```
src/
├── main.py              # FastAPI app entry point
├── config.py            # Settings (Pydantic BaseSettings)
├── database.py          # Async SQLAlchemy engine/session
├── adapters/            # Gateway integrations (stoa, kong, gravitee, webmethods)
├── auth/                # Keycloak OIDC + RBAC dependencies
├── models/              # SQLAlchemy ORM models
├── repositories/        # Data access layer (CRUD)
├── routers/             # API endpoint modules
├── schemas/             # Pydantic request/response schemas
├── services/            # Business logic (keycloak, argocd, kafka)
└── workers/             # Background tasks (sync_engine, health_worker)
```

## Configuration

All settings are environment variables. See `.env.example` for the full list with defaults.

Key variables for local dev:
- `DATABASE_URL` — PostgreSQL connection string
- `KEYCLOAK_URL` / `KEYCLOAK_REALM` — Authentication server
- `KEYCLOAK_CLIENT_ID` / `KEYCLOAK_CLIENT_SECRET` — OIDC credentials

## Database Migrations

```bash
cd alembic/
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Dependencies

- **Depends on**: PostgreSQL, Keycloak, Kafka (optional), OpenSearch (optional)
- **Depended on by**: control-plane-ui, portal (via REST API), stoa-gateway (via admin API)
