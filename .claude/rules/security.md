---
description: Infrastructure protection and security rules
globs: "terraform/**,charts/**,deploy/**,*.tfvars,*.pem,*.key,.env*"
---

# Security & Infrastructure Protection

## CRITICAL — Never Do Without Explicit User Confirmation
- **NEVER run `terraform destroy`**
- **NEVER delete EKS clusters** in production
- **NEVER delete GitLab repositories** with production data
- **NEVER delete Kafka topics** with unprocessed events
- **NEVER modify Keycloak realm** without backup
- **NEVER reset or change passwords** (Keycloak users, admin, OIDC clients, OpenSearch, arena tokens) — see Password Reset Prohibition below
- **NEVER run `rotate-secrets.sh`** or any rotation script without explicit user command

## Password Reset Prohibition (MANDATORY)

Agents MUST NEVER autonomously reset, change, or rotate any password or credential. This includes:

| Forbidden Action | Why |
|-----------------|-----|
| Keycloak `reset-password` API calls | Changes live credential, breaks all sessions |
| Running `scripts/ops/rotate-secrets.sh` | Resets passwords in Keycloak + stores in Infisical |
| Running `infisical-rotate-secret` | Rotates Machine Identity client secret |
| `infisical secrets set` for password fields | Overwrites stored credential |
| Generating new passwords to replace existing ones | Causes credential mismatch across services |
| `kubectl create secret` with new password values | Overrides live K8s secrets |

### What Agents CAN Do (read-only)
- **Read** password policy requirements (e.g., "must have uppercase, digit, special char")
- **Read** secret paths from Infisical (to reference in code/manifests)
- **Verify** a password works (e.g., `curl` to get a KC token — read-only validation)
- **Generate** passwords in code that will be used by the rotation script later (human-triggered)
- **Document** rotation procedures in runbooks

### Password Storage Strategy — Awareness
- **Source of truth**: Infisical (`vault.gostoa.dev`) — all credentials live here
- **Flow**: Human runs rotation script → script changes password in service → stores new value in Infisical → human restarts dependent pods
- **Never skip Infisical**: if a password is changed in a service but NOT stored in Infisical, the credential is effectively lost
- **Coordination required**: password changes affect multiple services (KC → API → Gateway → E2E). An uncoordinated change breaks the chain
- **When agent sees "password" in a task**: STOP and ask the user. Do not attempt to change it, even if a script exists to do so

## Safe Operations (Always OK)
- `terraform plan` — run before apply
- `helm diff` — preview changes
- `kubectl get` — read-only
- `git status/log` — read operations

## Docker Build Requirements
- **ALWAYS build multi-arch images**: `--platform linux/amd64,linux/arm64`
- EKS runs AMD64, local Mac is ARM64
- Example: `docker buildx build --platform linux/amd64,linux/arm64 -t <image> --push .`

## Secrets — Never Commit
- `.env*`, `*.pem`, `*.key`, `*credentials*`, `*.tfvars`
- All secrets via Vault or AWS Secrets Manager

## Security Tools
- **Gitleaks**: `.gitleaks.toml` with allowlist
- **Bandit**: `bandit -r src/`
- **Safety / pip-audit**: dependency scanning
- **Signed commits**: verified in CI (warning-only)
