<!-- Chargé à la demande par skills/commands. Jamais auto-chargé. -->

---
description: Infrastructure protection, password prohibition, secrets rules, and dual-repo OpSec
globs: "terraform/**,charts/**,deploy/**,*.tfvars,*.pem,*.key,.env*,.gitignore,stoa-strategy/**"
---

# Security & Infrastructure Protection

## CRITICAL — Never Do Without Explicit User Confirmation
- **NEVER run `terraform destroy`**
- **NEVER delete EKS clusters** in production
- **NEVER delete GitLab repositories** with production data
- **NEVER delete Kafka topics** with unprocessed events
- **NEVER modify Keycloak realm** without backup
- **NEVER reset or change passwords** — see Password Reset Prohibition below
- **NEVER run `rotate-secrets.sh`** or any rotation script without explicit user command

## Password Reset Prohibition (MANDATORY)

Agents MUST NEVER autonomously reset, change, or rotate any password or credential:

| Forbidden Action | Why |
|-----------------|-----|
| Keycloak `reset-password` API calls | Changes live credential, breaks all sessions |
| Running `scripts/ops/rotate-secrets.sh` | Resets passwords in Keycloak + stores in Infisical |
| `infisical secrets set` for password fields | Overwrites stored credential |
| Generating new passwords to replace existing ones | Causes credential mismatch |
| `kubectl create secret` with new password values | Overrides live K8s secrets |

**What agents CAN do**: read policy requirements, read secret paths, verify a password works (read-only), generate passwords for later human-triggered rotation, document rotation procedures.

**Password storage**: Vault (`hcvault.gostoa.dev`) is source of truth. Human runs rotation → stores in Vault → restarts pods. When agent sees "password" in a task: STOP and ask.

## Safe Operations (Always OK)
- `terraform plan`, `helm diff`, `kubectl get`, `git status/log`

## Docker Build Requirements
- **ALWAYS `--platform linux/amd64,linux/arm64`** (EKS AMD64, local Mac ARM64)

## Secrets — Never Commit
- `.env*`, `*.pem`, `*.key`, `*credentials*`, `*.tfvars`
- All secrets via Vault or K8s ExternalSecrets

## Security Tools
- **Gitleaks**: `.gitleaks.toml` with allowlist
- **Bandit**: `bandit -r src/`
- **Safety / pip-audit**: dependency scanning
- **Signed commits**: verified in CI (warning-only)

## OpSec — Dual Repo Security

| Repo | Visibility | Content |
|------|-----------|---------|
| `stoa-platform/stoa` | Public | Code, .claude/ config, sanitized plan.md |
| `PotoMitan/stoa-strategy` | Private | Client data, pricing, legal drafts, sensitive prompts |

### Never commit to public repo
- Real client names, pricing, business model details, email/MOU drafts
- Sensitive AI Factory prompts (`.claude/prompts/*.txt` — blocked by .gitignore)

### Allowed in public repo
- Code, tests, CI/CD, .claude/rules/agents/skills, legal templates with `[PLACEHOLDER]`
- `.claude/prompts/*.md` (tracked, non-sensitive)

### Code names for public references
- Use "Client A", "Partner A", "enterprise prospect" generically
- Real identities only in `stoa-strategy/clients/mapping.md`

### Verification before push
```bash
git grep -i "khalil\|lvmh\|engie\|banque" -- ':!.gitignore'
git grep -P "€\d|EUR \d" -- ':!.gitignore' ':!legal/'
```
Both must return empty.
