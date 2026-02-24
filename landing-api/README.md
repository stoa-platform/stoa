# Landing API

Backend API for the STOA landing page. Handles invite management, prospect event tracking, welcome flows, and usage metrics.

## Tech Stack

- Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2
- PostgreSQL (asyncpg), Alembic for migrations
- structlog for structured logging, slowapi for rate limiting

## Project Structure

```
src/control_plane/
├── main.py              # FastAPI app entry point
├── config.py            # Settings (Pydantic BaseSettings, STOA_ env prefix)
├── database.py          # Async SQLAlchemy engine/session
├── api/v1/              # API endpoints
│   ├── router.py        # Route aggregation
│   ├── events.py        # Prospect event tracking
│   ├── invites.py       # Invite management (rate-limited)
│   └── welcome.py       # Welcome flow
├── models/              # SQLAlchemy ORM models
│   ├── invite.py        # Invite model
│   └── prospect_event.py # Event tracking model
├── schemas/             # Pydantic request/response schemas
│   ├── event.py
│   ├── invite.py
│   └── metrics.py
└── services/            # Business logic
    ├── event_service.py
    ├── invite_service.py
    └── metrics_service.py
```

## Prerequisites

- Python 3.12+
- PostgreSQL 15+

## Quick Start

```bash
pip install -e ".[dev]"
uvicorn src.control_plane.main:app --reload
```

## Configuration

All settings use the `STOA_` environment variable prefix (via pydantic-settings):

| Variable | Default | Description |
|----------|---------|-------------|
| `STOA_DB_HOST` | `localhost` | PostgreSQL host |
| `STOA_DB_PORT` | `5432` | PostgreSQL port |
| `STOA_DB_NAME` | `stoa` | Database name |
| `STOA_DB_USER` | `stoa` | Database user |
| `STOA_DB_PASSWORD` | *(required)* | Database password |
| `STOA_HOST` | `0.0.0.0` | Server bind address |
| `STOA_PORT` | `8080` | Server port |
| `STOA_LOG_LEVEL` | `INFO` | Log level |

## Development

```bash
# Lint
ruff check .

# Type check
mypy src/

# Tests (requires PostgreSQL)
pytest tests/ --cov=src -q

# Migrations
cd alembic && alembic upgrade head
```

## Testing

All tests require a running PostgreSQL instance. The test suite creates a separate `stoa_test` database automatically.

## Dependencies

- **Depends on**: PostgreSQL
- **Depended on by**: landing page (gostoa.dev)
