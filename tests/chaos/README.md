# STOA Platform Chaos Testing

> **Phase**: 9.5 - Production Readiness
> **Ticket**: CAB-109
> **Framework**: LitmusChaos 3.0
> **Last Updated**: 2026-01-05

## Overview

This directory contains chaos engineering experiments for the STOA Platform. Chaos testing validates the platform's resilience by intentionally injecting failures.

## Quick Start

### Install Litmus

```bash
# Install LitmusChaos
./scripts/install-litmus.sh install

# Verify installation
./scripts/install-litmus.sh verify
```

### Run a Single Experiment

```bash
# Delete Control-Plane API pods
kubectl apply -f tests/chaos/experiments/pod-delete-api.yaml

# Watch experiment status
kubectl get chaosengine -n stoa-system -w

# Check results
kubectl describe chaosengine api-pod-delete -n stoa-system
```

### Run Full Chaos Suite

```bash
# Run all experiments (staging only!)
kubectl apply -f tests/chaos/workflows/full-chaos-suite.yaml

# Monitor workflow
kubectl get chaosworkflow -n litmus -w
```

## Experiments

### Pod Delete Experiments

| Experiment | Target | Duration | Expected Outcome |
|------------|--------|----------|------------------|
| `pod-delete-api.yaml` | Control-Plane API | 30s | Auto-recovery, no downtime |
| `pod-delete-mcp.yaml` | MCP Gateway | 30s | Auto-recovery, AI tools resume |
| `pod-delete-vault.yaml` | Vault | 30s | Auto-unseal via KMS |
| `pod-delete-awx.yaml` | AWX | 30s | Jobs resume after recovery |

### Network Experiments

| Experiment | Target | Effect | Expected Outcome |
|------------|--------|--------|------------------|
| `network-latency.yaml` | API + MCP | 500ms latency | Timeouts handled gracefully |

### Resource Stress Experiments

| Experiment | Target | Effect | Expected Outcome |
|------------|--------|--------|------------------|
| `cpu-stress.yaml` | API + MCP | 80% CPU | HPA scales, response OK |
| `cpu-stress.yaml` | Memory stress | 500MB | No OOM, graceful handling |

## Experiment Structure

Each experiment follows this structure:

```yaml
apiVersion: litmuschaos.io/v1alpha1
kind: ChaosEngine
metadata:
  name: experiment-name
  namespace: target-namespace
spec:
  engineState: "active"
  appinfo:
    appns: target-namespace
    applabel: "app.kubernetes.io/name=target-app"
    appkind: deployment
  chaosServiceAccount: litmus-admin
  experiments:
    - name: chaos-type
      spec:
        components:
          env:
            - name: PARAM
              value: "value"
        probe:
          - name: health-check
            type: httpProbe
            # ...
```

## Probes

Probes validate system behavior during chaos:

| Probe Type | Usage |
|------------|-------|
| `httpProbe` | Health endpoint checks |
| `cmdProbe` | Custom command validation |
| `k8sProbe` | Kubernetes resource checks |

### Probe Modes

- `Continuous`: Run throughout experiment
- `Edge`: Run at start and end
- `EOT`: Run at End of Test only
- `OnChaos`: Run only during chaos injection

## Running Experiments

### Prerequisites

1. Litmus installed (`./scripts/install-litmus.sh install`)
2. RBAC configured (ServiceAccount: `litmus-admin`)
3. Target namespace accessible

### Manual Execution

```bash
# 1. Apply experiment
kubectl apply -f tests/chaos/experiments/pod-delete-api.yaml

# 2. Monitor
watch kubectl get chaosengine -n stoa-system

# 3. Check result
kubectl get chaosresult -n stoa-system

# 4. Cleanup
kubectl delete chaosengine api-pod-delete -n stoa-system
```

### Automated Workflow

```bash
# Run full suite (weekly scheduled)
kubectl apply -f tests/chaos/workflows/full-chaos-suite.yaml

# Run quick test (manual)
kubectl apply -f tests/chaos/workflows/stoa-quick-chaos.yaml
```

## Environment Restrictions

| Environment | Allowed Experiments | Notes |
|-------------|---------------------|-------|
| **Dev** | All | Full chaos testing |
| **Staging** | All | Weekly automated runs |
| **Production** | **NONE** | Chaos testing prohibited |

## Results Interpretation

### Experiment Status

| Status | Meaning |
|--------|---------|
| `Running` | Experiment in progress |
| `Completed` | Experiment finished |
| `Stopped` | Manually stopped |
| `Aborted` | Failed due to error |

### Experiment Verdict

| Verdict | Meaning | Action |
|---------|---------|--------|
| `Pass` | All probes passed | System is resilient |
| `Fail` | One or more probes failed | Investigate and fix |
| `Awaited` | Still running | Wait for completion |

### Viewing Results

```bash
# Get all results
kubectl get chaosresult -A

# Describe specific result
kubectl describe chaosresult api-pod-delete-pod-delete -n stoa-system

# JSON output for parsing
kubectl get chaosresult -n stoa-system -o json | jq '.items[].status'
```

## Troubleshooting

### Experiment Stuck in Running

```bash
# Check chaos runner logs
kubectl logs -l app=chaos-runner -n stoa-system

# Force stop experiment
kubectl patch chaosengine api-pod-delete -n stoa-system --type merge -p '{"spec":{"engineState":"stop"}}'
```

### Probes Failing

1. Check target service is actually healthy:
   ```bash
   kubectl exec -it deploy/control-plane-api -n stoa-system -- curl localhost:8000/v1/health
   ```

2. Verify probe timeout is sufficient
3. Check network policies aren't blocking

### Permission Denied

```bash
# Verify RBAC
kubectl auth can-i delete pods -n stoa-system --as=system:serviceaccount:litmus:litmus-admin

# Reapply RBAC if needed
./scripts/install-litmus.sh install
```

## Best Practices

### Do's

- ✅ Run experiments in staging first
- ✅ Start with small blast radius (low `PODS_AFFECTED_PERC`)
- ✅ Monitor SLO metrics during chaos
- ✅ Document findings and fixes

### Don'ts

- ❌ Run chaos in production without approval
- ❌ Run during business hours initially
- ❌ Ignore failed experiments
- ❌ Run multiple experiments simultaneously

## Integration with CI/CD

### GitHub Actions

```yaml
# .github/workflows/chaos-test.yml
name: Chaos Testing
on:
  schedule:
    - cron: '0 2 * * 6'  # Saturday 2 AM
  workflow_dispatch:

jobs:
  chaos:
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Configure kubectl
        uses: azure/k8s-set-context@v3
        with:
          kubeconfig: ${{ secrets.STAGING_KUBECONFIG }}

      - name: Run Chaos Suite
        run: |
          kubectl apply -f tests/chaos/workflows/full-chaos-suite.yaml
          kubectl wait --for=condition=complete workflow/stoa-full-chaos-suite -n litmus --timeout=1h

      - name: Collect Results
        if: always()
        run: |
          kubectl get chaosresult -A -o yaml > chaos-results.yaml

      - name: Upload Results
        uses: actions/upload-artifact@v3
        with:
          name: chaos-results
          path: chaos-results.yaml
```

## Related Documentation

- [LitmusChaos Documentation](https://litmuschaos.io/docs/)
- [STOA SLO/SLA](../../docs/SLO-SLA.md)
- [Load Testing](../load/README.md)
- [Security Testing](../security/README.md)

## Experiment Ideas for Future

- [ ] Kafka broker failure
- [ ] DNS resolution failure
- [ ] Certificate expiry simulation
- [ ] Database connection pool exhaustion
- [ ] Multi-region failover
