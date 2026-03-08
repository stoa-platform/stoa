---
globs: "deploy/**,terraform/**,.infisical.json"
---

# Secrets Management

## Architecture

```
Infisical (self-hosted, source of truth — all environments)
       │
       ├── prod/     → Production secrets (Cloudflare, Contabo, Hetzner, OVH)
       ├── staging/  → Staging secrets
       └── dev/      → Development secrets

Access layers:
  Layer 1: Cloudflare Access (Service Token or email OTP)
  Layer 2: Infisical Machine Identity (Client ID + Secret → JWT)
  Layer 3: RBAC (project role: admin/member)
```

- **Infisical** = centralized secrets manager (self-hosted on Hetzner)
- **URL**: `https://vault.gostoa.dev`
- **Auth**: Machine Identity (`eval $(infisical-token)`) or browser login (`infisical login`)

## Agent Checklist

1. **Never hardcode** — use Infisical + K8s Secret reference
2. **NEVER reset/change/rotate passwords** — see `security.md` Password Reset Prohibition
3. **New secret?** → Add to Infisical + reference in K8s manifest
4. **K8s manifest** → Use `envFrom: secretRef` or `env.valueFrom.secretKeyRef`
5. **CI/CD secret** → GitHub repo/org secrets (`${{ secrets.NAME }}`)
6. **Rotation scripts are human-only** — never run by agents

## Anti-Patterns

| Anti-Pattern | Correct Approach |
|-------------|-----------------|
| Hardcoded password in code | Infisical → K8s Secret |
| `kubectl create secret` manual | Infisical + Helm `templates/` |
| Secret in `ConfigMap` | Use `Secret` resource (encrypted etcd) |
| Secret in `Dockerfile ENV` | Runtime env from K8s Secret |
| `.env` file committed | `.gitignore` + `infisical run` |
| Token in MEMORY.md / rules | Reference path only, never values |
| Agent runs rotation scripts | Human-only operation |

## Reference

Full details (secret inventory, CLI setup, rotation procedures, infra, multi-device access):
→ `docs/ai-ops/secrets-management-reference.md`
