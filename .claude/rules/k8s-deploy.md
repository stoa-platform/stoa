---
description: K8s deployment manifests and CI deploy workflows checklist
globs: "**/k8s/**,**/*-ci.yml,.github/workflows/reusable-k8s-deploy.yml"
---

# K8s Deployment Checklist

## Deployment Manifest (`k8s/deployment.yaml`)

Every deployment manifest MUST include:

### 1. Rollout Strategy (CRITICAL)
Single-replica deployments with default `maxSurge: 1, maxUnavailable: 0` will **deadlock** on resource-constrained clusters (no room to schedule the surge pod).

**Always set explicitly:**
```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 0
```

### 2. Probes must use `/health` endpoint
Use the dedicated health endpoint, not `/` (which may return SPA HTML even when backend proxies are broken).

### 3. Runtime env vars for nginx proxy backends
If the container uses `nginx.conf.template` with `proxy_pass` variables, the corresponding env vars (`LOGS_BACKEND_URL`, `GRAFANA_BACKEND_URL`, etc.) MUST be in the deployment manifest.

## CI Workflow (`*-ci.yml`)

### apply-manifest Job (CRITICAL)
The `reusable-k8s-deploy.yml` only runs `kubectl set image` + `kubectl rollout restart`. It does **NOT** apply the full deployment manifest. This means:
- New env vars are **never applied**
- Strategy changes are **never applied**
- Resource limits changes are **never applied**

**Every component CI must have an `apply-manifest` job** between `docker` and `deploy`:

```yaml
apply-manifest:
  needs: docker
  if: github.event_name == 'push' || github.event_name == 'workflow_dispatch'
  runs-on: ubuntu-latest
  permissions:
    contents: read
    id-token: write
  environment:
    name: ${{ github.event.inputs.environment || 'dev' }}
  steps:
    - uses: actions/checkout@v4
    - name: Configure AWS credentials
      uses: aws-actions/configure-aws-credentials@v4
      with:
        role-to-assume: arn:aws:iam::848853684735:role/github-actions-stoa-infra
        aws-region: eu-west-1
    - name: Update kubeconfig
      run: aws eks update-kubeconfig --name apim-dev-cluster --region eu-west-1
    - name: Apply k8s manifest
      run: |
        kubectl apply -f <component>/k8s/deployment.yaml 2>/dev/null \
          || kubectl replace --force -f <component>/k8s/deployment.yaml
```

**Gotcha**: `kubectl apply` fails with "spec.selector: field is immutable" if the deployment was originally created by Helm (different selector labels). The `replace --force` fallback deletes and recreates the deployment, which handles selector mismatches.

And the deploy job must depend on it:
```yaml
deploy:
  needs: [docker, apply-manifest]
```

## Reference: Components with apply-manifest
- `stoa-gateway` (stoa-gateway-ci.yml)
- `control-plane-ui` (control-plane-ui-ci.yml)
- `portal` (portal-ci.yml) — **TODO: verify**
- `control-plane-api` (control-plane-api-ci.yml) — **TODO: verify**
