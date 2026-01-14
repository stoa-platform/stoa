# Reconciliation Test Plan

> **CAB-367 — Task 4: Reconciliation Testing**
>
> Validate that webMethods Gateway can be automatically restored from Git source of truth.

---

## Test Objectives

| Objective | Description | Target |
|-----------|-------------|--------|
| **RTO** | Recovery Time Objective | < 5 minutes |
| **RPO** | Recovery Point Objective | 0 (Git = source of truth) |
| **Automation** | No manual intervention | 100% |
| **Idempotency** | Multiple runs = same result | Yes |

---

## Test Scenarios

### Scenario 1: Gateway Crash Recovery

**Purpose**: Validate full recovery after complete API loss

**Steps**:
1. Record current Gateway state (API count)
2. Delete all APIs (simulate crash/corruption)
3. Trigger reconciliation
4. Measure recovery time
5. Verify all APIs restored

**Acceptance Criteria**:
- All APIs recreated
- RTO < 5 minutes
- No manual intervention

---

### Scenario 2: Drift Detection & Correction

**Purpose**: Validate that unauthorized changes are reverted

**Steps**:
1. Select an existing API
2. Modify it directly on Gateway (create drift)
3. Trigger reconciliation
4. Verify original state restored

**Acceptance Criteria**:
- Drift detected
- Original configuration restored
- Change logged

---

### Scenario 3: Add New API via Git

**Purpose**: Validate GitOps workflow for new APIs

**Steps**:
1. Create new API YAML in Git
2. Trigger reconciliation
3. Verify API created on Gateway
4. Cleanup

**Acceptance Criteria**:
- API created automatically
- Configuration matches YAML
- Policies applied

---

### Scenario 4: Delete API via Git

**Purpose**: Validate orphan cleanup

**Steps**:
1. Create temporary API
2. Delete YAML from Git
3. Trigger reconciliation
4. Verify API removed from Gateway

**Acceptance Criteria**:
- Orphan detected
- API deleted from Gateway
- Deletion logged

---

## Test Environment

### Prerequisites

| Component | Requirement |
|-----------|-------------|
| Kubernetes | Access to cluster with kubectl |
| webMethods | Gateway running with API access |
| AWX | Job Template configured |
| Git | Clone of stoa-gitops repository |

### Environment Variables

```bash
# Required
export WM_ADMIN_PASSWORD="your-password"
export AWX_TOKEN="your-awx-token"

# Optional (with defaults)
export ENV="dev"
export WM_GATEWAY_URL="http://apim-gateway:9072"
export AWX_HOST="https://awx.stoa.cab-i.com"
export AWX_JOB_TEMPLATE_ID="42"
export GITOPS_REPO="/tmp/stoa-gitops"
```

---

## Execution

### Manual Execution

```bash
# Run all scenarios
./scripts/test-reconciliation.sh --env dev --scenario all

# Run specific scenario
./scripts/test-reconciliation.sh --scenario crash
./scripts/test-reconciliation.sh --scenario drift
./scripts/test-reconciliation.sh --scenario add
./scripts/test-reconciliation.sh --scenario delete

# Quick state validation
./scripts/validate-state.sh
```

### CI Execution

```bash
# GitLab CI
gitlab-runner exec docker test-reconciliation

# GitHub Actions (local)
act -j test-reconciliation
```

---

## Expected Results

### Scenario 1: Crash Recovery

```
════════════════════════════════════════════════════════════
  SCENARIO 1: Gateway Crash Recovery
════════════════════════════════════════════════════════════

[INFO] Step 1: Recording current Gateway state...
[INFO] Found 5 APIs on Gateway
[INFO] Step 2: Simulating crash by deleting all APIs...
.....
[OK] All APIs deleted (simulating crash)
[INFO] Step 3: Triggering reconciliation...
[INFO] Step 4: Waiting for reconciliation (Job ID: 123)...
..........
[OK] Job completed successfully in 45s
[INFO] Step 5: Verifying API recovery...
[OK] All 5 APIs recovered!
[OK] RTO (Recovery Time Objective): 45s
```

### Scenario 2: Drift Detection

```
════════════════════════════════════════════════════════════
  SCENARIO 2: Drift Detection & Correction
════════════════════════════════════════════════════════════

[INFO] Step 1: Selecting an API to modify...
[INFO] Selected API: crm-api (ID: abc123)
[INFO] Step 2: Creating drift by modifying API description...
[OK] API modified with drift marker
[INFO] Step 3: Triggering reconciliation...
.....
[INFO] Step 4: Verifying drift correction...
[OK] Drift corrected! Description restored from Git
```

---

## Metrics to Collect

| Metric | Description | Target |
|--------|-------------|--------|
| `reconciliation_duration_seconds` | Time to complete reconciliation | < 300s |
| `apis_created_total` | Number of APIs created | Matches Git |
| `apis_updated_total` | Number of APIs updated | 0 (after initial sync) |
| `apis_deleted_total` | Number of orphans deleted | 0 (normal state) |
| `drift_detected_total` | Number of drifts detected | 0 (normal state) |

---

## Troubleshooting

### Test fails to connect to Gateway

```bash
# Check Gateway pod
kubectl get pods -n stoa-system -l app=apim-gateway

# Check Gateway service
kubectl get svc -n stoa-system apim-gateway

# Port forward for local testing
kubectl port-forward -n stoa-system svc/apim-gateway 9072:9072
```

### AWX job fails to launch

```bash
# Check AWX connectivity
curl -s "${AWX_HOST}/api/v2/ping/" \
  -H "Authorization: Bearer ${AWX_TOKEN}"

# List job templates
curl -s "${AWX_HOST}/api/v2/job_templates/" \
  -H "Authorization: Bearer ${AWX_TOKEN}" | jq '.results[] | {id, name}'
```

### Reconciliation timeout

```bash
# Check AWX job logs
curl -s "${AWX_HOST}/api/v2/jobs/${JOB_ID}/stdout/" \
  -H "Authorization: Bearer ${AWX_TOKEN}"

# Check Ansible playbook locally
ansible-playbook reconcile-webmethods.yml -e "env=dev" -vvv
```

---

## Sign-off Checklist

| Check | Status |
|-------|--------|
| All 4 scenarios pass | |
| RTO < 5 minutes | |
| No manual intervention required | |
| Logs available in AWX | |
| Metrics exported to Prometheus | |
| Documentation updated | |

---

## References

- [CAB-367 — GitOps Reconciliation](https://linear.app/hlfh-workspace/issue/CAB-367)
- [Ansible Playbook](../../ansible/reconcile-webmethods/)
- [ArgoCD Integration](../../argocd/hooks/)
