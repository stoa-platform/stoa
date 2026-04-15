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

## Règles

Détail on-demand: `.claude/docs/stoactl-usage.md`, `cli-first.md`, `code-style-python.md`.

- stoactl > curl/bash pour toute opération supportée. Lire `.claude/context/cli-reference.md` avant de scanner src/.
- Ligne 100. Python 3.11. Ruff + black.
- `--output json|yaml|table|csv` supporté sur toutes les commandes.
- `--redact-pii` default true sur `audit export`.
- Après ajout de commande/schema: `scripts/generate-cli-context.sh`.
