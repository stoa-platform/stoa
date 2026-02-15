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

### Tier 0 — IAM & Platform Admin

| Env | Path | Secret | Purpose | Rotation | Script |
|-----|------|--------|---------|----------|--------|
| `prod` | `/keycloak` | `ADMIN_PASSWORD` | Keycloak admin (master realm) | 90 days | `rotate-secrets.sh keycloak-admin` |

### Tier 1 — Service-to-Service

| Env | Path | Secret | Purpose | Rotation | Script |
|-----|------|--------|---------|----------|--------|
| `prod` | `/keycloak/clients` | `CONTROL_PLANE_API_CLIENT_SECRET` | CP API OIDC client | 90 days | `rotate-secrets.sh oidc-clients` |
| `prod` | `/keycloak/clients` | `MCP_GATEWAY_CLIENT_SECRET` | MCP Gateway OIDC client | 90 days | `rotate-secrets.sh oidc-clients` |
| `prod` | `/keycloak/clients` | `OPENSEARCH_DASHBOARDS_CLIENT_SECRET` | OpenSearch Dashboards OIDC | N/A (public client) | N/A |
| `prod` | `/keycloak/clients` | `OBSERVABILITY_CLIENT_SECRET` | Grafana/Prometheus OIDC | 90 days | `rotate-secrets.sh oidc-clients` |
| `prod` | `/opensearch` | `ADMIN_PASSWORD` | OpenSearch admin | 90 days | `rotate-secrets.sh opensearch` |
| `prod` | `/gateway/arena` | `ADMIN_API_TOKEN` | VPS Arena gateway admin | 90 days | `rotate-secrets.sh arena-token` |

### Tier 2 — E2E Personas (Test Users)

| Env | Path | Secret | Purpose | Rotation | Script |
|-----|------|--------|---------|----------|--------|
| `prod` | `/e2e-personas` | `PARZIVAL_PASSWORD` | E2E persona (tenant-admin) | On demand | `rotate-secrets.sh personas` |
| `prod` | `/e2e-personas` | `ART3MIS_PASSWORD` | E2E persona (devops) | On demand | `rotate-secrets.sh personas` |
| `prod` | `/e2e-personas` | `AECH_PASSWORD` | E2E persona (viewer) | On demand | `rotate-secrets.sh personas` |
| `prod` | `/e2e-personas` | `SORRENTO_PASSWORD` | E2E persona (tenant-admin) | On demand | `rotate-secrets.sh personas` |
| `prod` | `/e2e-personas` | `I_R0K_PASSWORD` | E2E persona (viewer) | On demand | `rotate-secrets.sh personas` |
| `prod` | `/e2e-personas` | `ANORAK_PASSWORD` | E2E persona (cpi-admin) | On demand | `rotate-secrets.sh personas` |
| `prod` | `/e2e-personas` | `ALEX_PASSWORD` | E2E persona (viewer) | On demand | `rotate-secrets.sh personas` |

### Tier 3 — Infrastructure

| Env | Path | Secret | Purpose | Rotation | Script |
|-----|------|--------|---------|----------|--------|
| `prod` | `/cloudflare` | `API_TOKEN` | Cloudflare DNS API (DNS Edit scope) | 90 days | Manual |
| `prod` | `/hetzner` | `HCLOUD_TOKEN` | Hetzner Cloud API | 90 days | Manual |
| `prod` | `/ovh` | `OVH_APPLICATION_KEY` | OVH API key | 90 days | Manual |
| `prod` | `/ovh` | `OVH_APPLICATION_SECRET` | OVH API secret | 90 days | Manual |
| `prod` | `/ovh` | `OVH_CONSUMER_KEY` | OVH consumer key | 90 days | Manual |
| `prod` | `/ovh` | `OVH_CLOUD_PROJECT_ID` | OVH project ID | Never (static) | N/A |
| `prod` | `/ovh` | `OVH_OPENSTACK_PASSWORD` | OVH OpenStack password | 90 days | Manual |

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

## Automated Rotation Scripts

All rotation scripts are in `scripts/ops/`. They are idempotent and support `--dry-run`.

### Quick Reference

```bash
# Setup: get Infisical token first
eval $(infisical-token)

# Rotate Keycloak admin password
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh keycloak-admin

# Rotate E2E persona passwords (also updates GitHub Secrets)
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh personas

# Rotate OIDC client secrets (causes brief service interruption)
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh oidc-clients

# Rotate OpenSearch admin (semi-manual — stores in Infisical, prints manual steps)
./scripts/ops/rotate-secrets.sh opensearch

# Rotate VPS arena gateway token (stores in Infisical, prints manual steps)
./scripts/ops/rotate-secrets.sh arena-token

# Rotate everything
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh all

# Dry run (show what would change)
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh all --dry-run
```

### Keycloak Password Policy

Configured via `scripts/ops/configure-keycloak-policy.sh`. Policy (NIST 800-63B + DORA Art.9):

| Parameter | Value | Justification |
|-----------|-------|---------------|
| `length` | 12 | NIST SP 800-63B minimum |
| `upperCase/lowerCase/digits/specialChars` | 1 each | DORA "strong authentication" |
| `notUsername` | yes | Prevent trivial passwords |
| `passwordHistory` | 5 | DORA "credential rotation" |
| `maxLength` | 128 | Support passphrases |
| No forced expiration | - | NIST 800-63B recommends against it |

Brute-force protection: 5 attempts, 15-min progressive lockout, 1-hour max.

```bash
KC_ADMIN_PASSWORD=<current> ./scripts/ops/configure-keycloak-policy.sh
KC_ADMIN_PASSWORD=<current> ./scripts/ops/configure-keycloak-policy.sh --dry-run
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
| `rotate-secrets.sh` | `scripts/ops/` | Multi-component secret rotation (KC, personas, OIDC, OS, arena) |
| `configure-keycloak-policy.sh` | `scripts/ops/` | Password policy + brute-force hardening |

`infisical-*` scripts use macOS Keychain. `scripts/ops/` scripts use Infisical API + Keycloak Admin API.

## Audit

All secret operations are logged in Infisical audit log (accessible via UI at `vault.gostoa.dev`). K8s secret mutations are visible in:
- K8s events: `kubectl get events -n stoa-system`
- Infisical audit: Settings → Audit Logs in web UI

## Rotation History

| Date | Credential | Action | PRs |
|------|-----------|--------|-----|
| 2026-02-15 | KC password policy | Applied NIST 800-63B + DORA (staging + prod) | #533 |
| 2026-02-15 | KC brute-force | Hardened (5 attempts, 15 min lockout, both realms) | #533 |
| 2026-02-15 | KC admin (staging) | Rotated to random 32 chars, stored in Infisical | #536 |
| 2026-02-15 | KC admin (prod) | Rotated to random 32 chars, stored in Infisical | #536 |
| 2026-02-15 | OIDC clients (3) | Verified already non-default (not `*-dev-secret`) | — |
| 2026-02-15 | OIDC opensearch-dashboards | Public client — no secret to rotate | — |
| 2026-02-15 | E2E personas (7) | Rotated in KC + stored in Infisical + GitHub Secrets | #543 |
| 2026-02-15 | OpenSearch admin | Rotated via securityadmin.sh + stored in Infisical | — |

### Known Issues

- **`opensearch-dashboards`** is `publicClient: true` in production KC — no client secret needed for OIDC flow. JWKS token validation only.
- **OpenSearch securityadmin.sh** requires HTTP TLS enabled. Production runs with HTTP TLS disabled. Procedure: temporarily enable TLS, run securityadmin, revert, restart.
- **Infisical self-hosted v3 API** requires encrypted fields for REST API writes. Use `infisical secrets set` CLI instead (handles encryption transparently). PR #543 fixed `store_infisical()`.
- **Arena VPS token** (`arena-admin-token-2026`) still hardcoded on VPS. Requires SSH access to rotate.

## References

- Infisical docs: https://infisical.com/docs
- Machine Identity: https://infisical.com/docs/documentation/platform/identities/universal-auth
- `.claude/rules/secrets-management.md` — Full technical reference
