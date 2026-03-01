# Breaking Changes — STOA Platform v2.2.0

> A breaking change is any change that requires users or operators to take action.
> If you upgrade without addressing these, something **will** break.

## Severity Matrix

| Severity | Meaning | Action Required |
|----------|---------|-----------------|
| **Critical** | Service will not start or requests will fail | Must fix before upgrade |
| **High** | Feature degradation or auth failure | Must fix within 24h of upgrade |
| **Medium** | Deprecated feature removed, config key renamed | Fix at convenience, old behavior gone |
| **Low** | Default changed, opt-in required for old behavior | Awareness only |

## Breaking Changes in v2.2.0

### Critical

_None in this release._

### High

| Component | Change | Migration |
|-----------|--------|-----------|
| `gateway` | MCP protocol version bumped to `2025-11-25` | Clients using protocol `2025-03-26` will still work (negotiation supported), but new features require updated clients |
| `gateway` | OAuth DPoP sender-constraint middleware active by default | Clients not sending DPoP proofs will receive `401` on protected endpoints. Set `DPOP_REQUIRED=false` to disable |

### Medium

| Component | Change | Migration |
|-----------|--------|-----------|
| `api` | New database migrations required (billing, contracts, PII, signup tables) | Run `alembic upgrade head` before starting the new API version |
| `api` | Tenant provisioning endpoint moved from internal to `/v1/tenants/provision` | Update any scripts calling the old provisioning path |

### Low

| Component | Change | Migration |
|-----------|--------|-----------|
| `gateway` | Default tool schema validation enabled on registration | Tools with invalid JSON Schema will be rejected. Set `TOOL_SCHEMA_VALIDATION=false` to disable |
| `helm` | New `stoaGateway.llmProxy` and `stoaGateway.skills` value groups | No action needed — disabled by default. Enable explicitly in values to use |

## Deprecations (will break in next major)

| Component | What | Deprecated Since | Removal Target | Alternative |
|-----------|------|------------------|----------------|-------------|
| `gateway` | MCP protocol `2025-03-26` negotiation | v2.2.0 | v3.0.0 | Upgrade clients to `2025-11-25` |

## How to Check Your Deployment

After upgrading, verify no breaking change affects you:

```bash
# Run the verification script
./scripts/release/verify-upgrade.sh

# Or manually check each component
curl -s ${STOA_API_URL}/v1/health | jq .status
curl -s ${STOA_GATEWAY_URL}/health | jq .status
```

See [Upgrade Guide](./upgrade-guide.md) for full step-by-step upgrade procedure.
