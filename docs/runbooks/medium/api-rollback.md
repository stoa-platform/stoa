# Runbook: API Deployment Rollback

> **Severity**: Medium
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Linear Issue**: CAB-107

---

## 1. Symptoms

### When to Trigger a Rollback

| Situation | Indicators |
|-----------|------------|
| API returns 5xx errors | Error rate > 5% |
| Degraded latency | P95 > SLA threshold after deployment |
| Breaking change detected | Clients report incompatibility |
| Misconfiguration | Incorrect policies applied |

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | API non-functional |
| **APIs** | Deployed version defective |
| **SLA** | Potential ongoing violation |

---

## 2. Quick Diagnosis (< 5 min)

### Identify Version to Rollback

```bash
# 1. Check deployment history via API
curl -s https://api.stoa.cab-i.com/v1/deployments?api_id=<API_ID>&limit=5 | jq .

# 2. Check in GitLab
git log --oneline -10 -- apis/<API_NAME>/

# 3. Check in AWX
curl -s -H "Authorization: Bearer $AWX_TOKEN" \
  "https://awx.stoa.cab-i.com/api/v2/jobs/?job_template=1&order_by=-created" | \
  jq '.results[:5] | .[] | {id, status, created}'

# 4. Check active version in Gateway
curl -s -u $GATEWAY_USER:$GATEWAY_PASSWORD \
  "https://gateway.stoa.cab-i.com/rest/apigateway/apis/<API_ID>" | \
  jq '.apiResponse.api.apiVersion'
```

### Pre-Rollback Checklist

- [ ] Target version identified
- [ ] Rollback impact evaluated
- [ ] Clients notified if necessary
- [ ] Backup of current config done

---

## 3. Rollback Methods

### Method 1: Via Control-Plane UI (Recommended)

1. Go to https://console.stoa.cab-i.com
2. Navigate to APIs > [API Name] > Deployments
3. Find the previous deployment (status: success)
4. Click "Rollback to this version"
5. Confirm rollback

### Method 2: Via Control-Plane API

```bash
# Trigger rollback via API
curl -X POST \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  https://api.stoa.cab-i.com/v1/deployments/rollback \
  -d '{
    "api_id": "<API_ID>",
    "target_version": "1.0.0",
    "environment": "dev",
    "reason": "Regression detected after deployment"
  }'

# Follow rollback status
curl -s -H "Authorization: Bearer $JWT_TOKEN" \
  https://api.stoa.cab-i.com/v1/deployments/<DEPLOYMENT_ID> | jq .
```

### Method 3: Via AWX Job Template

```bash
# Launch "Rollback API" job template
curl -X POST \
  -H "Authorization: Bearer $AWX_TOKEN" \
  -H "Content-Type: application/json" \
  https://awx.stoa.cab-i.com/api/v2/job_templates/2/launch/ \
  -d '{
    "extra_vars": {
      "api_id": "<API_ID>",
      "api_name": "my-api",
      "target_version": "1.0.0",
      "tenant_id": "acme",
      "environment": "dev"
    }
  }'

# Follow job
curl -s -H "Authorization: Bearer $AWX_TOKEN" \
  https://awx.stoa.cab-i.com/api/v2/jobs/<JOB_ID>/ | jq '{status, failed}'
```

### Method 4: Manual Gateway Rollback (Emergency)

```bash
# 1. Deactivate current API
curl -X PUT \
  -u $GATEWAY_USER:$GATEWAY_PASSWORD \
  "https://gateway.stoa.cab-i.com/rest/apigateway/apis/<API_ID>/deactivate"

# 2. Restore previous version from Git
git checkout HEAD~1 -- apis/<API_NAME>/openapi.yaml

# 3. Re-import API
curl -X POST \
  -u $GATEWAY_USER:$GATEWAY_PASSWORD \
  -H "Content-Type: application/json" \
  "https://gateway.stoa.cab-i.com/rest/apigateway/apis" \
  -d @apis/<API_NAME>/openapi.yaml

# 4. Activate restored API
curl -X PUT \
  -u $GATEWAY_USER:$GATEWAY_PASSWORD \
  "https://gateway.stoa.cab-i.com/rest/apigateway/apis/<NEW_API_ID>/activate"
```

### Method 5: GitOps Rollback (ArgoCD)

```bash
# 1. View ArgoCD history
argocd app history <APP_NAME>

# 2. Rollback to previous revision
argocd app rollback <APP_NAME> <REVISION_NUMBER>

# 3. Or via kubectl
kubectl patch application <APP_NAME> -n argocd --type merge -p '{
  "operation": {
    "sync": {
      "revision": "<PREVIOUS_COMMIT_SHA>"
    }
  }
}'
```

---

## 4. Post-Rollback Verification

### Validation Checklist

- [ ] API responds correctly
- [ ] Correct version deployed
- [ ] No 5xx errors
- [ ] Normal latency
- [ ] Clients confirm functionality

### Verification Commands

```bash
# Test API
curl -s https://gateway.stoa.cab-i.com/gateway/<API_PATH>/health | jq .

# Check version
curl -s -u $GATEWAY_USER:$GATEWAY_PASSWORD \
  "https://gateway.stoa.cab-i.com/rest/apigateway/apis/<API_ID>" | \
  jq '.apiResponse.api | {name, apiVersion, isActive}'

# Check metrics
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 \
  'rate(http_requests_total{api="<API_NAME>",status=~"5.."}[5m])'

# Check logs
kubectl logs -n stoa deploy/apigateway --tail=50 | grep "<API_NAME>"
```

---

## 5. Communication

### Notification Template

```markdown
## API Rollback Notice

**API**: [API_NAME]
**Environment**: [dev/staging/prod]
**Time**: [TIMESTAMP]
**From Version**: [CURRENT_VERSION]
**To Version**: [TARGET_VERSION]

### Reason
[Description of the issue]

### Impact
[Description of the impact]

### Status
- [ ] Rollback initiated
- [ ] Rollback complete
- [ ] Verification OK
- [ ] Clients notified

### Contact
Platform Team - #ops-alerts
```

---

## 6. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Rollback decision | Slack `#ops-alerts` |
| L2 | API Owner | Business impact validation | Per API |
| L3 | Platform Team | If rollback fails | @platform-team |

---

## 7. Prevention

### Pre-Deployment Checklist

- [ ] Automated tests passed
- [ ] OpenAPI spec reviewed
- [ ] Backward compatibility verified
- [ ] Canary deployment if possible
- [ ] Rollback plan ready

### Best Practices

1. **Blue/Green deployment** to minimize downtime
2. **Canary releases** to detect issues early
3. **Feature flags** to enable/disable functionality
4. **Automated testing** before each deployment
5. **Monitoring** of key metrics post-deployment

---

## 8. References

- [Deployment Best Practices](docs/deployment-guide.md)
- [ArgoCD Rollback](https://argo-cd.readthedocs.io/en/stable/user-guide/commands/argocd_app_rollback/)
- [Gateway API Management](docs/ibm/webmethods-gateway-api.md)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2024-12-28 | Platform Team | Initial creation |
