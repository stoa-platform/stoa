# Runbook: Observability Stack - Troubleshooting

> **Severity**: High
> **Last updated**: 2026-03-07
> **Owner**: Platform Team
> **Linear Issue**: CAB-1689

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `PlatformCUJFailing` | CUJ failure > 30min | Gateway Arena |
| `PlatformVerifyStale` | No verify run > 5min | Platform Health |
| `HighGatewayLatency` | p95 > 2s for 5min | Gateway Unified |

### Observed Behavior

- Gateway logs not appearing in OpenSearch Dashboards
- Grafana dashboards showing "No data" for gateway metrics
- Trace correlation links broken (Loki -> Tempo or Tempo -> Loki)
- Tenant-scoped views returning empty results despite active traffic

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | Tenant admins cannot view API call logs or metrics |
| **APIs** | No impact on API traffic (observability is read-path only) |
| **SLA** | Degraded monitoring capability, slower incident response |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check observability stack pods
kubectl get pods -n stoa-system -l 'app in (opensearch,grafana,loki,tempo,prometheus)'
kubectl get pods -n monitoring

# 2. Check OpenSearch cluster health
kubectl exec -n stoa-system deploy/opensearch -- curl -sk https://localhost:9200/_cluster/health | jq .

# 3. Check Grafana datasource connectivity
kubectl logs -n stoa-system -l app=grafana --tail=50 --since=5m | grep -i error

# 4. Check Loki ingestion
kubectl logs -n stoa-system -l app=loki --tail=50 --since=5m | grep -i error

# 5. Check Tempo trace ingestion
kubectl logs -n stoa-system -l app=tempo --tail=50 --since=5m | grep -i error
```

### Verification Points

- [ ] OpenSearch cluster status is green/yellow (not red)?
- [ ] Grafana pod running and datasources configured?
- [ ] Loki receiving logs from gateway pods?
- [ ] Tempo receiving traces (OTLP endpoint reachable)?
- [ ] Gateway pods have correct log format (JSON)?
- [ ] ISM policies active (indices not bloated)?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| OpenSearch disk full | High | `curl -sk https://localhost:9200/_cat/allocation?v` |
| ISM policy not applied | High | `curl -sk https://localhost:9200/_plugins/_ism/explain/stoa-gw-*` |
| Loki -> Tempo derivedFields misconfigured | Medium | Check Grafana datasource provisioning YAML |
| Gateway not emitting traces | Medium | `kubectl logs -n stoa-system -l app=stoa-gateway --tail=20 \| grep trace_id` |
| DLS role misconfigured (tenant sees no data) | Medium | Check OpenSearch security roles for tenant_id filter |
| OpenSearch index template not applied | Low | `curl -sk https://localhost:9200/_index_template/gateway-logs` |

---

## 3. Resolution

### Immediate Action (mitigation)

> **Objective**: Restore observability visibility

```bash
# If OpenSearch is red (unassigned shards):
kubectl exec -n stoa-system deploy/opensearch -- \
  curl -sk -X POST https://localhost:9200/_cluster/reroute?retry_failed=true

# If Grafana shows "No data" — restart to reload datasources:
kubectl rollout restart -n stoa-system deploy/grafana

# If Loki is not ingesting — check and restart:
kubectl rollout restart -n stoa-system deploy/loki
```

### Corrective Action (fix root cause)

> **Objective**: Fix the root cause

```bash
# Re-apply index templates (if missing):
cd deploy/opensearch/scripts && ./init-opensearch.sh --force

# Re-apply ISM policies (if indices growing unbounded):
cd deploy/opensearch/scripts && ./init-opensearch.sh --force

# Fix DLS role for a tenant (if tenant sees no data):
# Verify the role exists:
kubectl exec -n stoa-system deploy/opensearch -- \
  curl -sk https://localhost:9200/_plugins/_security/api/roles/tenant_reader_TENANT_ID

# Fix trace correlation (derivedFields in Loki datasource):
# Verify provisioning file:
kubectl get configmap -n stoa-system grafana-datasources -o yaml | grep -A5 derivedFields
```

### Rollback if necessary

```bash
# Rollback OpenSearch to previous index template version:
# Templates are versioned — deploy previous ConfigMap:
kubectl apply -f k8s/opensearch/index-templates-configmap.yaml

# Rollback Grafana dashboards:
kubectl apply -f k8s/grafana/dashboards-configmap.yaml
kubectl rollout restart -n stoa-system deploy/grafana
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] OpenSearch cluster health is green
- [ ] Gateway logs visible in OpenSearch Dashboards (last 15 min)
- [ ] Grafana Gateway Unified dashboard shows metrics
- [ ] Grafana Tenant Observability dashboard shows per-tenant data
- [ ] Trace correlation works: click trace_id in Loki -> opens in Tempo
- [ ] Reverse link works: Tempo trace -> Loki logs
- [ ] ISM policies active on all index patterns

### Verification Commands

```bash
# OpenSearch health
kubectl exec -n stoa-system deploy/opensearch -- \
  curl -sk https://localhost:9200/_cluster/health | jq '{status, number_of_nodes, active_shards}'

# Verify recent gateway logs exist
kubectl exec -n stoa-system deploy/opensearch -- \
  curl -sk https://localhost:9200/stoa-gw-*/_count | jq .count

# Verify ISM policies are managing indices
kubectl exec -n stoa-system deploy/opensearch -- \
  curl -sk https://localhost:9200/_plugins/_ism/explain/stoa-gw-* | jq '.total_managed_indices'

# Verify Grafana datasources
kubectl exec -n stoa-system deploy/grafana -- \
  curl -s http://localhost:3000/api/datasources | jq '.[].name'
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | After 15 min without resolution | Slack `#platform-team` |
| L3 | OpenSearch/Grafana community | If blocked on config | GitHub issues |

---

## 6. References

### Grafana Dashboards

- Gateway Unified: `docker/observability/grafana/dashboards/gateway-unified.json` (19 panels)
- Tenant Observability: `docker/observability/grafana/dashboards/tenant-observability.json` (17 panels)

### OpenSearch Configuration

- Index templates: `deploy/opensearch/index-templates/`
- ISM policies: `deploy/opensearch/index-templates/ism-policies.json`
- Security roles (DLS/FLS): `deploy/docker-compose/config/opensearch/security/roles.yml`
- K8s ConfigMaps: `k8s/opensearch/`

### Trace Correlation

- Loki -> Tempo: `derivedFields` in `docker/observability/grafana/provisioning/datasources/prometheus.yml:44-48`
- Tempo -> Loki: `tracesToLogsV2` in same file, lines 72-74

### Related Tickets

| Ticket | Description |
|--------|-------------|
| CAB-1681 | [MEGA] Observability Data Pipeline |
| CAB-1684 | OpenSearch index templates + ISM + DLS/FLS |
| CAB-1688 | Grafana dashboards + trace correlation |

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2026-03-07 | @claude | Initial creation (CAB-1689) |
