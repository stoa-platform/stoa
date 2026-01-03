# Runbook: AWX - Unreachable

> **Severity**: Medium
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Linear Issue**: CAB-107

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `AWXDown` | `up{job="awx"} == 0` | [AWX Dashboard](https://grafana.dev.stoa.cab-i.com/d/awx) |
| `AWXWebUnhealthy` | `awx_web_status != 200` | [AWX Dashboard](https://grafana.dev.stoa.cab-i.com/d/awx) |
| `AWXTaskQueueHigh` | `awx_pending_jobs > 50` | [AWX Dashboard](https://grafana.dev.stoa.cab-i.com/d/awx) |

### Observed Behavior

- AWX UI inaccessible (https://awx.stoa.cab-i.com)
- Control-Plane API fails to launch jobs
- Automatic deployments not triggering
- "connection refused" error in logs

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | No deployment automation |
| **APIs** | Manual deployments only |
| **SLA** | Increased deployment delay |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check AWX pods
kubectl get pods -n awx

# 2. Check services
kubectl get svc -n awx

# 3. Check AWX Web logs
kubectl logs -n awx deploy/awx-web --tail=100

# 4. Check AWX Task logs
kubectl logs -n awx deploy/awx-task --tail=100

# 5. Check Ingress
kubectl get ingress -n awx
kubectl describe ingress awx -n awx

# 6. Test health check
curl -s https://awx.stoa.cab-i.com/api/v2/ping/ | jq .
```

### Verification Points

- [ ] awx-web pod running?
- [ ] awx-task pod running?
- [ ] awx-ee (execution env) pod running?
- [ ] PostgreSQL accessible?
- [ ] Redis accessible?
- [ ] Ingress configured?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| awx-web pod crash | High | `kubectl get pods -n awx` |
| Database connection lost | Medium | Logs "database" |
| Redis down | Medium | `kubectl get pods -n awx -l app=redis` |
| Invalid TLS certificate | Low | `curl -v https://awx.stoa.cab-i.com` |
| Insufficient resources | Low | `kubectl top pods -n awx` |

---

## 3. Resolution

### Immediate Action (mitigation)

```bash
# 1. Restart AWX pods
kubectl rollout restart deployment -n awx awx-web
kubectl rollout restart deployment -n awx awx-task

# 2. Follow rollout
kubectl rollout status deployment -n awx awx-web --timeout=5m

# 3. Check status
kubectl get pods -n awx
```

### Resolution by Cause

#### Case 1: awx-web pod crash

```bash
# View crash logs
kubectl logs -n awx deploy/awx-web --previous

# Check events
kubectl get events -n awx --sort-by='.lastTimestamp' | tail -20

# Restart
kubectl rollout restart deployment -n awx awx-web

# If OOM, increase memory
kubectl patch deployment awx-web -n awx --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "4Gi"}
]'
```

#### Case 2: PostgreSQL database inaccessible

```bash
# Check PostgreSQL pod
kubectl get pods -n awx -l app=postgres

# Check connection from AWX
kubectl exec -n awx deploy/awx-web -- \
  python -c "import psycopg2; psycopg2.connect('host=postgres port=5432 dbname=awx user=awx')"

# If PostgreSQL down, restart
kubectl rollout restart statefulset -n awx postgres

# Check PostgreSQL logs
kubectl logs -n awx postgres-0
```

#### Case 3: Redis inaccessible

```bash
# Check Redis
kubectl get pods -n awx -l app=redis
kubectl logs -n awx deploy/redis

# Test connection
kubectl exec -n awx deploy/awx-web -- redis-cli -h redis ping

# Restart Redis
kubectl rollout restart deployment -n awx redis
```

#### Case 4: AWX Operator issue

```bash
# Check operator
kubectl get pods -n awx -l app.kubernetes.io/name=awx-operator

# Operator logs
kubectl logs -n awx -l app.kubernetes.io/name=awx-operator --tail=100

# Check AWX custom resource
kubectl get awx -n awx
kubectl describe awx awx -n awx

# Restart operator
kubectl rollout restart deployment -n awx awx-operator-controller-manager
```

#### Case 5: Regenerate AWX API token

```bash
# Token is stored in AWS Secrets Manager
# If token is invalid, create a new one

# Log in to AWX UI and create new token:
# Settings > Users > admin > Tokens > Create Token

# Update AWS secret
aws secretsmanager update-secret \
  --secret-id stoa/awx-token \
  --secret-string '{"token":"<NEW_TOKEN>"}'

# Update K8s secret
kubectl create secret generic awx-token -n stoa-system \
  --from-literal=token=<NEW_TOKEN> \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart Control-Plane API to pick up new token
kubectl rollout restart deployment -n stoa-system control-plane-api
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] AWX UI accessible
- [ ] AWX API responds
- [ ] Jobs can be launched
- [ ] Control-Plane API can communicate with AWX
- [ ] No errors in logs

### Verification Commands

```bash
# API health check
curl -s https://awx.stoa.cab-i.com/api/v2/ping/ | jq .

# List job templates
curl -s -H "Authorization: Bearer $AWX_TOKEN" \
  https://awx.stoa.cab-i.com/api/v2/job_templates/ | jq '.results[].name'

# Test a job (dry-run)
curl -s -H "Authorization: Bearer $AWX_TOKEN" \
  -X POST \
  https://awx.stoa.cab-i.com/api/v2/job_templates/1/launch/ \
  -d '{"check": true}'

# Check from Control-Plane API
curl -s https://api.dev.stoa.cab-i.com/health | jq .awx
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | If restart fails | Slack `#platform-team` |
| L3 | AWX Community | AWX bug | GitHub Issues |

---

## 6. Prevention

### Recommended Monitoring

```yaml
groups:
  - name: awx
    rules:
      - alert: AWXWebDown
        expr: up{job="awx-web"} == 0
        for: 2m
        labels:
          severity: high
        annotations:
          summary: "AWX Web is down"

      - alert: AWXTaskDown
        expr: up{job="awx-task"} == 0
        for: 2m
        labels:
          severity: high

      - alert: AWXJobQueueHigh
        expr: awx_pending_jobs > 20
        for: 10m
        labels:
          severity: warning
```

### STOA Job Templates

| Job Template | ID | Description |
|--------------|-----|-------------|
| Deploy API | 1 | Deploy an API to Gateway |
| Rollback API | 2 | Rollback an API |
| Sync Gateway | 3 | Synchronize Gateway config |
| Promote Portal | 4 | Publish to Developer Portal |
| Provision Tenant | 5 | Provision a new tenant |
| Register API Gateway | 6 | Register an API in Gateway |

---

## 7. References

- [AWX Documentation](https://ansible.readthedocs.io/projects/awx/en/latest/)
- [AWX Operator](https://github.com/ansible/awx-operator)
- [AWX REST API](https://docs.ansible.com/ansible-tower/latest/html/towerapi/index.html)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2024-12-28 | Platform Team | Initial creation |
