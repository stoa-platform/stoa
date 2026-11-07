# Secrets Management — Full Reference

> Extracted from `.claude/rules/secrets-management.md` (rules diet). Essential rules remain in the rule file.
> Infisical was retired by ADR-075 (2026-11-07): tooling secrets now live in OpenBao.

## Secret Inventory

Former Infisical folders map to OpenBao paths of the same name under
`secret/stoa/tooling/` (ADR-075). The owner decides which ones to populate (put-secret).

| OpenBao path | Field | Purpose |
|--------------|-------|---------|
| `cloudflare` | `API_TOKEN` | Cloudflare DNS API (DNS Edit scope) |
| `cloudflare` | `CF_ACCESS_CLIENT_ID` | Cloudflare Access Service Token ID |
| `cloudflare` | `CF_ACCESS_CLIENT_SECRET` | Cloudflare Access Service Token Secret |
| `contabo` | `VPS_ROOT_PASSWORD` | Root password for 5 HEGEMON VPS |
| `hetzner` | `HCLOUD_TOKEN` | Hetzner Cloud API (decommissioned 2026-03, remove after cleanup) |
| `ovh` | `OVH_APPLICATION_KEY` | OVH API key |
| `ovh` | `OVH_APPLICATION_SECRET` | OVH API secret |
| `ovh` | `OVH_CONSUMER_KEY` | OVH consumer key |
| `ovh` | `OVH_CLOUD_PROJECT_ID` | OVH project ID |
| `ovh` | `OVH_OPENSTACK_PASSWORD` | OVH OpenStack password |
| `ovh` | `VPS_STOA_PASSWORD` | Root password for OVH VPS fleet |

## Tooling Access (OpenBao)

| Component | Value |
|-----------|-------|
| Address | `https://127.0.0.1:18200` through the SSH tunnel (`STOA_OPENBAO_ADDR`) |
| CA | `~/.config/stoa/openbao-ca.pem` (`STOA_OPENBAO_CACERT`) |
| Token | Read-only, periodic (768h): macOS Keychain service `stoa-openbao`, account `tooling`; Linux `~/.config/stoa/openbao-tooling-token`; or `STOA_OPENBAO_TOKEN` |
| Policy | read `secret/data/stoa/tooling/*`, read/list `secret/metadata/stoa/tooling/*` |
| Renewal | `renew-self` at most once a day, done by the helper |

```bash
# In a script: an env var already set always wins
source scripts/lib/stoa-secret.sh
[ -n "${CF_API_TOKEN:-}" ] || CF_API_TOKEN=$(stoa_secret cloudflare API_TOKEN) || CF_API_TOKEN=""

# From a shell
scripts/lib/stoa-secret.sh cloudflare API_TOKEN
```

Writes go through the owner's put-secret tool only; tooling never writes to OpenBao.

## Rotation Procedures

### Application Secrets

```bash
# Store the new value with put-secret (e.g. OpenBao cloudflare / API_TOKEN), then:
kubectl rollout restart deployment/<name> -n stoa-system
kubectl logs deployment/<name> -n stoa-system --tail=10
```

### Tooling Token

The helper renews the periodic tooling token at most once a day. If it expires
anyway (reads fail with HTTP 403), the owner issues a new one and stores it in
the Keychain item or token file above.

## Vault KV v2 Paths (ESO-Synced)

| Vault Path | K8s Secret | Component | Keys |
|---|---|---|---|
| `stoa/k8s/gateway` | `stoa-gateway-secrets` | stoa-gateway | STOA_CONTROL_PLANE_API_KEY, STOA_KEYCLOAK_CLIENT_SECRET |
| `stoa/k8s/opensearch` | `stoa-opensearch-secret` | control-plane-api | 6 OpenSearch keys |
| `stoa/k8s/anthropic` | `anthropic-api-key` | control-plane-api | ANTHROPIC_API_KEY |
| `stoa/dev/env` | `postgresql-credentials` | control-plane-api | DEV_PG_* (5 keys) |

## GitHub Actions Secrets

| Secret | Used By | Purpose |
|--------|---------|---------|
| `GATEWAY_API_KEYS` | control-plane-api deploy | Gateway registration auth |
| `STOA_CONTROL_PLANE_API_KEY` | stoa-gateway deploy | Gateway → API auth |
| `SONAR_TOKEN` | Quality gate jobs | SonarCloud analysis |
| `CODECOV_TOKEN` | Coverage upload | Codecov reporting |

## Multi-Device Access

See `docs/runbooks/multi-device-access.md` for the full runbook.

| Layer | Per-Device | Shared |
|-------|-----------|--------|
| SSH | Ed25519 key (`id_ed25519_stoa_<device>`) | — |
| OpenBao | Read-only tooling token (Keychain or token file) | — |

## Infrastructure

OpenBao runs on a dedicated VM managed by the platform owner and is reachable only
through an SSH tunnel. The Infisical host, its Caddy ingress and the Cloudflare
Access application in front of it were retired with ADR-075.
