# STOA CLI

## Overview
Command-line interface for STOA Platform management. Authenticate, browse APIs, deploy configurations via YAML manifests.

## Tech Stack
- Python 3.11, Typer (CLI framework), Rich (terminal formatting)
- OIDC/PKCE browser-based auth via Keycloak

## Commands
| Command | Description |
|---------|-------------|
| `stoa login` | OIDC/PKCE browser-based auth |
| `stoa logout` | Clear stored tokens |
| `stoa get apis` | List APIs (table/json/wide) |
| `stoa get api <id>` | Get API details |
| `stoa apply -f <file>` | Create/update from YAML manifest |
| `stoa status` | Connection health + token state |

## Directory Structure
```
src/
├── commands/            # Subcommand modules (login, apply, get, status)
└── ...
tests/                   # 55 tests, 84% coverage
```

## Development
```bash
pip install -e ".[dev]"
pytest --cov=src         # Tests
ruff check .             # Lint
```

## Dependencies
- **Depends on**: control-plane-api (REST API), Keycloak (auth)
- **Depended on by**: nothing (end-user tool)
