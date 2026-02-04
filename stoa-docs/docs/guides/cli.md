---
sidebar_position: 3
title: CLI
description: Use the stoa CLI to manage the platform from the terminal.
---

# CLI

The `stoa` CLI provides command-line access to the STOA platform. Built with Python (Typer + Rich), it supports tenant management, API operations, health checks, and more.

## Installation

```bash
pip install stoa-cli
```

Or install from source:

```bash
cd cli
pip install -e .
```

## Authentication

The CLI authenticates via Keycloak using OAuth 2.0 password grant:

```bash
stoa login --server https://api.gostoa.dev
```

You'll be prompted for username and password. The token is cached locally for subsequent commands.

### Environment Variables

```bash
export STOA_SERVER=https://api.gostoa.dev
export STOA_TOKEN=<your-token>
```

## Commands

### `stoa status`

Check platform health:

```bash
$ stoa status
┌──────────────────────┬────────┐
│ Component            │ Status │
├──────────────────────┼────────┤
│ Control Plane API    │ ✓ OK   │
│ Developer Portal     │ ✓ OK   │
│ Console UI           │ ✓ OK   │
│ MCP Gateway          │ ✓ OK   │
│ Keycloak             │ ✓ OK   │
└──────────────────────┴────────┘
```

### `stoa tenant`

Manage tenants:

```bash
# List tenants
stoa tenant list

# Create a tenant
stoa tenant create --name acme --display-name "ACME Corp"

# Show tenant details
stoa tenant show acme
```

### `stoa api`

Manage APIs within a tenant:

```bash
# List APIs for a tenant
stoa api list --tenant acme

# Create an API
stoa api create --tenant acme --name petstore --version 1.0.0 --spec ./openapi.json

# Show API details
stoa api show --tenant acme --name petstore

# Delete an API
stoa api delete --tenant acme --name petstore --version 1.0.0
```

### `stoa subscription`

Manage subscriptions:

```bash
# List subscriptions for an API
stoa subscription list --tenant acme --api petstore

# Approve a subscription
stoa subscription approve --id sub-123
```

### `stoa login`

Authenticate with the platform:

```bash
# Interactive login
stoa login --server https://api.gostoa.dev

# Login with credentials
stoa login --server https://api.gostoa.dev --username admin@stoa.local --password <pass>
```

## Output Formats

The CLI supports multiple output formats:

```bash
# Table (default)
stoa tenant list

# JSON
stoa tenant list --format json

# YAML
stoa tenant list --format yaml
```

## Configuration File

The CLI reads configuration from `~/.stoa/config.yaml`:

```yaml
server: https://api.gostoa.dev
default_tenant: acme
output_format: table
```

## Shell Completion

Enable tab completion for your shell:

```bash
# Bash
stoa --install-completion bash

# Zsh
stoa --install-completion zsh

# Fish
stoa --install-completion fish
```

See [CLI Reference](../reference/cli-reference) for the full command reference.
