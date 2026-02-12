# MCP Gateway (edge-mcp mode)

## Overview
Production MCP (Model Context Protocol) gateway. Exposes legacy APIs as AI-callable tools via SSE transport. Handles policy enforcement (OPA), metering (Kafka), semantic caching, and multi-tenant tool routing.

## Tech Stack
- Python 3.11, FastAPI 0.109, Pydantic v2
- SQLAlchemy 2.0 (async), asyncpg
- OPA (embedded policy engine), Kafka (aiokafka)
- Kubernetes-asyncio (CRD watcher), Vault (hvac)
- sentence-transformers (semantic cache), Prometheus, OpenTelemetry

## Directory Structure
```
src/
├── main.py              # FastAPI app + SSE endpoints
├── config/              # Settings management
├── db/                  # SQLAlchemy models (api_keys, subscriptions)
├── cache/               # Semantic caching (embedder, cache engine)
├── clients/             # core_api_client (talks to control-plane-api)
├── handlers/            # MCP protocol handlers (mcp.py, mcp_sse.py, servers, subscriptions)
├── k8s/                 # Kubernetes CRD watcher (models, watcher)
├── middleware/           # auth, cache, metrics, response_transformer, shadow, token_counter
├── models/              # Domain models (mcp, server, subscription, error_snapshot)
├── policy/              # OPA integration (argument_engine, opa_client, scopes)
├── services/            # Core services + tool_registry/ (7 submodules)
├── tools/               # Tool definitions (consolidated, core)
├── transformer/         # Response adapters (notion, linear), capper, engine
└── features/            # Error snapshots (capture, middleware, publisher)
```

## Development
```bash
pip install -e ".[dev,k8s]"
python -m src.main               # Dev server
pytest --cov=src                 # Tests
ruff check . && mypy src/        # Lint + types
```

## Key Patterns
- Tool Registry pattern (`services/tool_registry/`) with 7 submodules
- Adapter pattern for response transformation (`transformer/adapters/`)
- OPA-based policy enforcement (`policy/`)
- CRD-driven tool registration (`k8s/watcher.py`)

## Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `OPA_ENABLED` | `true` | OPA policy engine |
| `OPA_EMBEDDED` | `true` | Embedded evaluator |
| `METERING_ENABLED` | `true` | Kafka metering |
| `K8S_WATCHER_ENABLED` | `false` | CRD watcher |

## Dependencies
- **Depends on**: control-plane-api (config sync), PostgreSQL, Kafka, OPA, Vault
- **Depended on by**: AI agents (via MCP protocol), stoa-gateway (future replacement)

## Code Style
- Line length: 100
- ruff + mypy (strict)
