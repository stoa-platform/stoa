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
- **Org ID**: `d8d519fa-0e82-47e7-b914-bab341c9bbf2`
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

## CLI Setup

### Prerequisites

```bash
brew install infisical
```

### One-time login

```bash
infisical login --domain=https://vault.gostoa.dev/api
```

Opens browser for authentication. Session token stored in `~/.infisical/`.

### Project init (per-repo, one-time)

```bash
cd <repo-root>
infisical init --domain=https://vault.gostoa.dev/api
# Select project: stoa-infra
```

Creates `.infisical.json` in repo root (gitignored).

### Retrieve secrets

```bash
# Single secret
infisical secrets get API_TOKEN --env=prod --path=/cloudflare

# All secrets in a path
infisical secrets --env=prod --path=/cloudflare

# Inject into command
infisical run --env=prod --path=/cloudflare -- curl -H "Authorization: Bearer $API_TOKEN" ...
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

## Rotation Procedure

```
1. Update secret value in Infisical (UI or CLI)
   infisical secrets set API_TOKEN=new-value --env=prod --path=/cloudflare
2. Trigger pod restart to pick up new value:
   kubectl rollout restart deployment/<name> -n stoa-system
3. Verify pod is running with new secret:
   kubectl logs deployment/<name> -n stoa-system --tail=10
```

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

Infisical API requires org-scoped token:
```bash
# After initial auth, select organization:
POST /api/v3/auth/select-organization
Body: { "organizationId": "d8d519fa-0e82-47e7-b914-bab341c9bbf2" }
```

The CLI handles this automatically after `infisical login`.
