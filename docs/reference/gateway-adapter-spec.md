# Gateway Adapter Interface — Technical Specification

## Abstract

This document specifies the `GatewayAdapterInterface`, the contract that any API gateway must implement to be fully orchestrated by STOA's GitOps reconciliation pipeline.

**Module**: `control-plane-api/src/adapters/gateway_adapter_interface.py`

## AdapterResult

All operations return an `AdapterResult` dataclass:

```python
@dataclass
class AdapterResult:
    success: bool                    # Whether the operation succeeded
    resource_id: Optional[str]       # Gateway-side ID of the resource
    data: Optional[dict]             # Full response payload
    error: Optional[str]             # Error message if success=False
```

## Methods

### Lifecycle

| Method | Signature | Description |
|--------|-----------|-------------|
| `health_check` | `() -> AdapterResult` | Verify gateway is reachable and healthy |
| `connect` | `() -> None` | Initialize persistent connection (if needed) |
| `disconnect` | `() -> None` | Release connection resources |

### APIs

| Method | Signature | Description |
|--------|-----------|-------------|
| `sync_api` | `(api_spec, tenant_id, auth_token?) -> AdapterResult` | Create or update an API |
| `delete_api` | `(api_id, auth_token?) -> AdapterResult` | Delete an API |
| `list_apis` | `(auth_token?) -> list[dict]` | List all registered APIs |

**`api_spec`** must contain:
- `apiName`: str — API display name
- `apiVersion`: str — Semantic version
- `url` or `apiDefinition`: OpenAPI spec source

### Policies

| Method | Signature | Description |
|--------|-----------|-------------|
| `upsert_policy` | `(policy_spec, auth_token?) -> AdapterResult` | Create or update a policy |
| `delete_policy` | `(policy_id, auth_token?) -> AdapterResult` | Delete a policy |
| `list_policies` | `(auth_token?) -> list[dict]` | List all policies |

**`policy_spec`** must contain:
- `name`: str — Policy name (used for idempotent upsert)
- `type`: str — One of: `cors`, `rate_limit`, `logging`, `jwt`, `ip_filter`
- `config`: dict — Type-specific configuration

### Applications

| Method | Signature | Description |
|--------|-----------|-------------|
| `provision_application` | `(app_spec, auth_token?) -> AdapterResult` | Create app + associate with APIs |
| `deprovision_application` | `(app_id, auth_token?) -> AdapterResult` | Remove application |
| `list_applications` | `(auth_token?) -> list[dict]` | List all applications |

**`app_spec`** must contain:
- `subscription_id`: str
- `application_name`: str
- `api_id`: str
- `tenant_id`: str

### Auth / OIDC

| Method | Signature | Description |
|--------|-----------|-------------|
| `upsert_auth_server` | `(auth_spec, auth_token?) -> AdapterResult` | Create/update auth server alias |
| `upsert_strategy` | `(strategy_spec, auth_token?) -> AdapterResult` | Create/update auth strategy |
| `upsert_scope` | `(scope_spec, auth_token?) -> AdapterResult` | Create/update scope mapping |

### Aliases

| Method | Signature | Description |
|--------|-----------|-------------|
| `upsert_alias` | `(alias_spec, auth_token?) -> AdapterResult` | Create/update endpoint alias |

### Configuration

| Method | Signature | Description |
|--------|-----------|-------------|
| `apply_config` | `(config_spec, auth_token?) -> AdapterResult` | Apply global gateway config |

### Backup

| Method | Signature | Description |
|--------|-----------|-------------|
| `export_archive` | `(auth_token?) -> bytes` | Export full gateway state as ZIP |

## Idempotence Contract

All `upsert_*` and `sync_*` operations MUST be idempotent:

1. **First call**: Creates the resource, returns `AdapterResult(success=True, resource_id=...)`
2. **Subsequent calls** with same input: Updates the resource (or no-op if unchanged)
3. **Never** duplicates resources

Implementation pattern: lookup by name → PUT if exists, POST if not.

## Error Handling

- Operations MUST NOT raise exceptions; return `AdapterResult(success=False, error=...)`
- The caller (reconciliation engine or provisioning service) decides retry strategy
- HTTP 409 (conflict/already exists) should be treated as success for upsert operations

## Authentication

All methods accept an optional `auth_token` parameter:
- **OIDC proxy mode** (`auth_token` provided): Forward JWT to gateway admin API
- **Basic Auth mode** (`auth_token` is None): Use pre-configured credentials
