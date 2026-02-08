# Runbook: Gateway - Registration Failed

> **Severity**: 🟡 High
> **Last updated**: 2026-02-06
> **Owner**: Platform Team
> **Related ADR**: ADR-028 (Gateway Auto-Registration)

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `GatewayRegistrationFailed` | Registration error rate > 0 for 5m | [Gateways Dashboard](https://grafana.gostoa.dev/d/gateways) |
| `GatewayOffline` | Gateway OFFLINE for > 3m | [Gateways Dashboard](https://grafana.gostoa.dev/d/gateways) |

### Observed Behavior

- Gateway pod starts but doesn't appear in Console UI → Gateways
- Gateway logs show "Failed to register with Control Plane" errors
- Gateway shows OFFLINE status despite being healthy
- 503 "Gateway registration disabled" error in logs
- 401 "Invalid gateway key" error in logs

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | API traffic may not route through unregistered gateways |
| **APIs** | New API deployments won't reach the gateway |
| **SLA** | Reduced capacity if gateway pool is diminished |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check gateway pod status
kubectl get pods -n stoa-system -l app.kubernetes.io/name=stoa-gateway

# 2. Check gateway logs for registration errors
kubectl logs -n stoa-system -l app.kubernetes.io/name=stoa-gateway --tail=100 | grep -i "register\|error\|failed"

# 3. Check Control Plane API logs
kubectl logs -n stoa-system -l app.kubernetes.io/name=control-plane-api --tail=100 | grep -i gateway

# 4. Check if GATEWAY_API_KEYS is configured
kubectl exec -n stoa-system deployment/control-plane-api -- env | grep GATEWAY_API_KEYS

# 5. Test registration endpoint
curl -s -o /dev/null -w "%{http_code}" \
  -X POST https://api.gostoa.dev/v1/internal/gateways/register \
  -H "X-Gateway-Key: test" \
  -H "Content-Type: application/json" \
  -d '{"hostname":"test","mode":"edge-mcp","version":"0.1.0","environment":"test","capabilities":[],"admin_url":"http://test"}'
```

### Verification Points

- [ ] Gateway pod running?
- [ ] Control Plane API accessible from gateway?
- [ ] `GATEWAY_API_KEYS` secret mounted in Control Plane?
- [ ] Gateway has `STOA_CONTROL_PLANE_API_KEY` set?
- [ ] Network policy allows gateway → Control Plane traffic?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| `stoa-gateway-secrets` Secret missing or empty | High | `kubectl get secret stoa-gateway-secrets -n stoa-system` — if not found, gateway runs in standalone mode |
| GATEWAY_API_KEYS not configured on CP | High | `kubectl exec ... -- env \| grep GATEWAY_API_KEYS` returns empty |
| API key mismatch (gateway key != CP key) | High | Compare gateway key vs CP keys |
| Control Plane unreachable | Medium | `curl` from gateway pod to CP fails |
| Wrong endpoint URL | Medium | Check `STOA_CONTROL_PLANE_URL` in gateway |
| Network policy blocking | Low | Check NetworkPolicy resources |

---

## 3. Resolution

### Issue: 503 "Gateway registration disabled"

**Root cause**: `GATEWAY_API_KEYS` environment variable not set in Control Plane.

```bash
# 1. Create the secret (if not exists)
kubectl create secret generic stoa-gateway-api-keys \
  --namespace stoa-system \
  --from-literal=GATEWAY_API_KEYS="gw_prod_key_$(openssl rand -hex 16)" \
  --dry-run=client -o yaml | kubectl apply -f -

# 2. Patch Control Plane deployment
kubectl patch deployment control-plane-api -n stoa-system \
  --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/containers/0/env/-", "value": {"name": "GATEWAY_API_KEYS", "valueFrom": {"secretKeyRef": {"name": "stoa-gateway-api-keys", "key": "GATEWAY_API_KEYS"}}}}]'

# 3. Wait for rollout
kubectl rollout status deployment/control-plane-api -n stoa-system

# 4. Restart gateway to trigger re-registration
kubectl rollout restart deployment/stoa-gateway -n stoa-system
```

### Issue: 401 "Invalid gateway key"

**Root cause**: Gateway's API key doesn't match any key in `GATEWAY_API_KEYS`.

```bash
# 1. Check what keys Control Plane expects
kubectl get secret stoa-gateway-api-keys -n stoa-system \
  -o jsonpath='{.data.GATEWAY_API_KEYS}' | base64 -d
# Output example: gw_prod_key_abc123,gw_staging_key_xyz789

# 2. Check what key gateway is using
kubectl exec -n stoa-system deployment/stoa-gateway -- \
  env | grep STOA_CONTROL_PLANE_API_KEY
# Output example: STOA_CONTROL_PLANE_API_KEY=gw_wrong_key

# 3. Update gateway secret with correct key
kubectl create secret generic stoa-gateway-secrets \
  --namespace stoa-system \
  --from-literal=STOA_CONTROL_PLANE_API_KEY="gw_prod_key_abc123" \
  --dry-run=client -o yaml | kubectl apply -f -

# 4. Restart gateway
kubectl rollout restart deployment/stoa-gateway -n stoa-system
```

### Issue: Gateway shows OFFLINE despite heartbeat

**Root cause**: Heartbeat URL path is incorrect (was `/heartbeat/{id}`, should be `/{id}/heartbeat`).

```bash
# 1. Check gateway logs for 404 on heartbeat
kubectl logs -n stoa-system deployment/stoa-gateway | grep "heartbeat\|404"

# 2. If 404 found, upgrade to latest gateway image (fix in PR #122)
kubectl set image deployment/stoa-gateway \
  stoa-gateway=ghcr.io/stoa/stoa-gateway:latest -n stoa-system

# 3. Wait for rollout
kubectl rollout status deployment/stoa-gateway -n stoa-system
```

### Issue: Control Plane unreachable from gateway

```bash
# 1. Test connectivity from gateway pod
kubectl exec -n stoa-system deployment/stoa-gateway -- \
  curl -s http://control-plane-api.stoa-system.svc.cluster.local:8000/health

# 2. If DNS fails, check service exists
kubectl get svc control-plane-api -n stoa-system

# 3. If connection refused, check CP pod is running
kubectl get pods -n stoa-system -l app.kubernetes.io/name=control-plane-api

# 4. Check NetworkPolicy allows traffic
kubectl get networkpolicy -n stoa-system -o yaml | grep -A5 "stoa-gateway"
```

### Rollback if necessary

```bash
# Rollback Control Plane to previous version
kubectl rollout undo deployment/control-plane-api -n stoa-system

# Rollback gateway to previous version
kubectl rollout undo deployment/stoa-gateway -n stoa-system
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] Gateway appears in Console UI → Gateways
- [ ] Gateway status shows ONLINE (green)
- [ ] Heartbeat visible in gateway logs (every 30s)
- [ ] No registration errors in Control Plane logs
- [ ] Gateway config endpoint responds: `GET /v1/internal/gateways/{id}/config`

### Verification Commands

```bash
# 1. Check gateway registered (from Control Plane API)
curl -s https://api.gostoa.dev/v1/admin/gateways \
  -H "Authorization: Bearer $TOKEN" | jq '.[].name'

# 2. Check gateway status
curl -s https://api.gostoa.dev/v1/admin/gateways \
  -H "Authorization: Bearer $TOKEN" | jq '.[] | {name, status, last_health_check}'

# 3. Check heartbeat in gateway logs
kubectl logs -n stoa-system deployment/stoa-gateway --tail=10 | grep heartbeat

# 4. Verify config endpoint works
GATEWAY_ID=$(curl -s https://api.gostoa.dev/v1/admin/gateways -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')
curl -s "https://api.gostoa.dev/v1/internal/gateways/$GATEWAY_ID/config" \
  -H "X-Gateway-Key: $GW_KEY" | jq .
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | After 15 min without resolution | Slack `#platform-team` |
| L3 | Gateway Core Team | If registration protocol issues | Slack `#gateway-core` |

### Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| Platform Lead | - | @platform-lead |
| Gateway Owner | - | @gateway-team |
| Security (key compromise) | - | @security-team |

---

## 6. Post-mortem

### To document after resolution

- [ ] Incident timeline
- [ ] Root cause identified (503/401/404/network)
- [ ] Preventive actions (monitoring, alerts, documentation)
- [ ] Runbook updated if new scenario discovered

### Post-mortem Template

```markdown
## Incident: Gateway Registration Failure
**Date**: YYYY-MM-DD HH:MM
**Duration**: X hours Y minutes
**Severity**: High

### Timeline
- HH:MM - Gateway deployment rolled out
- HH:MM - Alert: GatewayOffline triggered
- HH:MM - Diagnosis: GATEWAY_API_KEYS not configured
- HH:MM - Fix applied: Secret created and deployment patched
- HH:MM - Verified: Gateway shows ONLINE in Console

### Root Cause
[e.g., New deployment of Control Plane didn't include GATEWAY_API_KEYS env var]

### Preventive Actions
- [ ] Add GATEWAY_API_KEYS to Helm values (always present)
- [ ] Add CI check for required env vars
- [ ] Create alert for registration failures
```

---

## 7. References

### Documentation

- [Gateway Auto-Registration Guide](../guides/gateway-auto-registration.md)
- [ADR-036: Gateway Auto-Registration](https://docs.gostoa.dev/architecture/adr/adr-036-gateway-auto-registration)
- [ADR-024: Gateway Unified Modes](https://docs.gostoa.dev/architecture/adr/adr-024-gateway-unified-modes)

### Grafana Dashboards

- [Gateways Overview](https://grafana.gostoa.dev/d/gateways)
- [Control Plane API](https://grafana.gostoa.dev/d/control-plane)

### Related Code

- Control Plane: `src/routers/gateway_internal.py`
- Control Plane: `src/workers/gateway_health_worker.py`
- Gateway (Rust): `src/control_plane/registration.rs`

### Previous Incidents

| Date | Issue | Resolution |
|------|-------|------------|
| 2026-02-06 | 503 registration disabled | Created GATEWAY_API_KEYS secret, patched CP deployment |
| 2026-02-06 | 404 on heartbeat | Fixed URL path order in registration.rs (PR #122) |

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-02-06 | Platform Team | Initial creation based on ADR-028 implementation |
