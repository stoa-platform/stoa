# Runbook: Jenkins - Pipeline Stuck

> **Severity**: Medium
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Linear Issue**: CAB-107

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `JenkinsBuildStuck` | `jenkins_build_duration > 1h` | [Jenkins Dashboard](https://grafana.gostoa.dev/d/jenkins) |
| `JenkinsQueueLong` | `jenkins_queue_size > 10` | [Jenkins Dashboard](https://grafana.gostoa.dev/d/jenkins) |
| `JenkinsAgentOffline` | `jenkins_agents_online == 0` | [Jenkins Dashboard](https://grafana.gostoa.dev/d/jenkins) |

### Observed Behavior

- Builds in "pending" state for a long time
- Pipeline stuck at a stage without progress
- Jenkins queue accumulating
- No new deployments

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | Deployments blocked |
| **APIs** | New versions not deployed |
| **SLA** | Delivery delays |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check Jenkins pods
kubectl get pods -n jenkins

# 2. Check Jenkins master logs
kubectl logs -n jenkins deploy/jenkins --tail=100

# 3. List builds in progress via API
curl -s -u admin:$JENKINS_TOKEN \
  "https://jenkins.gostoa.dev/api/json?tree=jobs[name,builds[number,result,building]]" | jq .

# 4. Check queue
curl -s -u admin:$JENKINS_TOKEN \
  "https://jenkins.gostoa.dev/queue/api/json" | jq '.items | length'

# 5. Check agents
curl -s -u admin:$JENKINS_TOKEN \
  "https://jenkins.gostoa.dev/computer/api/json" | jq '.computer[] | {name, offline}'
```

### Verification Points

- [ ] Jenkins master running?
- [ ] Agents available?
- [ ] Sufficient resources (CPU/Mem)?
- [ ] Valid credentials?
- [ ] Network to Git/Docker OK?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Agent disconnected | High | Check agents online |
| Expired credentials | Medium | Logs "authentication failed" |
| Docker registry timeout | Medium | Logs "docker pull" |
| Git clone failed | Medium | Logs "git clone" |
| Insufficient resources | Low | `kubectl top pods` |

---

## 3. Resolution

### Immediate Action (mitigation)

```bash
# 1. Cancel stuck builds (via UI or API)
curl -X POST -u admin:$JENKINS_TOKEN \
  "https://jenkins.gostoa.dev/job/<JOB_NAME>/<BUILD_NUMBER>/stop"

# 2. Clear queue
curl -X POST -u admin:$JENKINS_TOKEN \
  "https://jenkins.gostoa.dev/queue/cancelItem?id=<ITEM_ID>"

# 3. Restart Jenkins if necessary
kubectl rollout restart deployment -n jenkins jenkins
```

### Resolution by Cause

#### Case 1: Agent disconnected

```bash
# List agents
kubectl get pods -n jenkins -l app=jenkins-agent

# View agent logs
kubectl logs -n jenkins <jenkins-agent-pod>

# Delete zombie agents
kubectl delete pod -n jenkins -l app=jenkins-agent --field-selector status.phase=Failed

# Force agent reconnection (via Jenkins UI)
# Manage Jenkins > Manage Nodes > Reconnect
```

#### Case 2: Expired credentials

```bash
# Check credentials in Jenkins
# Manage Jenkins > Credentials

# Update via API (example for GitLab token)
curl -X POST -u admin:$JENKINS_TOKEN \
  "https://jenkins.gostoa.dev/credentials/store/system/domain/_/credential/gitlab-token/update" \
  --data-urlencode "json={
    \"secret\": \"$NEW_GITLAB_TOKEN\"
  }"

# Or via kubectl if stored in K8s secret
kubectl create secret generic jenkins-credentials -n jenkins \
  --from-literal=gitlab-token=$NEW_GITLAB_TOKEN \
  --dry-run=client -o yaml | kubectl apply -f -
```

#### Case 3: Docker registry timeout

```bash
# Test registry connection
kubectl run docker-test --rm -it --restart=Never \
  --image=docker:dind -n jenkins -- \
  docker pull 848853684735.dkr.ecr.eu-west-1.amazonaws.com/control-plane-api:latest

# Check ECR credentials
aws ecr get-login-password --region eu-west-1 | docker login \
  --username AWS \
  --password-stdin 848853684735.dkr.ecr.eu-west-1.amazonaws.com

# Regenerate ECR token in Jenkins secret
kubectl create secret docker-registry ecr-registry -n jenkins \
  --docker-server=848853684735.dkr.ecr.eu-west-1.amazonaws.com \
  --docker-username=AWS \
  --docker-password=$(aws ecr get-login-password --region eu-west-1) \
  --dry-run=client -o yaml | kubectl apply -f -
```

#### Case 4: Git clone failed

```bash
# Test Git access
kubectl run git-test --rm -it --restart=Never \
  --image=bitnami/git -n jenkins -- \
  git ls-remote https://github.com/PotoMitan/stoa.git

# Check GitLab token
kubectl get secret gitlab-credentials -n jenkins -o jsonpath='{.data.token}' | base64 -d
```

#### Case 5: Insufficient resources

```bash
# Check resources
kubectl top pods -n jenkins

# Increase limits
kubectl patch deployment jenkins -n jenkins --type=json -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "4Gi"},
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/cpu", "value": "2"}
]'
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] Jenkins master accessible
- [ ] Agents connected
- [ ] Queue empty or processing
- [ ] New build passes
- [ ] No errors in logs

### Verification Commands

```bash
# Check Jenkins status
curl -s https://jenkins.gostoa.dev/api/json | jq .mode

# Check agents
curl -s -u admin:$JENKINS_TOKEN \
  "https://jenkins.gostoa.dev/computer/api/json" | \
  jq '.computer[] | select(.offline == false) | .displayName'

# Trigger a test build
curl -X POST -u admin:$JENKINS_TOKEN \
  "https://jenkins.gostoa.dev/job/test-pipeline/build"
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | CI/CD Team | If critical pipeline blocked | Slack `#cicd-team` |
| L3 | Platform Team | Infrastructure issue | @platform-team |

---

## 6. Prevention

### Recommended Monitoring

```yaml
groups:
  - name: jenkins
    rules:
      - alert: JenkinsBuildStuck
        expr: jenkins_job_building_duration_seconds > 3600
        for: 10m
        labels:
          severity: medium
        annotations:
          summary: "Jenkins build stuck for {{ $labels.job }}"

      - alert: JenkinsQueueBacklog
        expr: jenkins_queue_size_value > 5
        for: 15m
        labels:
          severity: warning
```

### Best Practices

1. **Timeouts** on each pipeline stage
2. **Automatic cleanup** of old builds
3. **Health checks** on agents
4. **Alerts** on build duration
5. **Retry logic** for network operations

---

## 7. References

- [Jenkins Administration](https://www.jenkins.io/doc/book/managing/)
- [Pipeline Best Practices](https://www.jenkins.io/doc/book/pipeline/pipeline-best-practices/)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2024-12-28 | Platform Team | Initial creation |
