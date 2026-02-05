---
description: Python code style rules for control-plane-api, mcp-gateway, cli, landing-api
globs: "**/*.py"
---

# Python Code Style

## Tools: ruff + black + isort + mypy

## Line Length
- **100**: mcp-gateway, landing-api, cli
- **120**: control-plane-api

## Ruff
- Rules: E, W, F, I, B, C4, UP, ARG, SIM, S, DTZ, LOG, RUF
- First-party package: `src`
- Run: `ruff check .`

## Black
- Config in each component's `pyproject.toml`
- Run: `black --check .`

## isort
- Profile: black
- Run via ruff (I rules)

## mypy
- `disallow_untyped_defs = true`
- Run: `mypy src/`

## Conventions
- Async by default (async/await preferred)
- Pydantic v2 for validation
- Type hints mandatory on all functions
- Python 3.11 (except landing-api: 3.12)
