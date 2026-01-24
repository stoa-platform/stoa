# MCP Gateway Migration Runbook: Python to Rust

## Overview

This runbook documents the progressive migration from the Python MCP Gateway to the Rust implementation using shadow mode and canary deployment strategies.

**Objective**: Zero-downtime migration with instant rollback capability.

## Architecture

```
                         ┌─────────────────────────┐
                         │      Ingress/LB         │
                         │   (traffic splitting)   │
                         └───────────┬─────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    │                │                │
                    ▼                ▼                ▼
            ┌───────────┐    ┌───────────┐    ┌───────────┐
            │  Python   │    │   Rust    │    │  Shadow   │
            │ Gateway   │    │ Gateway   │    │ Comparator│
            │  (prod)   │    │ (canary)  │    │           │
            └───────────┘    └───────────┘    └───────────┘
```

## Prerequisites

- [ ] Rust gateway deployed and passing health checks
- [ ] Prometheus rules applied
- [ ] Grafana dashboard imported
- [ ] On-call engineer notified
- [ ] Rollback script tested

## Phase 1: Shadow Mode

Shadow mode mirrors all MCP requests to the Rust gateway without affecting production traffic. Python responses are authoritative.

### Enable Shadow Mode

```bash
# Set environment variables
kubectl set env deployment/mcp-gateway-python -n stoa-system \
  SHADOW_MODE_ENABLED=true \
  SHADOW_RUST_GATEWAY_URL=http://mcp-gateway-rust:8080

# Verify
kubectl logs -l app=mcp-gateway-python -n stoa-system | grep "Shadow mode"
```

### Monitor Shadow Mode

**Dashboard**: Grafana → "MCP Gateway Migration: Python to Rust"

**Key Metrics**:
| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| Shadow Match Rate | > 99.9% | < 99.9% |
| Shadow Error Rate | < 1% | > 1% |
| Shadow Timeout Rate | < 5% | > 5% |

**Prometheus Queries**:
```promql
# Match rate
sum(rate(mcp_shadow_match_total{result="match"}[5m])) / sum(rate(mcp_shadow_match_total[5m]))

# Error rate
sum(rate(mcp_shadow_requests_total{status="error"}[5m])) / sum(rate(mcp_shadow_requests_total[5m]))
```

### Investigate Mismatches

```bash
# View mismatch logs
kubectl logs -l app=mcp-gateway-python -n stoa-system | grep "Shadow MISMATCH"

# Filter by path
kubectl logs -l app=mcp-gateway-python -n stoa-system | grep "Shadow MISMATCH" | jq '.path'
```

**Common Mismatch Causes**:
1. **Timestamp differences**: Already normalized, shouldn't cause mismatches
2. **Ordering differences**: JSON object key ordering
3. **Precision differences**: Floating point precision
4. **Missing fields**: Response schema differences

### Disable Shadow Mode

```bash
kubectl set env deployment/mcp-gateway-python -n stoa-system \
  SHADOW_MODE_ENABLED=false
```

### Shadow Mode Duration

**Minimum**: 7 days with > 99.9% match rate

## Phase 2: Canary Deployment

After successful shadow mode validation, gradually shift production traffic to the Rust gateway.

### Prerequisites Checklist

- [ ] Shadow match rate > 99.9% for 7 days
- [ ] No critical alerts in last 48h
- [ ] On-call engineer aware and available
- [ ] Rollback script verified working
- [ ] Business-hours deployment window

### Apply Canary Ingress

```bash
kubectl apply -f k8s/ingress/mcp-gateway-canary.yaml
```

### Ramp-up Schedule

| Day | Weight | Duration | Go/No-Go Criteria |
|-----|--------|----------|-------------------|
| 1   | 1%     | 48h      | Error rate ≤ 0.1%, p99 ≤ 1.5x Python |
| 3   | 5%     | 48h      | Same |
| 5   | 10%    | 48h      | Same |
| 7   | 25%    | 48h      | Same |
| 9   | 50%    | 48h      | Same |
| 11  | 100%   | -        | Rust is primary |

### Update Canary Weight

```bash
# Increase to 1%
./scripts/canary-update.sh 1

# Check current weight
kubectl get ingress mcp-gateway-canary -n stoa-system \
  -o jsonpath='{.metadata.annotations.nginx\.ingress\.kubernetes\.io/canary-weight}'
```

### Go/No-Go Criteria

Before each weight increase, verify:

1. **Error Rate**: `mcp:rust_gateway_error_rate:5m < 0.001`
2. **Latency**: `mcp:rust_gateway_p99_latency:5m < 1.5 * mcp:python_gateway_p99_latency:5m`
3. **No Critical Alerts**: Check Alertmanager
4. **User Complaints**: Check support channels

```bash
# Quick check
kubectl exec -it prometheus-0 -n stoa-monitoring -- \
  promtool query instant http://localhost:9090 'mcp:rust_gateway_ready_for_traffic'
```

### Rollback

**Immediate rollback** if any of these conditions:
- Error rate > 0.1%
- p99 latency > 2x Python
- Critical alert fires
- User-reported issues

```bash
# Emergency rollback
./scripts/canary-rollback.sh
```

## Alerts & Escalation

| Alert | Severity | Action |
|-------|----------|--------|
| MCPShadowMismatchRateHigh | Warning | Investigate logs, pause ramp-up |
| MCPShadowErrorRateHigh | Warning | Check Rust gateway health |
| MCPRustGatewayErrorRateHigh | Critical | **Immediate rollback** |
| MCPRustGatewayLatencyHigh | Warning | Pause ramp-up, investigate |
| MCPRustGatewayDown | Critical | **Immediate rollback** |

### Escalation Path

1. **L1**: On-call engineer - execute rollback
2. **L2**: Platform team lead - investigate root cause
3. **L3**: Rust gateway maintainer - fix issues

## Post-Migration

### Cleanup (After 14 Days at 100%)

1. Remove Python gateway deployment:
```bash
kubectl delete deployment mcp-gateway-python -n stoa-system
kubectl delete service mcp-gateway-python -n stoa-system
```

2. Update primary ingress to point to Rust:
```bash
kubectl patch ingress mcp-gateway-primary -n stoa-system \
  -p '{"spec":{"rules":[{"host":"mcp.gostoa.dev","http":{"paths":[{"path":"/","pathType":"Prefix","backend":{"service":{"name":"mcp-gateway-rust","port":{"number":8080}}}}]}}]}}'
```

3. Remove canary ingress:
```bash
kubectl delete ingress mcp-gateway-canary -n stoa-system
```

4. Remove shadow mode code (optional, can keep for future migrations)

### Monitoring Retention

Keep migration-specific monitoring for 30 days post-migration for comparison and debugging.

## Troubleshooting

### Shadow requests failing

```bash
# Check Rust gateway health
kubectl exec -it deploy/mcp-gateway-rust -n stoa-system -- curl localhost:8080/health

# Check network connectivity
kubectl exec -it deploy/mcp-gateway-python -n stoa-system -- \
  curl -v http://mcp-gateway-rust:8080/health
```

### High mismatch rate

1. Check specific endpoints:
```bash
kubectl logs -l app=mcp-gateway-python -n stoa-system | \
  grep "Shadow MISMATCH" | jq -r '.path' | sort | uniq -c | sort -rn
```

2. Compare responses manually:
```bash
# Python
curl -X POST https://mcp.gostoa.dev/mcp/v1/tools -H "Content-Type: application/json" -d '...'

# Rust (direct)
kubectl port-forward svc/mcp-gateway-rust 8081:8080 -n stoa-system &
curl -X POST http://localhost:8081/mcp/v1/tools -H "Content-Type: application/json" -d '...'
```

### Canary not receiving traffic

1. Verify ingress:
```bash
kubectl describe ingress mcp-gateway-canary -n stoa-system
```

2. Check nginx controller logs:
```bash
kubectl logs -l app.kubernetes.io/component=controller -n ingress-nginx
```

### Rollback not working

1. Manual weight reset:
```bash
kubectl patch ingress mcp-gateway-canary -n stoa-system \
  -p '{"metadata":{"annotations":{"nginx.ingress.kubernetes.io/canary-weight":"0"}}}'
```

2. Delete canary ingress completely:
```bash
kubectl delete ingress mcp-gateway-canary -n stoa-system
```

## Contacts

| Role | Contact |
|------|---------|
| Platform Team | platform@cab-i.com |
| Rust Gateway Maintainer | rust-team@cab-i.com |
| On-Call | #oncall-platform (Slack) |

## References

- [Shadow Mode Implementation](mcp-gateway/src/middleware/shadow.py)
- [Canary Ingress Config](k8s/ingress/mcp-gateway-canary.yaml)
- [Prometheus Rules](docker/observability/prometheus/rules/mcp-migration-alerts.yaml)
- [Grafana Dashboard](docker/observability/grafana/dashboards/mcp-gateway-migration.json)
