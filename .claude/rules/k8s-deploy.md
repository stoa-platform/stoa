---
description: K8s deployment manifests and CI deploy workflows checklist
globs: "**/k8s/**,**/*-ci.yml,.github/workflows/reusable-k8s-deploy.yml"
---

# K8s Deployment Checklist

## Deployment Manifest (`k8s/deployment.yaml`)

Every deployment manifest MUST include:

### 1. Rollout Strategy (CRITICAL)
Single-replica deployments with default `maxSurge: 1, maxUnavailable: 0` will **deadlock** on resource-constrained clusters.

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 0
```

### 2. Kyverno `restrict-privileged` — EXPLICIT `privileged: false` (CRITICAL)
The cluster has a Kyverno `restrict-privileged` policy in **Enforce** mode. Every container MUST have `securityContext.privileged: false` **explicitly set**. Omitting it (even if the default is false) causes Kyverno to **block pod creation**.

```yaml
securityContext:
  privileged: false          # REQUIRED — Kyverno Enforce policy
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
  seccompProfile:
    type: RuntimeDefault
```

### 3. Nginx containers — NO `readOnlyRootFilesystem: true`
nginx-unprivileged requires writable paths beyond `/var/cache/nginx`, `/var/run`, `/tmp`:
- `/etc/nginx/conf.d/` — envsubst writes processed templates here at startup
- Other internal nginx paths

Use `readOnlyRootFilesystem: false` for nginx containers, or mount ALL writable paths as emptyDir.

### 4. Nginx proxy_pass — NEVER use static hostnames
Static `proxy_pass http://hostname:port/` hostnames are resolved at nginx startup. If the backend DNS doesn't resolve (e.g., service not yet created, wrong name), **nginx will crash immediately**.

**Always use variables** for proxy_pass backends:
```nginx
set $api_backend "${API_BACKEND_URL}";
location /api/ {
    proxy_pass $api_backend;   # Resolved at request time, not startup
}
```

### 5. K8s service names — check ACTUAL service name
The standalone k8s manifest may use a different service name than the Helm chart:
- Helm: `stoa-control-plane-api` (prefixed)
- Standalone: `control-plane-api` (no prefix)

Always verify: `kubectl get svc -n stoa-system`

### 6. Probes must use `/health` endpoint
Use the dedicated health endpoint, not `/` (which may return SPA HTML even when backend proxies are broken).

### 7. Runtime env vars for nginx proxy backends
If the container uses `nginx.conf.template` with `proxy_pass` variables, the corresponding env vars MUST be in the deployment manifest AND in the Dockerfile's `NGINX_ENVSUBST_FILTER`.

### 8. Nginx envsubst templates — use `$$` prefix for nginx variables (CRITICAL)
Do NOT use `NGINX_ENVSUBST_FILTER` — the latest nginx Docker image's entrypoint uses awk to process it as a regex, and `${VAR}` syntax breaks awk. Also, Docker's `ENV` expands `${VAR}` at build time.

**Instead, use `$$` prefix** for all nginx variables in the template (envsubst converts `$$` → `$`):
```nginx
set $$api_backend "${API_BACKEND_URL}";     # envsubst: $$api_backend → $api_backend
proxy_pass $$api_backend;                    # envsubst: leaves $api_backend
proxy_set_header Host $$http_host;           # envsubst: $$http_host → $http_host
resolver ${NGINX_LOCAL_RESOLVERS} valid=30s; # envsubst: substitutes the IP
```
Use `NGINX_LOCAL_RESOLVERS` (built-in from nginx image's `15-local-resolvers.envsh`) instead of a custom DNS resolver script.

## CI Workflow (`*-ci.yml`)

### apply-manifest Job (CRITICAL)
`reusable-k8s-deploy.yml` only runs `kubectl set image` + `kubectl rollout restart`. It does **NOT** apply the full deployment manifest.

Every component CI must have an `apply-manifest` job between `docker` and `deploy`:

```yaml
- name: Apply k8s manifest
  run: |
    kubectl apply -f <component>/k8s/deployment.yaml 2>&1 || {
      echo "Apply failed (likely immutable selector). Deleting and recreating..."
      kubectl delete deployment <name> -n stoa-system --ignore-not-found
      kubectl apply -f <component>/k8s/deployment.yaml
    }
```

**NEVER use `kubectl replace --force`** — it deletes the resource first, and if Kyverno blocks the recreation, the deployment is gone.

**NEVER use `kubectl apply --server-side`** with Helm-migrated resources — server-side apply merges fields, creating invalid specs (e.g., both `value` and `valueFrom` on the same env var).

## Reference: Components with apply-manifest
- `stoa-gateway` (stoa-gateway-ci.yml) ✓
- `control-plane-ui` (control-plane-ui-ci.yml) ✓
- `portal` (stoa-portal-ci.yml) ✓
- `control-plane-api` — **NO** (naming mismatch: CI uses `control-plane-api`, k8s has `stoa-control-plane-api`)
