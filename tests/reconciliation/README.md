# webMethods GitOps Reconciliation Tests

> **Automated test suite for validating GitOps reconciliation**
>
> Ensures webMethods Gateway can be automatically restored from Git source of truth.

---

## Quick Start

```bash
# Set required credentials
export WM_ADMIN_PASSWORD="your-gateway-password"
export AWX_TOKEN="your-awx-token"

# Run all tests
./scripts/test-reconciliation.sh --env dev --scenario all

# Run specific scenario
./scripts/test-reconciliation.sh --scenario crash

# Quick state validation
./scripts/validate-state.sh
```

---

## Test Scenarios

| Scenario | Description | Target |
|----------|-------------|--------|
| **crash** | Delete all APIs, verify full recovery | RTO < 5 min |
| **drift** | Modify API directly, verify correction | Auto-fix |
| **add** | Create API via Git, verify creation | Idempotent |
| **delete** | Remove API from Git, verify deletion | Orphan cleanup |

---

## Structure

```
tests/reconciliation/
├── README.md                    # This file
├── gitlab-ci.yml                # CI pipeline
├── scripts/
│   ├── test-reconciliation.sh   # Main test script
│   └── validate-state.sh        # Quick state check
└── docs/
    └── TEST-PLAN.md             # Detailed test plan
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `WM_ADMIN_PASSWORD` | Yes | - | webMethods admin password |
| `AWX_TOKEN` | Yes | - | AWX API token |
| `ENV` | No | `dev` | Target environment |
| `WM_GATEWAY_URL` | No | `http://apim-gateway:9072` | Gateway API URL |
| `AWX_HOST` | No | `https://awx.stoa.cab-i.com` | AWX host |
| `AWX_JOB_TEMPLATE_ID` | No | `42` | AWX Job Template ID |
| `GITOPS_REPO` | No | `/tmp/stoa-gitops` | GitOps repository path |

---

## Usage

### Manual Testing

```bash
# Full test suite
./scripts/test-reconciliation.sh --scenario all

# Individual scenarios
./scripts/test-reconciliation.sh --scenario crash
./scripts/test-reconciliation.sh --scenario drift
./scripts/test-reconciliation.sh --scenario add
./scripts/test-reconciliation.sh --scenario delete

# Different environment
./scripts/test-reconciliation.sh --env staging --scenario all
```

### CI/CD Integration

Add to your `.gitlab-ci.yml`:

```yaml
include:
  - local: 'tests/reconciliation/gitlab-ci.yml'
```

Or schedule nightly runs in GitLab:
- **CI/CD > Schedules > New schedule**
- Cron: `0 2 * * *` (2 AM daily)

---

## Expected Output

```
════════════════════════════════════════════════════════════
  webMethods GitOps Reconciliation Test Suite
════════════════════════════════════════════════════════════

Configuration:
  Environment: dev
  Scenario: all
  Gateway URL: http://apim-gateway:9072
  AWX Host: https://awx.stoa.cab-i.com

[INFO] Checking prerequisites...
[OK] Gateway connectivity OK
[OK] AWX connectivity OK

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
.....
[OK] Job completed successfully in 45s
[INFO] Step 5: Verifying API recovery...
[OK] All 5 APIs recovered!
[OK] RTO (Recovery Time Objective): 45s

...

════════════════════════════════════════════════════════════
  Test Results Summary
════════════════════════════════════════════════════════════

Results:
  crash: PASSED
  drift: PASSED
  add: PASSED
  delete: PASSED

Passed: 4
Failed: 0

[OK] All tests passed!
```

---

## Acceptance Criteria

| Criteria | Target | Validation |
|----------|--------|------------|
| APIs restored after crash | 100% | Scenario 1 |
| RTO (Recovery Time) | < 5 min | Scenario 1 |
| Drift auto-corrected | Yes | Scenario 2 |
| No manual intervention | 100% | All scenarios |
| Idempotent execution | Yes | Multiple runs |

---

## Links

- [CAB-367 — GitOps Reconciliation](https://linear.app/hlfh-workspace/issue/CAB-367)
- [Test Plan](docs/TEST-PLAN.md)
- [Ansible Playbook](../../ansible/reconcile-webmethods/)
- [ArgoCD Integration](../../argocd/hooks/)
