# STOA CLI

Command-line interface for STOA Platform management. Authenticate, browse APIs, deploy configurations via YAML manifests.

## Tech Stack

- Python 3.11, Typer (CLI framework), Rich (terminal formatting)
- OIDC/PKCE browser-based auth via Keycloak

## Prerequisites

- Python 3.11+

## Quick Start

```bash
pip install -e ".[dev]"
stoa --help
```

## Commands

| Command | Description |
|---------|-------------|
| `stoa login` | OIDC/PKCE browser-based auth |
| `stoa logout` | Clear stored tokens |
| `stoa get apis` | List APIs (table/json/wide) |
| `stoa get api <id>` | Get API details |
| `stoa apply -f <file>` | Create/update from YAML manifest |
| `stoa status` | Connection health + token state |
| `stoa deploy create` | Create a deployment |
| `stoa deploy list` | List deployments |
| `stoa deploy get <id>` | Get deployment details |
| `stoa deploy rollback <id>` | Rollback a deployment |

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -q              # Tests
ruff check .                  # Lint
```

## CI

No dedicated CI workflow exists for the CLI yet. Lint and test locally before pushing.

## Dependencies

- **Depends on**: control-plane-api (REST API), Keycloak (auth)
- **Depended on by**: nothing (end-user tool)
