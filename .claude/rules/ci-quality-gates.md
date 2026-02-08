---
description: CI quality gates — exact thresholds per component. Consult BEFORE committing.
---

# CI Quality Gates

## Full Deployment Lifecycle

A change is NOT done until the pod is updated on EKS. The complete lifecycle:

```
1. PR created          → CI (lint, test, coverage) + security-scan.yml
2. CI Green            → 3 required checks pass (License Compliance, SBOM Generation, Verify Signed Commits)
3. Merge to main       → CI re-runs on main + Docker build + ECR push
4. CI Green on main    → apply-manifest (if applicable) + deploy (rollout restart)
5. CD Green            → smoke-test (@smoke E2E) + notify
6. Pod updated         → verify: kubectl get pods -n stoa-system (new image running)
```

### What runs when

| Event | CI | Docker | Apply Manifest | Deploy | Smoke Test |
|-------|-----|--------|---------------|--------|------------|
| PR to main | Yes | No | No | No | No |
| Push to main (merge) | Yes | Yes | Yes (UI/portal) | Yes | Yes |
| workflow_dispatch | Yes | Yes | Yes (UI/portal) | Yes | Yes |

### Pipeline per component

| Component | Pipeline on merge | Deploy method |
|-----------|-------------------|---------------|
| control-plane-api | ci → integration → docker → deploy | `kubectl set image` |
| control-plane-ui | ci → docker → apply-manifest → deploy | `kubectl apply` + `set image` |
| portal | ci → docker → apply-manifest → deploy | `kubectl apply` + `set image` |
| stoa-gateway | ci → docker → deploy | `kubectl rollout restart` (ArgoCD-managed) |
| mcp-gateway | ci → docker → deploy | `kubectl set image` |

### Path triggers

Each workflow only triggers on its own component paths:
- `control-plane-api/**`, `control-plane-ui/**` + `shared/**`, `portal/**` + `shared/**`, `stoa-gateway/**`, `mcp-gateway/**`
- `security-scan.yml` runs on **ALL** PRs (no path filter)
- Docs-only changes (`*.md`, `.claude/**`) trigger security-scan but NOT component CI

### Required checks (branch protection)

3 required checks from `security-scan.yml` (runs on all PRs):
1. **License Compliance** — Trivy SPDX scan
2. **SBOM Generation** — CycloneDX + SPDX
3. **Verify Signed Commits** — signature check

### Post-merge verification

After merge, verify the full pipeline completed:
```bash
# Check CI + deploy status on main
gh run list --branch main --limit 5

# Verify pod is running new image
kubectl get pods -n stoa-system -o wide
kubectl describe deployment/<name> -n stoa-system | grep Image

# For ArgoCD-managed (stoa-gateway)
kubectl get applications -n argocd
```

## Python Thresholds

| Component | Coverage | Line Length | Ruff Rules | Notes |
|-----------|----------|-------------|------------|-------|
| control-plane-api | **53%** | 120 | E,W,F,I,B,C4,UP,ARG,SIM,S,DTZ,LOG,RUF | `--ignore tests/test_opensearch.py` for integration |
| mcp-gateway | **40%** | 100 | E,W,F,I,B,C4,UP | Simpler ruleset |

Pre-push commands:
```bash
# control-plane-api
cd control-plane-api && pytest tests/ --cov=src --cov-fail-under=53 --ignore=tests/test_opensearch.py -q

# mcp-gateway
cd mcp-gateway && pytest tests/ --cov=src --cov-fail-under=40 -q
```

## TypeScript Thresholds

| Component | ESLint max-warnings | Prettier | Build | Notes |
|-----------|-------------------|----------|-------|-------|
| control-plane-ui | **93** | blocking | `tsc -p tsconfig.app.json` | `tsconfig.app.json` excludes `**/*.test.ts(x)` |
| portal | **20** | blocking | `tsc -p tsconfig.app.json` | jsx-a11y plugin active |

Pre-push commands:
```bash
# control-plane-ui
cd control-plane-ui && npm run lint && npm run format:check && npx tsc -p tsconfig.app.json --noEmit

# portal
cd portal && npm run lint && npm run format:check && npx tsc -p tsconfig.app.json --noEmit
```

## Rust Thresholds

Zero tolerance — any warning = CI failure.

```bash
cd stoa-gateway
RUSTFLAGS=-Dwarnings cargo clippy --all-targets --all-features -- -D warnings
cargo fmt --check
cargo test --all-features
```

SAST clippy (security-scan.yml) — stricter:
```bash
cargo clippy --all-targets --all-features -- \
  -W warnings \
  -D clippy::todo \
  -D clippy::unimplemented \
  -D clippy::dbg_macro \
  -W clippy::unwrap_used \
  -W clippy::expect_used \
  -W clippy::panic
```

## Docker Build

| Setting | Value |
|---------|-------|
| Platform | `linux/amd64` (EKS target) |
| Monorepo context | `control-plane-ui`, `portal` (for `shared/` deps) |
| Registry | `848853684735.dkr.ecr.eu-west-1.amazonaws.com` |

## Security Pipeline (security-scan.yml)

| Tool | Scope | Blocking? |
|------|-------|-----------|
| Gitleaks | Entire repo, `.gitleaks.toml` config | Yes |
| Bandit | control-plane-api, mcp-gateway, MEDIUM+ severity+confidence | Yes |
| ESLint security plugin | control-plane-ui, portal (7 rules) | 2 critical rules blocking (`detect-eval-with-expression`, `detect-unsafe-regex`) |
| Clippy SAST | stoa-gateway (strict rules above) | Yes (`-D` rules) |
| Trivy | Container images, CRITICAL+HIGH, ignore-unfixed | Yes |
| Cargo audit | stoa-gateway | Non-blocking (`continue-on-error: true`) |
| pip-audit / npm audit | All components | Non-blocking |

## K8s Deploy Pipeline

Every component CI MUST have `apply-manifest` between `docker` and `deploy`:
```
ci → docker → apply-manifest → deploy (rollout restart)
```

Components with `apply-manifest`: stoa-gateway, control-plane-ui, portal.
Exception: control-plane-api (naming mismatch, standalone manifest uses `stoa-control-plane-api`).

## Common CI Failure Patterns

| Pattern | Cause | Fix |
|---------|-------|-----|
| `eslint: too many warnings (N > max)` | New warnings added | Fix warnings or raise max (ratchet only) |
| `coverage below threshold` | New code untested | Add tests or lower threshold (justified) |
| `clippy::xxx` warning | Rust lint violation | Fix the clippy issue, never suppress |
| `prettier: formatting mismatch` | Unstaged format changes | `npm run format` and commit |
| `tsc: Cannot find module` in Docker | Test imports outside build context | Ensure `tsconfig.app.json` excludes test files |
| `bddgen: missing step definitions` | Feature file without steps | Add `@wip` tag and `tags: 'not @wip'` |
| `bandit: MEDIUM severity` | Security pattern detected | Fix or add `# nosec` with justification |
| `gitleaks: secret detected` | Hardcoded secret or false positive | Remove secret or update `.gitleaks.toml` allowlist |
| `CrashLoopBackOff` after deploy | envsubst, missing env var, bad config | Check `kubectl logs --previous`, verify env vars |
| `Kyverno: blocked` | Missing `privileged: false` explicit | Add full securityContext (see k8s-deploy.md) |

## Pre-Commit Checklist by Component

### Python (control-plane-api / mcp-gateway)
```bash
ruff check . && black --check . && pytest tests/ --cov=src --cov-fail-under=<threshold> -q
```

### TypeScript (control-plane-ui / portal)
```bash
npm run lint && npm run format:check && npx tsc -p tsconfig.app.json --noEmit && npm run test -- --run
```

### Rust (stoa-gateway)
```bash
cargo fmt --check && RUSTFLAGS=-Dwarnings cargo clippy --all-targets --all-features -- -D warnings && cargo test --all-features
```
