---
description: Secrets management strategy — Infisical self-hosted. Consult when adding/modifying credentials or env vars.
globs: "deploy/**,k8s/**,charts/**,.env*,**/secrets*"
---

# Secrets Management

## Architecture

```
Infisical (self-hosted, source of truth — all environments)
       │
       ├── prod/     → Production secrets (Cloudflare, Hetzner, OVH)
       ├── staging/  → Staging secrets
       └── dev/      → Development secrets
```

- **Infisical** = centralized secrets manager, replaces Vault + AWS SM + ESO (decommissioned Feb 2026)
- **Self-hosted** on Hetzner (Docker Compose: infisical + postgres + redis)
- **URL**: `https://vault.gostoa.dev`
- **Admin**: `admin@gostoa.dev` (superAdmin)
- **Org ID**: `0c9506ce-668c-4ecd-8e6f-5845952eeb50`
- **Project**: `stoa-infra` (`97972ffc-990b-4d28-9c4d-0664d217f03b`)

## Secret Inventory

| Env | Path | Secret | Purpose |
|-----|------|--------|---------|
| `prod` | `/cloudflare` | `API_TOKEN` | Cloudflare DNS API (DNS Edit scope) |
| `prod` | `/hetzner` | `HCLOUD_TOKEN` | Hetzner Cloud API |
| `prod` | `/ovh` | `OVH_APPLICATION_KEY` | OVH API key |
| `prod` | `/ovh` | `OVH_APPLICATION_SECRET` | OVH API secret |
| `prod` | `/ovh` | `OVH_CONSUMER_KEY` | OVH consumer key |
| `prod` | `/ovh` | `OVH_CLOUD_PROJECT_ID` | OVH project ID |
| `prod` | `/ovh` | `OVH_OPENSTACK_PASSWORD` | OVH OpenStack password |

## Authentication

Two methods available — Machine Identity (recommended) and browser login (fallback).

### Machine Identity (Universal Auth) — Recommended

Like AWS IAM roles: Client ID + Client Secret → short-lived access token (24h), auto-renewable.

| Component | Value |
|-----------|-------|
| Identity | `stoa-cli-local` (`597c4a1e-ee10-44f7-8654-3b3cb4d01d84`) |
| Client ID | `91417b6e-d6fd-424f-a9f0-b5e3ba063e2f` (non-sensitive, in `~/.zprofile`) |
| Client Secret | Stored in macOS Keychain (`infisical-client-secret`) |
| Access Token TTL | 24h (auto-renewable, max 30 days) |
| Project Role | `admin` on `stoa-infra` |

#### Get a token

```bash
# Quick — sets INFISICAL_TOKEN in current shell
eval $(infisical-token)

# Raw token for scripts
export INFISICAL_TOKEN=$(infisical-token --raw)
```

#### How it works

1. `infisical-token` reads Client Secret from macOS Keychain
2. Calls `POST /api/v1/auth/universal-auth/login` with Client ID + Secret
3. Returns a 24h access token (no browser needed)

### Browser Login (Fallback)

```bash
infisical login --domain=https://vault.gostoa.dev/api
```

Opens browser for authentication. Session token stored in `~/.infisical/`. Expires in 10 days.

## CLI Setup

### Prerequisites

```bash
brew install infisical
```

### Project init (per-repo, one-time)

```bash
cd <repo-root>
infisical init --domain=https://vault.gostoa.dev/api
# Select project: stoa-infra
```

Creates `.infisical.json` in repo root (gitignored).

### Retrieve secrets

```bash
# Ensure you have a token first
eval $(infisical-token)

# Single secret
infisical secrets get API_TOKEN --env=prod --path=/cloudflare

# All secrets in a path
infisical secrets --env=prod --path=/cloudflare

# Inject into command
infisical run --env=prod --path=/cloudflare -- curl -H "Authorization: Bearer $API_TOKEN" ...

# Direct API call (without CLI)
curl -s "https://vault.gostoa.dev/api/v3/secrets/raw?workspaceId=97972ffc-990b-4d28-9c4d-0664d217f03b&environment=prod&secretPath=/cloudflare" \
  -H "Authorization: Bearer $INFISICAL_TOKEN"
```

### Add a new secret

```bash
infisical secrets set MY_SECRET=value --env=prod --path=/my-service
```

## Agent Checklist

When touching secrets, env vars, or credentials:

1. **Never hardcode** — use Infisical + K8s Secret reference
2. **New secret?** → Add to Infisical (correct env + path) + reference in K8s manifest
3. **K8s manifest** → Use `envFrom: secretRef` or `env.valueFrom.secretKeyRef`
4. **Non-critical secret** → Set `optional: true` on the secretRef to avoid pod crash
5. **CI/CD secret** → Add to GitHub repo/org secrets, reference as `${{ secrets.NAME }}`
6. **Local dev** → Use `infisical run` to inject, or `.env` file (gitignored)
7. **Retrieve programmatically** → `infisical secrets get <NAME> --env=prod --path=/<service>`

## Anti-Patterns

| Anti-Pattern | Why It's Wrong | Correct Approach |
|-------------|---------------|-----------------|
| Hardcoded password in code | Committed to git, visible in image layers | Infisical → K8s Secret |
| `kubectl create secret` manual | Drift, no audit trail, lost on cluster rebuild | Infisical + Helm `templates/` |
| Secret in `ConfigMap` | ConfigMaps are not encrypted at rest | Use `Secret` resource (encrypted etcd) |
| Secret in `Dockerfile ENV` | Baked into image layers, visible via `docker inspect` | Runtime env from K8s Secret |
| Secret in GitHub Actions workflow file | Committed to git | Use GitHub Secrets (`${{ secrets.X }}`) |
| `.env` file committed | Plaintext in repo history forever | `.gitignore` + `infisical run` for shared secrets |
| Token in MEMORY.md / rules | AI context = potential leak | Reference path only, never values |

## Rotation Procedures

### Rotate Application Secrets (Cloudflare, Hetzner, OVH)

```bash
# 1. Update secret value in Infisical
infisical secrets set API_TOKEN=new-value --env=prod --path=/cloudflare

# 2. Trigger pod restart to pick up new value
kubectl rollout restart deployment/<name> -n stoa-system

# 3. Verify pod is running with new secret
kubectl logs deployment/<name> -n stoa-system --tail=10
```

### Rotate Machine Identity Client Secret

```bash
# Automated: generates new secret, updates Keychain, verifies
infisical-rotate-secret

# Dry run (shows what would happen)
infisical-rotate-secret --dry-run
```

The rotation script (`~/.local/bin/infisical-rotate-secret`):
1. Authenticates with current credentials
2. Generates a new client secret via Infisical API
3. Updates macOS Keychain with new secret
4. Verifies new credentials work
5. Old secrets remain active (revoke manually in UI if needed)

**Recommended cadence**: Rotate every 90 days or after team member departure.

### Helper Scripts

| Script | Location | Purpose |
|--------|----------|---------|
| `infisical-token` | `~/.local/bin/` | Get fresh access token (24h TTL) |
| `infisical-rotate-secret` | `~/.local/bin/` | Rotate Machine Identity client secret |

Both scripts use macOS Keychain for secure secret storage — no plaintext files.

## GitHub Actions Secrets (CI/CD)

| Secret | Used By | Purpose |
|--------|---------|---------|
| `GATEWAY_API_KEYS` | control-plane-api deploy | Gateway registration auth |
| `STOA_CONTROL_PLANE_API_KEY` | stoa-gateway deploy | Gateway → API auth |
| `SONAR_TOKEN` | Quality gate jobs | SonarCloud analysis |
| `CODECOV_TOKEN` | Coverage upload | Codecov reporting |

> Note: `AWS_ROLE_ARN` removed — AWS decommissioned Feb 2026.

## Infrastructure

| Component | Detail |
|-----------|--------|
| Host | Hetzner master-1 (`46.225.112.68`) |
| Path | `/opt/infisical/` |
| Stack | `infisical:latest` + `postgres:15-alpine` + `redis:7-alpine` |
| RAM | ~800 MB |
| Ingress | Traefik (K3s), TLS via `letsencrypt-production` ClusterIssuer |
| DNS | `vault.gostoa.dev` → `46.225.112.68` |
| Backup | PostgreSQL dump (TODO: automate) |

## Auth Gotcha

- **Machine Identity tokens** (from Universal Auth login) are already org-scoped — no extra step needed
- **Browser login tokens** require org selection: the CLI handles this automatically after `infisical login`
- **API tokens are JWT**: decode with `python3 -c "import base64,json; print(json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==')))"` to check expiry/org
