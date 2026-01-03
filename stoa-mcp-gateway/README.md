# STOA MCP Gateway

> Model Context Protocol Gateway for AI-Native API Management

## Overview

The STOA MCP Gateway exposes APIs as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools, enabling LLMs to discover and invoke APIs through a standardized interface.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          STOA MCP Gateway                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     MCP Protocol Layer                           │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │   │
│  │  │  Tools   │  │Resources │  │ Prompts  │  │ Sampling │        │   │
│  │  │Discovery │  │  Access  │  │Templates │  │  Hooks   │        │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                  │                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Security Layer                               │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │   │
│  │  │ Keycloak │  │   OPA    │  │  Rate    │  │  Audit   │        │   │
│  │  │   OIDC   │  │ Policies │  │ Limiting │  │  Logs    │        │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                  │                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Backend Adapters                             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │   │
│  │  │ REST/OAS │  │ GraphQL  │  │   gRPC   │  │  Kafka   │        │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- pip or uv

### Installation

```bash
# Clone the repository
cd stoa-mcp-gateway

# Install dependencies
pip install -e ".[dev]"

# Or with uv
uv pip install -e ".[dev]"
```

### Run Development Server

```bash
# Set environment variables
export BASE_DOMAIN=stoa.cab-i.com
export DEBUG=true

# Run the server
python -m src.main

# Or with uvicorn directly
uvicorn src.main:app --reload --port 8080
```

### Health Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check for load balancers |
| `GET /ready` | Readiness check for Kubernetes |
| `GET /live` | Liveness check for Kubernetes |
| `GET /metrics` | Prometheus metrics |

### MCP Endpoints (Coming Soon)

| Endpoint | Description |
|----------|-------------|
| `GET /mcp/v1/tools` | List available MCP tools |
| `GET /mcp/v1/resources` | List available MCP resources |
| `POST /mcp/v1/tools/{tool}/invoke` | Invoke an MCP tool |

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_DOMAIN` | `stoa.cab-i.com` | Base domain for STOA services |
| `ENVIRONMENT` | `dev` | Environment (dev/staging/prod) |
| `DEBUG` | `false` | Enable debug mode |
| `PORT` | `8080` | Server port |
| `KEYCLOAK_URL` | Derived from BASE_DOMAIN | Keycloak URL |
| `KEYCLOAK_REALM` | `stoa` | Keycloak realm |
| `LOG_LEVEL` | `INFO` | Logging level |

## Project Structure

```
stoa-mcp-gateway/
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config/              # Settings and configuration
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── handlers/            # MCP protocol handlers
│   │   └── __init__.py
│   ├── middleware/          # Auth, rate limiting, etc.
│   │   └── __init__.py
│   ├── models/              # Pydantic models
│   │   └── __init__.py
│   └── services/            # Business logic
│       └── __init__.py
├── tests/
│   ├── __init__.py
│   └── test_health.py
├── pyproject.toml
└── README.md
```

## Development

### Run Tests

```bash
pytest
```

### Code Quality

```bash
# Linting
ruff check src tests

# Type checking
mypy src
```

## Related Documentation

- [STOA Platform](../README.md)
- [MCP Specification](https://modelcontextprotocol.io/)
- [Phase 12 - STOA Gateway + Copilot](../docs/ARCHITECTURE-PRESENTATION.md)

## License

MIT - CAB Ingénierie
