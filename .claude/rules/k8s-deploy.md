---
globs: "k8s/**,deploy/**,charts/**,terraform/**,**/alembic/**"
---

# Deployment & K8s Checklist

## Helm
```bash
helm lint charts/stoa-platform
helm upgrade --install stoa-platform ./charts/stoa-platform -n stoa-system --create-namespace
kubectl apply -f charts/stoa-platform/crds/
```

## Terraform
```bash
cd terraform/environments/dev
terraform init && terraform plan && terraform apply
```
Always `terraform plan` before `terraform apply`.

## Database Migrations (Alembic)
- Location: `control-plane-api/alembic/`
- Create: `alembic revision --autogenerate -m "description"`
- Apply: `alembic upgrade head`

## MCP Gateway CRDs
```bash
kubectl apply -f - <<EOF
apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: my-api-tool
  namespace: tenant-acme
spec:
  displayName: My API Tool
  description: A sample tool
  endpoint: https://api.example.com/v1/action
  method: POST
EOF
```

## Configuration
- `BASE_DOMAIN` is single source of truth for all URLs
- Environment configs: `deploy/config/{dev,staging,prod}.env`

## MCP Gateway Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `OPA_ENABLED` | `true` | OPA policy engine |
| `OPA_EMBEDDED` | `true` | Embedded evaluator |
| `METERING_ENABLED` | `true` | Kafka metering |
| `K8S_WATCHER_ENABLED` | `false` | CRD watcher |

## K8s Deployment Checklist

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
If the container uses `nginx.conf.template` with `proxy_pass` variables, the corresponding env vars MUST be in the deployment manifest.

### 8. Nginx envsubst — use custom script, NOT built-in (CRITICAL)
Do NOT use `NGINX_ENVSUBST_FILTER` or the built-in `20-envsubst-on-templates.sh`:
- `NGINX_ENVSUBST_FILTER`: latest nginx image uses awk to process it, `${VAR}` breaks awk regex
- Docker `ENV` expands `${VAR}` at build time (single quotes don't prevent this)
- Without filter, envsubst replaces ALL `$var` refs (including nginx `$uri`, `$host`) with empty strings
- `$$` is NOT an escape in envsubst — `$$var` becomes `$` + empty string, not `$var`

**Solution**: Custom entrypoint script with explicit filter + non-standard template dir:
```dockerfile
# Template in custom dir (NOT /etc/nginx/templates/) so built-in script skips it
COPY 19-envsubst-custom.sh /docker-entrypoint.d/19-envsubst-custom.sh
COPY nginx.conf.template /etc/nginx/custom-templates/default.conf.template
```
```bash
#!/bin/sh
# 19-envsubst-custom.sh — only substitute our 4 variables
envsubst '${API_BACKEND_URL} ${LOGS_BACKEND_URL} ${GRAFANA_BACKEND_URL} ${DNS_RESOLVER}' \
  < /etc/nginx/custom-templates/default.conf.template \
  > /etc/nginx/conf.d/default.conf
```

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

## Service Port Consistency (post-mortem PR #2077)

Backend URL env vars in k8s manifests MUST use the correct K8s Service port. The Helm chart in stoa-infra defines the actual Service port — standalone manifests and Helm defaults in this repo must match.

### Known-ports map (source of truth)

| K8s Service | Port | Container Port |
|-------------|------|---------------|
| stoa-control-plane-api | 8000 | 8000 |
| stoa-gateway | 80 | 8080 |
| opensearch-dashboards | 5601 | 5601 |
| grafana | 3000 | 3000 |
| prometheus-kube-prometheus-prometheus | 9090 | 9090 |

### CI enforcement

`scripts/ci/check-service-ports.sh` scans all `**/k8s/deployment.yaml` and `charts/**/*.yaml` for `*.svc.cluster.local` URLs and validates ports against the known-ports map. Runs in `required-checks.yml` on every PR.

```bash
# Local check
bash scripts/ci/check-service-ports.sh --verbose
```

### When to update

- Service port changed in stoa-infra Helm chart → update `KNOWN_PORTS` in the script + fix all references
- New internal service added → add to `KNOWN_PORTS` in the script
