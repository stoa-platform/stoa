# Secrets Management — Full Reference

> Extracted from `.claude/rules/secrets-management.md` (rules diet). Essential rules remain in the rule file.

## Secret Inventory

| Env | Path | Secret | Purpose |
|-----|------|--------|---------|
| `prod` | `/cloudflare` | `API_TOKEN` | Cloudflare DNS API (DNS Edit scope) |
| `prod` | `/cloudflare` | `CF_ACCESS_CLIENT_ID` | Cloudflare Access Service Token ID |
| `prod` | `/cloudflare` | `CF_ACCESS_CLIENT_SECRET` | Cloudflare Access Service Token Secret |
| `prod` | `/contabo` | `VPS_ROOT_PASSWORD` | Root password for 5 HEGEMON VPS |
| `prod` | `/hetzner` | `HCLOUD_TOKEN` | Hetzner Cloud API |
| `prod` | `/ovh` | `OVH_APPLICATION_KEY` | OVH API key |
| `prod` | `/ovh` | `OVH_APPLICATION_SECRET` | OVH API secret |
| `prod` | `/ovh` | `OVH_CONSUMER_KEY` | OVH consumer key |
| `prod` | `/ovh` | `OVH_CLOUD_PROJECT_ID` | OVH project ID |
| `prod` | `/ovh` | `OVH_OPENSTACK_PASSWORD` | OVH OpenStack password |
| `prod` | `/ovh` | `VPS_STOA_PASSWORD` | Root password for OVH VPS fleet |

## Authentication

### Machine Identity (Universal Auth)

| Component | Value |
|-----------|-------|
| Identity | `stoa-cli-local` |
| Client ID | In `~/.zprofile` |
| Client Secret | macOS Keychain (`infisical-client-secret`) |
| Access Token TTL | 24h (auto-renewable, max 30 days) |

```bash
# Quick — sets INFISICAL_TOKEN in current shell
eval $(infisical-token)

# Raw token for scripts
export INFISICAL_TOKEN=$(infisical-token --raw)
```

### Browser Login (Fallback)

```bash
infisical login --domain=https://vault.gostoa.dev/api
```

## CLI Setup

```bash
brew install infisical
cd <repo-root> && infisical init --domain=https://vault.gostoa.dev/api

# Retrieve
eval $(infisical-token)
infisical secrets get API_TOKEN --env=prod --path=/cloudflare
infisical secrets --env=prod --path=/cloudflare
infisical run --env=prod --path=/cloudflare -- <command>

# Add
infisical secrets set MY_SECRET=value --env=prod --path=/my-service
```

## Rotation Procedures

### Application Secrets

```bash
infisical secrets set API_TOKEN=new-value --env=prod --path=/cloudflare
kubectl rollout restart deployment/<name> -n stoa-system
kubectl logs deployment/<name> -n stoa-system --tail=10
```

### Machine Identity Client Secret

```bash
infisical-rotate-secret           # Automated
infisical-rotate-secret --dry-run # Preview
```

Cadence: every 90 days or after team member departure.

## GitHub Actions Secrets

| Secret | Used By | Purpose |
|--------|---------|---------|
| `GATEWAY_API_KEYS` | control-plane-api deploy | Gateway registration auth |
| `STOA_CONTROL_PLANE_API_KEY` | stoa-gateway deploy | Gateway → API auth |
| `SONAR_TOKEN` | Quality gate jobs | SonarCloud analysis |
| `CODECOV_TOKEN` | Coverage upload | Codecov reporting |

## Cloudflare Access

`vault.gostoa.dev` protected by Cloudflare Access (Zero Trust).

| Variable | Where to Set |
|----------|-------------|
| `CF_ACCESS_CLIENT_ID` | `~/.zprofile` + VPS `~/.env.hegemon` |
| `CF_ACCESS_CLIENT_SECRET` | `~/.zprofile` + VPS `~/.env.hegemon` |

Setup: `./scripts/ops/setup-cloudflare-access.sh`

## Multi-Device Access

See `docs/runbooks/multi-device-access.md` for the full runbook.

| Layer | Per-Device | Shared |
|-------|-----------|--------|
| SSH | Ed25519 key (`id_ed25519_stoa_<device>`) | — |
| Infisical | Machine Identity (`stoa-cli-<device>`) | — |
| CF Access | — | Service Token (`stoa-infisical-cli`) |

## Infrastructure

| Component | Detail |
|-----------|--------|
| Host | Hetzner master-1 |
| Path | `/opt/infisical/` |
| Stack | `infisical:latest` + `postgres:15-alpine` + `redis:7-alpine` |
| Ingress | Traefik (K3s), TLS via `letsencrypt-production` |
| DNS | `vault.gostoa.dev` |
