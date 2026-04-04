# STOA Platform — Secrets Management & Rotation

## Architecture

```
HashiCorp Vault (hcvault.gostoa.dev) — Source of Truth
       │
       ├── stoa/k8s/*         → K8s Secrets (via ESO)
       ├── stoa/vps/*         → VPS service secrets (via Vault Agent)
       ├── stoa/shared/*      → Cross-cutting creds (KC, Anthropic, Slack, etc.)
       │
       ├─→ K8s (OVH Prod)
       │   └── External Secrets Operator → K8s Secrets (auto-sync, 5 min)
       │
       ├─→ VPS Services (n8n, Kong, Gravitee, webMethods)
       │   └── Vault Agent (systemd) → /opt/secrets/*.env → Docker Compose
       │
       └─→ HEGEMON Workers (5x Contabo)
           └── vault-loader.sh → env vars in memory (no disk)

Infisical (vault.gostoa.dev) — Legacy (dual-write during transition)
       │
       └── prod/*             → Historical paths, read-only after migration
```

**HashiCorp Vault** is the primary secrets backend since March 2026 (CAB-1795).
Infisical remains as dual-write target during transition. ESO syncs from Vault, not Infisical.

## Infrastructure

### Vault (Primary)

| Component | Detail |
|-----------|--------|
| URL | `https://hcvault.gostoa.dev` |
| Host | OVH spare-gra-vps (`51.255.193.129`) |
| Path | `/opt/vault/` |
| Stack | HashiCorp Vault 1.18+ (binary) + Caddy (TLS) |
| Storage | File backend (`/opt/vault/data/`) |
| Auth | AppRole (VPS agents), Kubernetes (ESO), Token (admin) |
| KV Engine | `stoa/` (KV v2, versioned) |

### Infisical (Legacy)

| Component | Detail |
|-----------|--------|
| URL | `https://vault.gostoa.dev` |
| Host | OVH infisical-vps (`213.199.45.108`) |
| Stack | `infisical:latest` + `postgres:15-alpine` + `redis:7-alpine` |
| Project | `stoa-infra` (`97972ffc-990b-4d28-9c4d-0664d217f03b`) |
| Status | **Dual-write target** — to be decommissioned after 30-day transition |

## Secret Inventory

### Tier 0 — IAM & Platform Admin

| Vault Path | Secret | Purpose | Rotation | Script |
|------------|--------|---------|----------|--------|
| `shared/keycloak` | `ADMIN_PASSWORD` | Keycloak admin (master realm) | 90 days | `rotate-secrets.sh keycloak-admin` |

### Tier 1 — Service-to-Service (K8s)

| Vault Path | Secret | Purpose | Rotation | Script |
|------------|--------|---------|----------|--------|
| `shared/keycloak/clients` | `CONTROL_PLANE_API_CLIENT_SECRET` | CP API OIDC client | 90 days | `rotate-secrets.sh oidc-clients` |
| `shared/keycloak/clients` | `MCP_GATEWAY_CLIENT_SECRET` | MCP Gateway OIDC client | 90 days | `rotate-secrets.sh oidc-clients` |
| `shared/keycloak/clients` | `OBSERVABILITY_CLIENT_SECRET` | Grafana/Prometheus OIDC | 90 days | `rotate-secrets.sh oidc-clients` |
| `k8s/opensearch` | `ADMIN_PASSWORD` | OpenSearch admin | 90 days | `rotate-secrets.sh opensearch` |

### Tier 1b — VPS Services

| Vault Path | Secret | VPS | Rotation | Script |
|------------|--------|-----|----------|--------|
| `vps/webmethods` | `ADMIN_PASSWORD` | 51.255.201.17 | 90 days | `rotate-secrets.sh webmethods-admin` |
| `vps/kong` | `KONG_ADMIN_TOKEN` | 51.83.45.13 | 90 days | `rotate-secrets.sh kong-admin` |
| `vps/gravitee` | `ADMIN_PASSWORD` | 54.36.209.237 | 90 days | `rotate-secrets.sh gravitee-admin` |
| `vps/n8n` | `POSTGRES_PASSWORD` | 51.254.139.205 | 90 days | `rotate-secrets.sh n8n-db` |
| `vps/arena` | `ADMIN_API_TOKEN` | 51.83.45.13 | 90 days | `rotate-secrets.sh arena-token` |

### Tier 2 — E2E Personas (Test Users)

| Vault Path | Secret | Purpose | Rotation | Script |
|------------|--------|---------|----------|--------|
| `k8s/e2e-personas` | `PARZIVAL_PASSWORD` | E2E persona (tenant-admin) | On demand | `rotate-secrets.sh personas` |
| `k8s/e2e-personas` | `ART3MIS_PASSWORD` | E2E persona (devops) | On demand | `rotate-secrets.sh personas` |
| `k8s/e2e-personas` | `AECH_PASSWORD` | E2E persona (viewer) | On demand | `rotate-secrets.sh personas` |
| `k8s/e2e-personas` | `SORRENTO_PASSWORD` | E2E persona (tenant-admin) | On demand | `rotate-secrets.sh personas` |
| `k8s/e2e-personas` | `I_R0K_PASSWORD` | E2E persona (viewer) | On demand | `rotate-secrets.sh personas` |
| `k8s/e2e-personas` | `ANORAK_PASSWORD` | E2E persona (cpi-admin) | On demand | `rotate-secrets.sh personas` |
| `k8s/e2e-personas` | `ALEX_PASSWORD` | E2E persona (viewer) | On demand | `rotate-secrets.sh personas` |

### Tier 3 — Infrastructure

| Vault Path | Secret | Purpose | Rotation | Script |
|------------|--------|---------|----------|--------|
| `shared/cloudflare` | `API_TOKEN` | Cloudflare DNS API (DNS Edit scope) | 90 days | Manual |
| `shared/ovh` | `OVH_APPLICATION_KEY` | OVH API key | 90 days | Manual |
| `shared/ovh` | `OVH_APPLICATION_SECRET` | OVH API secret | 90 days | Manual |
| `shared/ovh` | `OVH_CONSUMER_KEY` | OVH consumer key | 90 days | Manual |
| `shared/ovh` | `OVH_CLOUD_PROJECT_ID` | OVH project ID | Never (static) | N/A |
| `shared/ovh` | `OVH_OPENSTACK_PASSWORD` | OVH OpenStack password | 90 days | Manual |

## Authentication

### Vault Token — Primary Method

```bash
# Admin token (stored in Infisical, for human rotation ops)
export VAULT_TOKEN=<admin-token>

# Verify access
curl -sf https://hcvault.gostoa.dev/v1/stoa/data/shared/keycloak \
  -H "X-Vault-Token: $VAULT_TOKEN" | jq '.data.data | keys'
```

### Vault Auth Methods

| Method | Used By | How |
|--------|---------|-----|
| Token | Human operators (`rotate-secrets.sh`) | `VAULT_TOKEN` env var |
| AppRole | Vault Agent on VPS services | role-id + secret-id files |
| Kubernetes | External Secrets Operator (ESO) | K8s service account JWT |

### Infisical — Legacy (dual-write period)

```bash
# Still available during transition
eval $(infisical-token)
infisical secrets get API_TOKEN --env=prod --path=/cloudflare
```

## Retrieving Secrets

```bash
# From Vault (primary)
export VAULT_TOKEN=<token>

# Single secret
curl -sf https://hcvault.gostoa.dev/v1/stoa/data/vps/n8n \
  -H "X-Vault-Token: $VAULT_TOKEN" | jq '.data.data'

# List paths
curl -sf https://hcvault.gostoa.dev/v1/stoa/metadata/vps?list=true \
  -H "X-Vault-Token: $VAULT_TOKEN" | jq '.data.keys'

# From Infisical (legacy, still works)
eval $(infisical-token)
infisical secrets --env=prod --path=/cloudflare
```

## Automated Rotation Scripts

All rotation scripts are in `scripts/ops/`. They are idempotent and support `--dry-run`.

### Quick Reference

```bash
# Setup: Vault token (primary) + optional Infisical token (dual-write)
export VAULT_TOKEN=<vault-admin-token>
eval $(infisical-token)  # optional, for dual-write during transition

# === Keycloak + K8s commands ===

# Rotate Keycloak admin password
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh keycloak-admin

# Rotate E2E persona passwords (also updates GitHub Secrets)
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh personas

# Rotate OIDC client secrets (causes brief service interruption)
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh oidc-clients

# Rotate OpenSearch admin (semi-manual — stores in Vault, prints manual steps)
./scripts/ops/rotate-secrets.sh opensearch

# === VPS service commands ===

# Rotate webMethods admin password (Vault Agent auto-restarts Docker)
./scripts/ops/rotate-secrets.sh webmethods-admin

# Rotate Kong admin token
./scripts/ops/rotate-secrets.sh kong-admin

# Rotate Gravitee admin password
./scripts/ops/rotate-secrets.sh gravitee-admin

# Rotate n8n PostgreSQL password (causes brief downtime)
./scripts/ops/rotate-secrets.sh n8n-db

# Rotate VPS arena gateway token
./scripts/ops/rotate-secrets.sh arena-token

# Rotate all VPS secrets
./scripts/ops/rotate-secrets.sh all-vps

# Rotate everything (KC + K8s + VPS)
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh all

# Dry run (show what would change)
KC_ADMIN_PASSWORD=<current> ./scripts/ops/rotate-secrets.sh all --dry-run

# Skip Infisical dual-write (Vault only)
./scripts/ops/rotate-secrets.sh kong-admin --no-infisical
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

### How Vault Agent Propagates Secrets

When `rotate-secrets.sh` writes a new value to Vault, the propagation differs by target:

| Target | Mechanism | Latency | Restart |
|--------|-----------|---------|---------|
| K8s Pods | ESO polls Vault → updates K8s Secret → pod env refresh | ~5 min | Rolling restart if needed |
| VPS Docker | Vault Agent renders `.env.tpl` → `/opt/secrets/*.env` → Docker restart | ~5 min | Auto (via Agent `command`) |
| HEGEMON | vault-loader.sh reads on shell start | Next session | No (env vars in memory) |

### Application Secrets (Cloudflare, OVH)

90-day rotation schedule. Steps:

```bash
# 1. Generate new credential at the provider
#    (Cloudflare dashboard, OVH API panel)

# 2. Update in Vault (primary)
export VAULT_TOKEN=<admin-token>
curl -X POST https://hcvault.gostoa.dev/v1/stoa/data/shared/cloudflare \
  -H "X-Vault-Token: $VAULT_TOKEN" \
  -d '{"data": {"API_TOKEN": "<new-value>"}}'

# 3. ESO syncs to K8s within 5 min, or force:
kubectl annotate externalsecret -n stoa-system <name> force-sync=$(date +%s) --overwrite

# 4. Restart affected pods
kubectl rollout restart deployment/<name> -n stoa-system

# 5. Verify
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
# Check Vault is accessible
curl -sf https://hcvault.gostoa.dev/v1/sys/health | jq '.initialized, .sealed'

# Read a secret from Vault (key names only, never values in logs)
curl -sf https://hcvault.gostoa.dev/v1/stoa/data/vps/n8n \
  -H "X-Vault-Token: $VAULT_TOKEN" | jq '.data.data | keys'

# Verify ESO sync (K8s)
kubectl get externalsecrets -n stoa-system
kubectl get secrets -n stoa-system -l app.kubernetes.io/part-of=stoa-platform

# Verify Vault Agent on VPS
ssh -i ~/.ssh/id_ed25519_stoa debian@<VPS_IP> 'systemctl status vault-agent'
ssh -i ~/.ssh/id_ed25519_stoa debian@<VPS_IP> 'ls -la /opt/secrets/'

# Verify API health after rotation
curl -s https://api.gostoa.dev/health

# Check pod env vars are populated (never log the actual value)
kubectl exec -n stoa-system deploy/control-plane-api -- env | grep -c "DATABASE_URL"
```

## SSH Signing (Vault CA)

Vault's SSH secrets engine replaces static key distribution. Instead of copying public keys
to every VPS (`distribute-ssh-key.sh`), Vault signs short-lived SSH certificates.

### How It Works

```
User → vault write ssh-client-signer/sign/admin public_key=@~/.ssh/id_ed25519.pub
     → Vault signs certificate (TTL 24h)
     → ssh -o CertificateFile=~/.ssh/id_ed25519-cert.pub debian@<vps>
     → VPS sshd trusts Vault CA (TrustedUserCAKeys /etc/ssh/vault-ca.pub)
```

### Roles

| Role | TTL | Max TTL | Principals | Use Case |
|------|-----|---------|------------|----------|
| `admin` | 24h | 72h | debian, root | Human SSH access |
| `ci-deploy` | 30m | 2h | debian | CI/CD deploy scripts |

### Setup & Deploy

```bash
# 1. Configure SSH engine + CA + roles (once)
./stoa-infra:deploy/vps/vault/setup-ssh-engine.sh

# 2. Deploy CA trust to all VPS (once per fleet change)
./stoa-infra:deploy/vps/vault/deploy-ssh-trust.sh

# 3. Sign your key (daily)
./stoa-infra:deploy/vps/vault/setup-ssh-engine.sh --sign ~/.ssh/id_ed25519.pub

# 4. Verify
./stoa-infra:deploy/vps/vault/deploy-ssh-trust.sh --verify
```

**Migration**: Both mechanisms coexist. Static keys (`authorized_keys`) still work alongside
Vault-signed certificates. Remove static keys once all operators use Vault signing.

## PKI Engine (mTLS Certificates)

Vault acts as an intermediate CA for issuing mTLS certificates, used by stoa-gateway
and internal service-to-service authentication.

### CA Hierarchy

```
pki/       → Root CA (EC P-256, 10y TTL, signs intermediate only)
pki_int/   → Intermediate CA (EC P-256, 5y TTL, issues leaf certs)
```

### Roles

| Role | Domains | TTL | Use Case |
|------|---------|-----|----------|
| `gateway-mtls` | `*.gostoa.dev`, `*.svc.cluster.local` | 30d | Gateway client/server mTLS |
| `service-mesh` | `*.svc.cluster.local` | 7d | K8s internal service-to-service |

### Setup & Test

```bash
# 1. Configure PKI engines + CA hierarchy + roles (once)
./stoa-infra:deploy/vps/vault/setup-pki-engine.sh

# 2. Issue a test certificate
./stoa-infra:deploy/vps/vault/setup-pki-engine.sh --issue mcp.gostoa.dev
```

**Future**: cert-manager + Vault issuer for automatic K8s cert rotation.

## Helper Scripts

| Script | Location | Purpose |
|--------|----------|---------|
| `rotate-secrets.sh` | `scripts/ops/` | Multi-component secret rotation (KC, personas, OIDC, VPS services) |
| `configure-keycloak-policy.sh` | `scripts/ops/` | Password policy + brute-force hardening |
| `vault-agent deploy.sh` | `stoa-infra:deploy/vps/vault-agent/` | Deploy Vault Agent to VPS (systemd + templates) |
| `vault-agent deploy-hegemon.sh` | `stoa-infra:deploy/vps/vault-agent/` | Deploy vault-loader.sh to HEGEMON workers |
| `vault-config.sh` | `stoa-infra:deploy/external-secrets/` | Configure Vault K8s auth for ESO |
| `setup-ssh-engine.sh` | `stoa-infra:deploy/vps/vault/` | Configure Vault SSH CA signing engine + roles |
| `deploy-ssh-trust.sh` | `stoa-infra:deploy/vps/vault/` | Deploy SSH CA public key to all VPS |
| `setup-pki-engine.sh` | `stoa-infra:deploy/vps/vault/` | Configure Vault PKI CA hierarchy + mTLS roles |
| `infisical-token` | `~/.local/bin/` | Get Infisical access token (legacy, dual-write) |
| `infisical-rotate-secret` | `~/.local/bin/` | Rotate Infisical Machine Identity (legacy) |

`rotate-secrets.sh` writes to both Vault (primary, via HTTP API) and Infisical (legacy, via CLI/API).
Use `--no-infisical` to skip Infisical writes after transition is complete.

## Audit

All secret operations are traced in Vault's audit log. K8s and VPS mutations are visible in:
- Vault audit: `curl -sf https://hcvault.gostoa.dev/v1/sys/audit -H "X-Vault-Token: $VAULT_TOKEN"`
- K8s events: `kubectl get events -n stoa-system`
- Vault Agent logs (VPS): `journalctl -u vault-agent -f`
- Infisical audit (legacy): Settings → Audit Logs in web UI

## Rotation History

| Date | Credential | Action | PRs |
|------|-----------|--------|-----|
| 2026-03-13 | SSH + PKI engines | Vault SSH CA signing (replaces static keys) + PKI intermediate CA for mTLS | #1731 |
| 2026-03-13 | Vault migration | All secrets migrated Infisical → Vault. Rotation script extended with VPS commands | #1729 |
| 2026-03-13 | Vault Agent | Deployed on VPS services (n8n, Kong, Gravitee, webMethods). Auto-rotation via templates | #1728 |
| 2026-03-13 | ESO → Vault | External Secrets Operator pointed to Vault (was Infisical) | #1727 |
| 2026-02-15 | KC password policy | Applied NIST 800-63B + DORA (staging + prod) | #533 |
| 2026-02-15 | KC brute-force | Hardened (5 attempts, 15 min lockout, both realms) | #533 |
| 2026-02-15 | KC admin (staging) | Rotated to random 32 chars, stored in Infisical | #536 |
| 2026-02-15 | KC admin (prod) | Rotated to random 32 chars, stored in Infisical | #536 |
| 2026-02-15 | OIDC clients (3) | Verified already non-default (not `*-dev-secret`) | — |
| 2026-02-15 | E2E personas (7) | Rotated in KC + stored in Infisical + GitHub Secrets | #543 |
| 2026-02-15 | OpenSearch admin | Rotated via securityadmin.sh + stored in Infisical | — |
| 2026-02-15 | Arena VPS token | Rotated on VPS + stored in Infisical | — |

### Known Issues

- **`opensearch-dashboards`** is `publicClient: true` in production KC — no client secret needed for OIDC flow. JWKS token validation only.
- **OpenSearch securityadmin.sh** requires HTTP TLS enabled. Production runs with HTTP TLS disabled.
- **Vault Agent restart latency**: After writing to Vault, Agent polls every 5 min. For urgent rotation, SSH and restart the Agent: `sudo systemctl restart vault-agent`
- **Dual-write period**: `rotate-secrets.sh` writes to both Vault and Infisical. After 30 days of stable Vault operation, use `--no-infisical` flag exclusively.

## References

- Vault docs: https://developer.hashicorp.com/vault/docs
- Vault KV v2: https://developer.hashicorp.com/vault/docs/secrets/kv/kv-v2
- Vault Agent: https://developer.hashicorp.com/vault/docs/agent-and-proxy/agent
- Vault SSH: https://developer.hashicorp.com/vault/docs/secrets/ssh/signed-ssh-certificates
- Vault PKI: https://developer.hashicorp.com/vault/docs/secrets/pki
- ESO + Vault: https://external-secrets.io/latest/provider/hashicorp-vault/
- `.claude/rules/secrets-management.md` — Internal AI Factory reference
- `stoa-infra:deploy/vps/vault-agent/README.md` — VPS deploy guide
