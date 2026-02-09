# Troubleshooting

## Quick Diagnostics

```bash
# Pod status overview
kubectl get pods -n stoa-system

# Recent events (shows scheduling, pull, crash issues)
kubectl get events -n stoa-system --sort-by='.lastTimestamp' | tail -20

# Component logs
kubectl logs -f deploy/control-plane-api -n stoa-system
kubectl logs -f deploy/mcp-gateway -n stoa-system
kubectl logs -f deploy/stoa-gateway -n stoa-system

# Previous container logs (after crash)
kubectl logs deploy/control-plane-api -n stoa-system --previous
```

## Common Issues

### CrashLoopBackOff

**Symptoms**: Pod repeatedly crashes, `kubectl get pods` shows `CrashLoopBackOff`.

**Diagnosis**:
```bash
kubectl describe pod <pod-name> -n stoa-system
kubectl logs <pod-name> -n stoa-system --previous
```

**Common causes**:

| Cause | Log Pattern | Fix |
|-------|------------|-----|
| Missing env var | `KeyError: 'DATABASE_URL'` | Check secret exists: `kubectl get secret -n stoa-system` |
| Bad DB connection | `connection refused` or `password authentication failed` | Verify PostgreSQL is reachable, check credentials |
| Port conflict | `Address already in use` | Check for duplicate deployments |
| OOM killed | `OOMKilled` in pod status | Increase memory limits in Helm values |
| Bad config | `ValidationError` at startup | Check env vars and config format |

### ImagePullBackOff

**Symptoms**: Pod stuck in `ImagePullBackOff` or `ErrImagePull`.

```bash
kubectl describe pod <pod-name> -n stoa-system | grep -A5 "Events"
```

**Fixes**:
- Verify image exists in registry: `aws ecr describe-images --repository-name apim/<component>`
- Check image pull secrets: `kubectl get secret -n stoa-system | grep registry`
- Verify ECR auth: `aws ecr get-login-password | docker login --username AWS --password-stdin <registry>`

### Kyverno Blocks Pod Creation

**Symptoms**: Deployment stuck, no pods created. Events show Kyverno policy violation.

```bash
kubectl get events -n stoa-system | grep -i kyverno
```

**Root cause**: The cluster has a `restrict-privileged` Kyverno policy in Enforce mode. Every container MUST explicitly set `securityContext.privileged: false`.

**Fix**: Ensure the deployment manifest includes:

```yaml
securityContext:
  privileged: false          # REQUIRED — explicit, not just default
  runAsNonRoot: true
  allowPrivilegeEscalation: false
  capabilities:
    drop:
      - ALL
  seccompProfile:
    type: RuntimeDefault
```

### Nginx envsubst Issues

**Symptoms**: Console UI or Portal returns 502/503, or `$uri`, `$host` are replaced with empty strings.

**Root cause**: Using the built-in nginx `NGINX_ENVSUBST_FILTER` or default `20-envsubst-on-templates.sh` causes issues — see `k8s-deploy.md` rule #8 for full details.

**Fixes**:
- Use the custom `19-envsubst-custom.sh` entrypoint script
- Place templates in `/etc/nginx/custom-templates/` (not `/etc/nginx/templates/`)
- Only substitute known variables: `${API_BACKEND_URL} ${LOGS_BACKEND_URL} ${GRAFANA_BACKEND_URL} ${DNS_RESOLVER}`

**Verify nginx config**:
```bash
kubectl exec -it deploy/control-plane-ui -n stoa-system -- cat /etc/nginx/conf.d/default.conf
```

### Nginx proxy_pass DNS Failure

**Symptoms**: nginx crashes at startup with `host not found in upstream`.

**Root cause**: Static `proxy_pass http://hostname:port/` hostnames are resolved at startup. If DNS doesn't resolve, nginx crashes.

**Fix**: Use variables for proxy_pass backends:

```nginx
set $api_backend "${API_BACKEND_URL}";
location /api/ {
    proxy_pass $api_backend;   # Resolved at request time
}
```

### MCP Gateway — Circuit Breaker Tripped

**Symptoms**: Tool calls return `503 Service Unavailable` with circuit breaker message.

**Diagnosis**:
```bash
kubectl logs deploy/mcp-gateway -n stoa-system | grep "circuit"
```

**Fixes**:
- Check upstream service health
- Wait for half-open timeout (default: 30s)
- Restart gateway if upstream is now healthy: `kubectl rollout restart deploy/mcp-gateway -n stoa-system`

### MCP Gateway — Token Validation Failed

**Symptoms**: `401 Unauthorized` or `403 Forbidden` from gateway.

**Diagnosis**:
```bash
kubectl logs deploy/mcp-gateway -n stoa-system | grep -i "token\|auth\|jwt"
```

**Common causes**:

| Cause | Fix |
|-------|-----|
| JWT secret mismatch | Verify `JWT_SECRET` matches between gateway and API |
| Keycloak client secret rotated | Update secret in Vault, force ESO sync, restart pods |
| Token expired | Client needs to refresh token |
| Wrong audience claim | Check Keycloak client configuration |

### OOM (Out of Memory)

**Symptoms**: Pod killed with `OOMKilled` status.

```bash
kubectl describe pod <pod-name> -n stoa-system | grep -A3 "Last State"
```

**Fix**: Increase memory limits:

```yaml
resources:
  limits:
    memory: "512Mi"    # Increase from default
  requests:
    memory: "256Mi"
```

### Rollout Stuck (Deadlock)

**Symptoms**: Deployment rollout hangs, old pod running but new pod not starting.

**Root cause**: Single-replica deployment with `maxSurge: 1, maxUnavailable: 0` on a resource-constrained cluster — no room to schedule the new pod alongside the old one.

**Fix**: Use `maxUnavailable: 1, maxSurge: 0`:

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 0
```

## Service-Specific Debugging

### Control Plane API

```bash
# Check database connectivity
kubectl exec deploy/control-plane-api -n stoa-system -- \
  python3 -c "from sqlalchemy import create_engine; e = create_engine('$DATABASE_URL'); e.connect(); print('OK')"

# Check Alembic migration state
kubectl exec deploy/control-plane-api -n stoa-system -- \
  alembic current

# Health endpoints
curl -s https://api.<BASE_DOMAIN>/health/ready   # Readiness (DB + deps)
curl -s https://api.<BASE_DOMAIN>/health/live     # Liveness (process alive)
curl -s https://api.<BASE_DOMAIN>/health/startup  # Startup (init complete)
```

### Keycloak

```bash
# Check Keycloak health
curl -s https://auth.<BASE_DOMAIN>/health/ready

# Verify OIDC config
curl -s https://auth.<BASE_DOMAIN>/realms/stoa/.well-known/openid-configuration | python3 -m json.tool

# Test token issuance
curl -s -X POST "https://auth.<BASE_DOMAIN>/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=control-plane-ui&username=test-user&password=test" \
  | python3 -m json.tool
```

## Log Level Adjustment

To temporarily increase logging for debugging:

```bash
# Control Plane API — set DEBUG level
kubectl set env deploy/control-plane-api -n stoa-system LOG_LEVEL=DEBUG
kubectl rollout restart deploy/control-plane-api -n stoa-system

# Remember to revert after debugging
kubectl set env deploy/control-plane-api -n stoa-system LOG_LEVEL=INFO
kubectl rollout restart deploy/control-plane-api -n stoa-system
```
