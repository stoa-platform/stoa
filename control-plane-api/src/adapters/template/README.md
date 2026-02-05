# How to Build a STOA Gateway Adapter

This directory is a **copy-and-rename** template for implementing a new
gateway adapter. Follow the steps below to integrate any API gateway
with the STOA Control Plane.

## Quick Start

```bash
# 1. Copy the template
cp -r src/adapters/template/ src/adapters/my_gateway/

# 2. Rename the class in adapter.py
#    TemplateGatewayAdapter → MyGatewayAdapter

# 3. Update __init__.py
#    from .adapter import MyGatewayAdapter

# 4. Implement the 6 required methods (see below)

# 5. Register in src/adapters/registry.py
#    from .my_gateway import MyGatewayAdapter
#    AdapterRegistry.register("my_gateway", MyGatewayAdapter)

# 6. Run the tests
pytest tests/test_adapter_template.py -v
```

## Interface Overview

The `GatewayAdapterInterface` (see `src/adapters/gateway_adapter_interface.py`)
defines 18 abstract methods. Of these, **6 are required** and **12 are optional**.

### Required Methods (Must Implement)

| Method | Purpose |
|--------|---------|
| `connect()` | Initialize connection to the gateway admin API |
| `disconnect()` | Clean up connection resources |
| `health_check()` | Verify gateway connectivity and readiness |
| `sync_api(api_spec, tenant_id)` | Create or update an API on the gateway |
| `delete_api(api_id)` | Delete an API from the gateway |
| `list_apis()` | List all APIs on the gateway (for drift detection) |

### Optional Methods (Default: Not Supported)

These return `AdapterResult(success=False, error="Not supported by this gateway")`
by default. Override them if your gateway supports the functionality:

- **Policies**: `upsert_policy`, `delete_policy`, `list_policies`
- **Applications** (OAuth): `provision_application`, `deprovision_application`, `list_applications`
- **Auth / OIDC**: `upsert_auth_server`, `upsert_strategy`, `upsert_scope`
- **Config**: `upsert_alias`, `apply_config`, `export_archive`

## Config Dict Convention

The adapter constructor receives a `config` dict from the `AdapterRegistry`:

```python
config = {
    "base_url": "https://gateway-admin.example.com",
    "auth_config": {
        "type": "bearer",          # or "basic", "api_key", "vault"
        "admin_token": "secret",   # for bearer auth
        # "username": "admin",     # for basic auth
        # "password": "...",
        # "vault_path": "...",     # for Vault-managed secrets
    },
}
```

Your adapter should extract what it needs in `__init__()` and use it
in `connect()`.

## AdapterResult

All mutating methods must return an `AdapterResult`:

```python
@dataclass
class AdapterResult:
    success: bool
    resource_id: Optional[str] = None   # Gateway-side ID (set on sync_api success)
    data: Optional[dict] = None         # Additional data
    error: Optional[str] = None         # Error message (set on failure)
```

## Idempotency Contract

All operations **MUST** be idempotent:
- `sync_api()` called twice with the same `api_spec` → same result, no side effects
- `delete_api()` on a non-existent API → `success=True` (already absent)
- `upsert_policy()` with same config → no-op

## Error Handling

- **Never raise exceptions** from adapter methods. Always return
  `AdapterResult(success=False, error="...")`.
- Use `try/except` around HTTP calls and map to `AdapterResult`.
- The Sync Engine retries failed operations (up to `SYNC_ENGINE_RETRY_MAX`).

## Registration

Add your adapter to `src/adapters/registry.py`:

```python
def _register_builtin_adapters() -> None:
    from .webmethods import WebMethodsGatewayAdapter
    AdapterRegistry.register("webmethods", WebMethodsGatewayAdapter)

    from .stoa import StoaGatewayAdapter
    AdapterRegistry.register("stoa", StoaGatewayAdapter)

    # Add yours:
    from .my_gateway import MyGatewayAdapter
    AdapterRegistry.register("my_gateway", MyGatewayAdapter)
```

Then register a `GatewayInstance` with `gateway_type = "my_gateway"` via
the admin API.

## Reference Implementation

See `src/adapters/stoa/adapter.py` for a complete example:
- Uses `httpx.AsyncClient` for HTTP calls
- Implements all 6 required methods + policies
- Has dedicated `mappers.py` for request/response translation
- Full test suite in `tests/test_stoa_adapter.py`

## Mapper Functions

`mappers.py` contains translation functions between STOA's internal
format and your gateway's API. Key mappers:

| Function | Direction | Used by |
|----------|-----------|---------|
| `map_api_spec()` | STOA → Gateway | `sync_api()` |
| `map_policy()` | STOA → Gateway | `upsert_policy()` |
| `map_api_from_gateway()` | Gateway → STOA | `list_apis()` |

## Testing

Copy `tests/test_adapter.py` and fill in:
1. Mock your gateway's HTTP responses
2. Test each required method
3. Verify idempotency
4. Test error paths

Run: `pytest tests/test_my_gateway_adapter.py -v`
