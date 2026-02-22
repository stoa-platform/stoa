# Runbook: Staging-to-Prod Promotion

> **Severity**: High
> **Last updated**: 2026-02-22
> **Owner**: Platform Team
> **Linear Issue**: CAB-1303

---

## Overview

The `promote-to-prod.yml` workflow promotes a dev-tagged Docker image from GHCR to the OVH MKS production cluster. It validates staging health, gates on a GitHub Environment approval, and deploys using `kubectl set image` with auto-rollback.

## Prerequisites (one-time setup)

### 1. GitHub Environment `prod`

1. Go to **Settings > Environments > New environment** → name: `prod`
2. Enable **Required reviewers** → add at least 1 team member
3. Optionally set **Wait timer** (e.g., 5 min) for extra safety

### 2. `KUBECONFIG_B64` secret (OVH MKS kubeconfig)

1. Base64-encode the OVH MKS kubeconfig: `base64 -w0 < ~/.kube/config-stoa-ovh`
2. Add as **Environment secret** scoped to `prod` (recommended) or as a repo-level secret
3. Settings > Environments > prod > Environment secrets > Add secret
4. The reusable-promote workflow declares `environment: prod` to access this secret

## How to promote

### Via GitHub Actions UI

1. Go to **Actions > Promote to Prod > Run workflow**
2. Select component: `all` (or individual component)
3. Enter SHA: the git commit SHA whose image you want to promote
4. Type `yes` in the confirm field
5. Click **Run workflow**
6. Approve the deployment when prompted (GitHub Environment gate)

### Via CLI

```bash
# Promote all components at latest main SHA
gh workflow run promote-to-prod.yml \
  --field component=all \
  --field sha=$(git rev-parse main) \
  --field confirm=yes

# Promote a single component
gh workflow run promote-to-prod.yml \
  --field component=control-plane-api \
  --field sha=abc1234 \
  --field confirm=yes

# Watch the run
gh run list --workflow=promote-to-prod.yml --limit 3
gh run watch
```

## Component mapping

| Component input | K8s deployment | GHCR image |
|----------------|----------------|------------|
| `control-plane-api` | `control-plane-api` | `ghcr.io/stoa-platform/control-plane-api` |
| `control-plane-ui` | `control-plane-ui` | `ghcr.io/stoa-platform/control-plane-ui` |
| `portal` | `stoa-portal` | `ghcr.io/stoa-platform/portal` |
| `stoa-gateway` | `stoa-gateway` | `ghcr.io/stoa-platform/stoa-gateway` |

Image tag format: `<image>:dev-<sha>` (built on push to main).

## What the workflow does

1. **Validate** — confirms `confirm=yes` and SHA is non-empty
2. **Gate** — triggers GitHub Environment approval for `prod`
3. **Per-component promote** (parallel for `all`):
   - Verify image exists in GHCR (`docker manifest inspect`)
   - Staging health pre-flight (5 endpoints)
   - Configure kubeconfig (prod)
   - Save previous image for rollback
   - `kubectl set image` + `kubectl rollout restart`
   - Auto-rollback on failure (`kubectl rollout undo`)
   - Post-deploy prod health check (5 endpoints)
4. **Notify** — Slack notification with result

## Rollback

### Automatic

The workflow auto-rolls back if `kubectl rollout status` fails within 300s.

### Manual

```bash
# Rollback a specific component
kubectl --kubeconfig ~/.kube/config-stoa-ovh \
  rollout undo deployment/control-plane-api -n stoa-system

# Verify
kubectl --kubeconfig ~/.kube/config-stoa-ovh \
  get pods -n stoa-system -l app=control-plane-api -o wide
```

## Verification

```bash
# Check pod status
kubectl --kubeconfig ~/.kube/config-stoa-ovh get pods -n stoa-system

# Check deployed image
kubectl --kubeconfig ~/.kube/config-stoa-ovh \
  get deployment -n stoa-system -o custom-columns='NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image'

# Health checks
curl -s https://api.gostoa.dev/health | jq .
curl -s https://mcp.gostoa.dev/health/ready
curl -s -o /dev/null -w "%{http_code}" https://portal.gostoa.dev
curl -s -o /dev/null -w "%{http_code}" https://console.gostoa.dev
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "Image not found in GHCR" | SHA doesn't have a built image | Verify SHA is from a merged main commit: `gh run list --branch main` |
| Staging pre-flight fails | Staging is unhealthy | Fix staging first — never promote from a broken staging |
| Rollout timeout (300s) | Pod crash, image pull error, resource limits | Check `kubectl describe pod` + `kubectl logs --previous` |
| "KUBECONFIG_B64 not set" | Secret missing from prod environment | Add it in Settings > Environments > prod |
| Approval gate timeout (60 min) | No reviewer approved | Re-run the workflow and approve within 60 min |
