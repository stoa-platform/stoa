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
