# STOA Platform — Secrets Management & Rotation

## Architecture

```
Infisical (self-hosted, vault.gostoa.dev)
       │
       ├── prod/cloudflare    → Cloudflare API token
       ├── prod/hetzner       → Hetzner Cloud token
       ├── prod/ovh           → OVH API keys (5)
       └── dev/, staging/     → Environment-specific secrets
       │
       ▼
Machine Identity (Universal Auth)
  Client ID + Client Secret → 24h access token
       │
       ▼
K8s Secrets (envFrom / secretKeyRef) → Pods
```

**Infisical** replaced HashiCorp Vault + AWS Secrets Manager + External Secrets Operator (ESO) in February 2026. All references to Vault, ESO, and AWS SM in this codebase are historical.

## Infrastructure

| Component | Detail |
|-----------|--------|
| URL | `https://vault.gostoa.dev` |
| Host | Hetzner master-1 (`46.225.112.68`) |
| Path | `/opt/infisical/` |
| Stack | `infisical:latest` + `postgres:15-alpine` + `redis:7-alpine` |
| RAM | ~800 MB |
| Ingress | Traefik (K3s), TLS via `letsencrypt-production` ClusterIssuer |
| Admin | `admin@gostoa.dev` (superAdmin) |
| Org ID | `0c9506ce-668c-4ecd-8e6f-5845952eeb50` |
| Project | `stoa-infra` (`97972ffc-990b-4d28-9c4d-0664d217f03b`) |

## Secret Inventory

| Env | Path | Secret | Purpose | Rotation |
|-----|------|--------|---------|----------|
| `prod` | `/cloudflare` | `API_TOKEN` | Cloudflare DNS API (DNS Edit scope) | 90 days |
| `prod` | `/hetzner` | `HCLOUD_TOKEN` | Hetzner Cloud API | 90 days |
| `prod` | `/ovh` | `OVH_APPLICATION_KEY` | OVH API key | 90 days |
| `prod` | `/ovh` | `OVH_APPLICATION_SECRET` | OVH API secret | 90 days |
| `prod` | `/ovh` | `OVH_CONSUMER_KEY` | OVH consumer key | 90 days |
| `prod` | `/ovh` | `OVH_CLOUD_PROJECT_ID` | OVH project ID | Never (static) |
| `prod` | `/ovh` | `OVH_OPENSTACK_PASSWORD` | OVH OpenStack password | 90 days |

## Authentication

### Machine Identity (Universal Auth) — Primary Method

Like AWS IAM roles: Client ID + Client Secret → short-lived access token (24h), auto-renewable.

| Component | Value |
|-----------|-------|
| Identity | `stoa-cli-local` (`597c4a1e-ee10-44f7-8654-3b3cb4d01d84`) |
| Client ID | `91417b6e-d6fd-424f-a9f0-b5e3ba063e2f` (in `~/.zprofile`) |
| Client Secret | macOS Keychain (`infisical-client-secret`) |
| Token TTL | 24h (auto-renewable, max 30 days) |
| Project Role | `admin` on `stoa-infra` |

```bash
# Quick — sets INFISICAL_TOKEN in current shell
eval $(infisical-token)

# Raw token for scripts
export INFISICAL_TOKEN=$(infisical-token --raw)
```

### Browser Login — Fallback

```bash
infisical login --domain=https://vault.gostoa.dev/api
```

Opens browser, session stored in `~/.infisical/`, expires in 10 days.

## Retrieving Secrets

```bash
# Ensure you have a token
eval $(infisical-token)

# Single secret
infisical secrets get API_TOKEN --env=prod --path=/cloudflare

# All secrets in a path
infisical secrets --env=prod --path=/cloudflare

# Inject into a command
infisical run --env=prod --path=/cloudflare -- curl -H "Authorization: Bearer $API_TOKEN" ...

# Direct API (without CLI)
curl -s "https://vault.gostoa.dev/api/v3/secrets/raw?workspaceId=97972ffc-990b-4d28-9c4d-0664d217f03b&environment=prod&secretPath=/cloudflare" \
  -H "Authorization: Bearer $INFISICAL_TOKEN"
```

## Rotation Procedures

### Application Secrets (Cloudflare, Hetzner, OVH)

90-day rotation schedule. Steps:

```bash
# 1. Generate new credential at the provider
#    (Cloudflare dashboard, Hetzner console, OVH API panel)

# 2. Update in Infisical
eval $(infisical-token)
infisical secrets set API_TOKEN=<new-value> --env=prod --path=/cloudflare

# 3. Restart affected pods to pick up new value
kubectl rollout restart deployment/<name> -n stoa-system

# 4. Verify pod is running with new secret
kubectl logs deployment/<name> -n stoa-system --tail=10

# 5. Test the service
curl -s https://api.gostoa.dev/health
```

### Machine Identity Client Secret

Rotate every 90 days or after team member departure.

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
5. Old secrets remain active (revoke manually in Infisical UI if needed)

### Emergency Rotation

If a secret is suspected compromised:

1. **Immediately** revoke the old credential at the provider
2. Generate a new credential
3. Update Infisical: `infisical secrets set <KEY>=<new-value> --env=prod --path=/<service>`
4. Restart all affected pods: `kubectl rollout restart deployment -n stoa-system -l uses-secret=<name>`
5. Verify services are healthy
6. Document the incident in `#ops-alerts`

## K8s Secret References

### How to Reference Infisical Secrets in Deployments

```yaml
# Option A: envFrom (all secrets from a K8s Secret)
envFrom:
  - secretRef:
      name: cloudflare-credentials
      optional: true  # Non-critical secrets: set optional to avoid pod crash

# Option B: Individual env vars
env:
  - name: API_TOKEN
    valueFrom:
      secretKeyRef:
        name: cloudflare-credentials
        key: API_TOKEN
```

### Adding a New Secret

1. Add to Infisical (correct env + path): `infisical secrets set MY_SECRET=value --env=prod --path=/my-service`
2. Create or update K8s Secret manifest
3. Reference in deployment manifest (`envFrom` or `env.valueFrom.secretKeyRef`)
4. Set `optional: true` on non-critical secrets to avoid pod crash on missing secret

## CI/CD Secrets (GitHub Actions)

| Secret | Used By | Purpose |
|--------|---------|---------|
| `GATEWAY_API_KEYS` | control-plane-api deploy | Gateway registration auth |
| `STOA_CONTROL_PLANE_API_KEY` | stoa-gateway deploy | Gateway → API auth |
| `SONAR_TOKEN` | Quality gate jobs | SonarCloud analysis |
| `CODECOV_TOKEN` | Coverage upload | Codecov reporting |

CI secrets are managed in GitHub repo/org settings, not in Infisical.

## Anti-Patterns

| Anti-Pattern | Why Wrong | Correct |
|-------------|-----------|---------|
| Hardcoded password in code | Committed to git, visible in image layers | Infisical → K8s Secret |
| `kubectl create secret` manual | Drift, no audit trail, lost on rebuild | Infisical + Helm templates |
| Secret in ConfigMap | Not encrypted at rest | Use K8s `Secret` resource |
| Secret in `Dockerfile ENV` | Baked into layers, visible via `docker inspect` | Runtime env from K8s Secret |
| Secret in workflow file | Committed to git | GitHub Secrets (`${{ secrets.X }}`) |
| `.env` committed | Plaintext in repo history | `.gitignore` + `infisical run` |
| Token in MEMORY.md/rules | AI context leak risk | Reference path only, never values |

## Verification

```bash
# Check that a secret is accessible
eval $(infisical-token)
infisical secrets get API_TOKEN --env=prod --path=/cloudflare

# List all secrets in a path
infisical secrets --env=prod --path=/cloudflare

# Verify API health after rotation
curl -s https://api.gostoa.dev/health

# Check pod env vars are populated (never log the actual value)
kubectl exec -n stoa-system deploy/control-plane-api -- env | grep -c "DATABASE_URL"
```

## Helper Scripts

| Script | Location | Purpose |
|--------|----------|---------|
| `infisical-token` | `~/.local/bin/` | Get fresh access token (24h TTL) |
| `infisical-rotate-secret` | `~/.local/bin/` | Rotate Machine Identity client secret |

Both scripts use macOS Keychain for secure secret storage.

## Audit

All secret operations are logged in Infisical audit log (accessible via UI at `vault.gostoa.dev`). K8s secret mutations are visible in:
- K8s events: `kubectl get events -n stoa-system`
- Infisical audit: Settings → Audit Logs in web UI

## References

- Infisical docs: https://infisical.com/docs
- Machine Identity: https://infisical.com/docs/documentation/platform/identities/universal-auth
- `.claude/rules/secrets-management.md` — Full technical reference
