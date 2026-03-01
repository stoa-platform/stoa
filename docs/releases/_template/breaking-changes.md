# Breaking Changes — STOA Platform vX.Y.Z

> A breaking change is any change that requires users or operators to take action.
> If you upgrade without addressing these, something **will** break.

## Severity Matrix

| Severity | Meaning | Action Required |
|----------|---------|-----------------|
| **Critical** | Service will not start or requests will fail | Must fix before upgrade |
| **High** | Feature degradation or auth failure | Must fix within 24h of upgrade |
| **Medium** | Deprecated feature removed, config key renamed | Fix at convenience, old behavior gone |
| **Low** | Default changed, opt-in required for old behavior | Awareness only |

## Breaking Changes in vX.Y.Z

### Critical

<!-- None expected for minor releases. List here if any. -->

_None in this release._

### High

| Component | Change | Migration |
|-----------|--------|-----------|
| `api` | Description of what changed | `command or config change to apply` |

### Medium

| Component | Change | Migration |
|-----------|--------|-----------|
| `gateway` | Description | Steps to migrate |

### Low

| Component | Change | Migration |
|-----------|--------|-----------|
| `helm` | Default for `key` changed from X to Y | Set `key: X` in values to keep old behavior |

## Deprecations (will break in next major)

| Component | What | Deprecated Since | Removal Target | Alternative |
|-----------|------|------------------|----------------|-------------|
| `api` | `GET /v1/old-endpoint` | v2.1.0 | v3.0.0 | `GET /v1/new-endpoint` |

## How to Check Your Deployment

After upgrading, verify no breaking change affects you:

```bash
# Run the verification script
./scripts/release/verify-upgrade.sh

# Or manually check each component
curl -s https://${STOA_API_URL}/v1/health | jq .status
curl -s https://${STOA_GATEWAY_URL}/health | jq .status
```

See [Upgrade Guide](./upgrade-guide.md) for full step-by-step upgrade procedure.
