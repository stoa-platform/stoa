# STOA Platform Python SDK

Auto-generated typed Python client for the STOA Control-Plane API.

## Generate

```bash
# Prerequisites
pip install openapi-python-client ruff

# Generate SDK from OpenAPI spec
./scripts/sdk/generate-python-sdk.sh

# Generate + validate imports
./scripts/sdk/generate-python-sdk.sh --validate
```

## Usage

```python
from stoa_platform_client import AuthenticatedClient

client = AuthenticatedClient(
    base_url="https://api.gostoa.dev",
    token="<your-bearer-token>",
)
```

The SDK provides:
- **Typed models** — Pydantic v2 models for all API schemas
- **Async client** — httpx-based async HTTP client
- **Type-safe API calls** — one function per endpoint with typed parameters and responses

## Source

Generated from `control-plane-api/openapi-snapshot.json` using
[openapi-python-client](https://github.com/openapi-generators/openapi-python-client).

Config: `scripts/sdk/config.yaml`
