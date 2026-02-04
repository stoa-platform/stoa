---
sidebar_position: 2
title: CLI Reference
description: Complete stoa CLI command reference.
---

# CLI Reference

Full command reference for the `stoa` CLI. See [CLI Guide](../guides/cli) for usage examples.

## Global Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--server` | `-s` | `$STOA_SERVER` | API server URL |
| `--token` | `-t` | `$STOA_TOKEN` | Authentication token |
| `--format` | `-f` | `table` | Output format: `table`, `json`, `yaml` |
| `--verbose` | `-v` | `false` | Enable verbose output |
| `--help` | | | Show help and exit |
| `--version` | | | Show version and exit |

## `stoa login`

Authenticate with the STOA platform.

```
stoa login [OPTIONS]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--server` | Yes | API server URL |
| `--username` | No | Username (interactive prompt if omitted) |
| `--password` | No | Password (interactive prompt if omitted) |
| `--client-id` | No | OIDC client ID (default: `control-plane-ui`) |

**Examples**:

```bash
# Interactive login
stoa login --server https://api.gostoa.dev

# Non-interactive
stoa login --server https://api.gostoa.dev \
  --username admin@gostoa.dev --password secret
```

## `stoa status`

Check platform component health.

```
stoa status [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--component` | Check a specific component only |

**Output**:

```
┌──────────────────────┬────────┬──────────┐
│ Component            │ Status │ Latency  │
├──────────────────────┼────────┼──────────┤
│ Control Plane API    │ ✓ OK   │ 45ms     │
│ Developer Portal     │ ✓ OK   │ 32ms     │
│ Console UI           │ ✓ OK   │ 28ms     │
│ MCP Gateway          │ ✓ OK   │ 51ms     │
│ Keycloak             │ ✓ OK   │ 67ms     │
└──────────────────────┴────────┴──────────┘
```

## `stoa tenant`

Manage tenants.

### `stoa tenant list`

```
stoa tenant list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--format` | Output format (table/json/yaml) |

### `stoa tenant create`

```
stoa tenant create [OPTIONS]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--name` | Yes | Tenant identifier (lowercase, hyphens) |
| `--display-name` | Yes | Human-readable name |
| `--email` | No | Contact email |

### `stoa tenant show`

```
stoa tenant show <TENANT_NAME>
```

### `stoa tenant delete`

```
stoa tenant delete <TENANT_NAME> [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--force` | Skip confirmation prompt |

:::warning
Deleting a tenant removes all its APIs, subscriptions, and applications. This operation cannot be undone.
:::

## `stoa api`

Manage APIs within a tenant.

### `stoa api list`

```
stoa api list [OPTIONS]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--tenant` | Yes | Tenant name |
| `--status` | No | Filter by status (draft/published/deprecated/retired) |

### `stoa api create`

```
stoa api create [OPTIONS]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--tenant` | Yes | Tenant name |
| `--name` | Yes | API name |
| `--version` | Yes | API version (semver) |
| `--spec` | No | Path to OpenAPI spec file |
| `--spec-url` | No | URL to OpenAPI spec |
| `--description` | No | API description |

### `stoa api show`

```
stoa api show [OPTIONS]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--tenant` | Yes | Tenant name |
| `--name` | Yes | API name |

### `stoa api delete`

```
stoa api delete [OPTIONS]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--tenant` | Yes | Tenant name |
| `--name` | Yes | API name |
| `--version` | Yes | API version |
| `--force` | No | Skip confirmation |

## `stoa subscription`

Manage API subscriptions.

### `stoa subscription list`

```
stoa subscription list [OPTIONS]
```

| Option | Required | Description |
|--------|----------|-------------|
| `--tenant` | No | Filter by tenant |
| `--api` | No | Filter by API name |
| `--status` | No | Filter by status |

### `stoa subscription approve`

```
stoa subscription approve --id <SUBSCRIPTION_ID>
```

### `stoa subscription reject`

```
stoa subscription reject --id <SUBSCRIPTION_ID> [--reason "..."]
```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | General error |
| `2` | Authentication error |
| `3` | Resource not found |
| `4` | Permission denied |
| `5` | Network error |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `STOA_SERVER` | Default API server URL |
| `STOA_TOKEN` | Authentication token |
| `STOA_TENANT` | Default tenant name |
| `STOA_FORMAT` | Default output format |
| `STOA_CONFIG` | Config file path (default: `~/.stoa/config.yaml`) |
| `NO_COLOR` | Disable colored output |
