---
globs: "deploy/**,terraform/**,.infisical.json,**/vault*"
---

# Secrets Management

## Architecture

```
HashiCorp Vault (hcvault.gostoa.dev) — Source of Truth (CAB-1795)
    │
    ├── K8s (OVH Prod)
    │   └── External Secrets Operator → ClusterSecretStore → ExternalSecret CRs
    │
    ├── VPS Services
    │   └── Vault Agent (systemd) → /opt/secrets/*.env → Docker Compose
    │
    └── Rotation
        └── rotate-secrets.sh (human-only) → Vault KV v2

Infisical (vault.gostoa.dev) — Legacy, read-only reference during transition
```

- **Vault** = primary secrets manager (self-hosted on spare-gra-vps)
- **URL**: `https://hcvault.gostoa.dev`
- **Auth**: AppRole (VPS agents), Kubernetes (ESO), Token (admin/human)
- **Infisical** = legacy, read-only reference. URL: `https://vault.gostoa.dev`

## Agent Checklist

1. **Never hardcode** — use Vault + K8s Secret reference
2. **NEVER reset/change/rotate passwords** — see `security.md` Password Reset Prohibition
3. **New secret?** → Add to Vault (`stoa/` KV v2) + reference in K8s manifest
4. **K8s manifest** → Use `envFrom: secretRef` or `env.valueFrom.secretKeyRef`
5. **CI/CD secret** → GitHub repo/org secrets (`${{ secrets.NAME }}`)
6. **Rotation scripts are human-only** — never run by agents
7. **Vault paths**: `stoa/k8s/*` (K8s), `stoa/vps/*` (VPS), `stoa/shared/*` (cross-service)

## K8s Secret Manifests in GitOps

**NEVER commit real credential values in `kind: Secret` manifests.** This is a GitOps repo — secrets in YAML are visible in git history forever.

| Allowed | Forbidden |
|---------|-----------|
| `REPLACE_FROM_VAULT` placeholder | Real password values in stringData |
| `${VAR}` env substitution | bcrypt hashes in config files |
| `CHANGE_ME` placeholder | Plaintext password in YAML comment |
| ExternalSecret CRD referencing Vault | `stringData` with real values |

**Enforcement** (3 layers):
1. **gitleaks** — custom rules `k8s-secret-password`, `password-in-comment`, `bcrypt-hash` in `.gitleaks.toml`
2. **PreToolUse hook** — `pre-edit-no-k8s-secrets.sh` blocks AI Factory from writing secrets in YAML files
3. **CI** — `security-scan.yml` runs gitleaks on every PR

## Anti-Patterns

| Anti-Pattern | Correct Approach |
|-------------|-----------------|
| Hardcoded password in code | Vault → ExternalSecret → K8s Secret |
| Real password in `stringData:` | `REPLACE_FROM_VAULT` placeholder |
| Password in YAML comment | `# Credential managed via Vault stoa/path` |
| bcrypt hash in config file | `REPLACE_WITH_BCRYPT_HASH` placeholder |
| `kubectl create secret` manual | ExternalSecret CR (ESO → Vault) |
| Secret in `ConfigMap` | Use `Secret` resource (encrypted etcd) |
| Secret in `Dockerfile ENV` | Runtime env from K8s Secret |
| `.env` file committed | `.gitignore` + Vault Agent templates |
| Plaintext `.env` on VPS | Vault Agent → `/opt/secrets/*.env` (0600) |
| Token in MEMORY.md / rules | Reference path only, never values |
| Agent runs rotation scripts | Human-only operation |

## Key Files

| File | Purpose |
|------|---------|
| `deploy/vps/vault/` | Vault server deployment (docker-compose, config, policies) |
| `deploy/external-secrets/` | ESO SecretStore + ExternalSecret CRs |
| `scripts/ops/rotate-secrets.sh` | Credential rotation (human-only) |
| `scripts/ops/migrate-to-vault.sh` | Infisical → Vault migration |

## Reference

Full details (secret inventory, CLI setup, rotation procedures, infra, multi-device access):
→ `docs/ai-ops/secrets-management-reference.md`
