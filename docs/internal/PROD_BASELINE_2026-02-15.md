# PROD Baseline — 2026-02-15 (Code Freeze)

> Captured before code freeze (18h). Reference state for demo day (24/02).
> If anything drifts during off period (16-22 fev), compare against this file.

## 1. Git State

| Field | Value |
|-------|-------|
| Branch | `main` |
| HEAD commit | `a5ef13ce` — `docs: sync plan.md with latest Linear cycle tickets` |
| Full SHA | `a5ef13ce0adcf48e8ac3a2d7ab87b8fdb276a368` |
| Last merge | PR #480 — `perf(gateway): arena k6 level 3 — ramp-up scenario + CI95 latency bars` |

## 2. Cluster Info (OVH MKS — GRA9)

| Node | Status | K8s Version | CPU | RAM |
|------|--------|-------------|-----|-----|
| stoa-pool-node-6d55d6 | Ready | v1.34.2 | 4 | ~14 Gi |
| stoa-pool-node-b6aaa7 | Ready | v1.34.2 | 4 | ~14 Gi |
| stoa-pool-node-f7243b | Ready | v1.34.2 | 4 | ~14 Gi |

**3 nodes, 12 vCPU, ~42 Gi RAM total**

## 3. Pods & Images (stoa-system)

### Core Services

| Service | Replicas | Image | Status | Restarts |
|---------|----------|-------|--------|----------|
| control-plane-api | 2/2 | `ghcr.io/.../control-plane-api:dev-latest` | Running | 0 |
| control-plane-ui | 2/2 | `ghcr.io/.../control-plane-ui:dev-4361fea...` | Running | 0 |
| stoa-portal | 2/2 | `ghcr.io/.../portal:dev-0a2ae1d...` | Running | 0 |
| stoa-gateway | 2/2 | `ghcr.io/.../stoa-gateway:latest` | Running | 0 |
| stoa-operator | 1/1 | `ghcr.io/.../stoa-operator:latest` (v0.3.0) | Running | 0 |
| keycloak | 1/1 | `ghcr.io/.../keycloak:latest` | Running | 0 |

### Data & Messaging

| Service | Replicas | Image | Status | Restarts |
|---------|----------|-------|--------|----------|
| redpanda | 1/1 | `redpandadata/redpanda:v24.3.1` | Running | 0 |
| openldap | 1/1 | `osixia/openldap:1.5.0` | Running | 0 |

### Arena (Benchmark Lab)

| Service | Replicas | Image | Status | Restarts |
|---------|----------|-------|--------|----------|
| echo-backend | 1/1 | `nginx-unprivileged:1.27-alpine` | Running | 0 |
| kong-arena | 1/1 | `kong:3.9-ubuntu` | Running | 15 |
| gravitee-arena-mongo | 1/1 | `mongo:7.0` | Running | 0 |
| gravitee-arena-gw | 0/0 | (scaled down) | — | — |
| gravitee-arena-mgmt | 0/0 | (scaled down) | — | — |

### CronJobs

| CronJob | Status | Notes |
|---------|--------|-------|
| gateway-arena | Last: 13:00 UTC | FailureTarget on last run |
| traffic-generator | Running | 30-min schedule, completing normally |

## 4. Deployment Replicas

| Deployment | Ready | Desired |
|------------|-------|---------|
| control-plane-api | 2 | 2 |
| control-plane-ui | 2 | 2 |
| stoa-portal | 2 | 2 |
| stoa-gateway | 2 | 2 |
| stoa-operator | 1 | 1 |
| keycloak | 1 | 1 |
| echo-backend | 1 | 1 |
| kong-arena | 1 | 1 |

## 5. ArgoCD State

| Application | Sync | Health | Revision |
|-------------|------|--------|----------|
| stoa-gateway | Synced | Healthy | `48379f1` |

ArgoCD pods: 7/7 Running (namespace `argocd`), age 2d17h, zero restarts.

## 6. Ingress Routes (TLS)

| Host | Service |
|------|---------|
| `api.gostoa.dev` | stoa-control-plane-api |
| `auth.gostoa.dev` | keycloak |
| `console.gostoa.dev` | control-plane-ui |
| `mcp.gostoa.dev` | stoa-gateway |
| `portal.gostoa.dev` | stoa-portal |
| `pushgateway.gostoa.dev` | pushgateway (monitoring) |

## 7. Health Checks (Public Endpoints)

| Endpoint | Status | Response |
|----------|--------|----------|
| `https://api.gostoa.dev/health` | 200 | `{"status":"healthy","version":"2.0.0"}` |
| `https://mcp.gostoa.dev/health` | 200 | `OK` |
| `https://portal.gostoa.dev` | 200 | HTML |
| `https://console.gostoa.dev` | 200 | HTML |
| `https://auth.gostoa.dev/realms/stoa/.well-known/openid-configuration` | 200 | OIDC config |

**All 5 public endpoints healthy.**

## 8. Keycloak

### Realms (7)

| Realm | Enabled | Purpose |
|-------|---------|---------|
| master | Yes | Admin |
| stoa | Yes | Main platform realm |
| demo-org-alpha | Yes | Demo org (Oasis) |
| demo-org-beta | Yes | Demo org |
| demo-org-gamma | Yes | Demo org |
| idp-source-alpha | Yes | External IdP source |
| idp-source-beta | Yes | External IdP source |

### Clients in `stoa` Realm (9)

| Client ID | Enabled | Public | Purpose |
|-----------|---------|--------|---------|
| acme-corp-api-consumer-001 | Yes | No | Demo consumer |
| argocd | Yes | No | ArgoCD SSO |
| control-plane-api | Yes | No | Backend API |
| control-plane-ui | Yes | Yes | Console SPA |
| opensearch-dashboards | Yes | Yes | OpenSearch OIDC |
| stoa-mcp-gateway | Yes | No | MCP Gateway auth |
| stoa-observability | Yes | No | Grafana OIDC |
| stoa-portal | Yes | Yes | Portal SPA |
| stoa-test-client | Yes | Yes | Test client |

## 9. OpenSearch

| Field | Value |
|-------|-------|
| Cluster name | `stoa-cluster` |
| Status | **yellow** (expected: 1-node cluster, replicas unassigned) |
| Nodes | 1 |
| Active primary shards | 15 |
| Unassigned shards | 6 (replica shards, no second node) |
| Active shards % | 71.4% |

### Indices

| Index | Health | Docs | Size |
|-------|--------|------|------|
| stoa-logs-2026.02.15 | green | 9,031,040 | 319 MB |
| stoa-logs-2026.02.14 | green | 17,789,318 | 601 MB |
| stoa-logs-2026.02.13 | green | 14,011 | 886 KB |
| stoa-logs-2026.02.12 | green | 72 | 57 KB |
| stoa-errors-2026.02.14 | yellow | 53 | 46 KB |
| audit | yellow | 198,760 | 78.5 MB |
| security-auditlog-2026.02.15 | yellow | 7 | 103 KB |
| security-auditlog-2026.02.14 | yellow | 13 | 76 KB |
| security-auditlog-2026.02.13 | yellow | 13 | 84 KB |
| security-auditlog-2026.02.12 | yellow | 5,135 | 1.2 MB |

**Total log volume**: ~1 GB. Traffic generator active (9M+ entries on Feb 15 alone).

## 10. Redpanda (Kafka)

### Topics (7)

| Topic | Partitions | Replicas |
|-------|------------|----------|
| audit-log | 1 | 1 |
| deploy-requests | 1 | 1 |
| gateway-sync-requests | 1 | 1 |
| stoa.errors | 1 | 1 |
| stoa.errors.snapshots | 1 | 1 |
| stoa.metering | 1 | 1 |
| tenant-events | 1 | 1 |

### Consumer Groups (3)

| Group | State | Total Lag |
|-------|-------|-----------|
| deployment-worker | Stable | 0 |
| error-snapshot-consumer | Stable | 0 |
| sync-engine | Stable | 0 |

**All consumer groups healthy, zero lag.**

## 11. STOA Operator

| Metric | Value |
|--------|-------|
| `stoa_operator_up` | 1.0 |
| Version | 0.3.0 |
| Pod | Running, 0 restarts |

Features active: GWI/GWB reconciliation, drift detection timers, Prometheus /metrics endpoint.

## 12. CRDs (6)

| CRD | Group |
|-----|-------|
| gatewaybindings | gostoa.dev |
| gatewayinstances | gostoa.dev |
| subscriptions | gostoa.dev |
| tenants | gostoa.dev |
| tools | gostoa.dev |
| toolsets | gostoa.dev |

## 13. Monitoring Stack

| Component | Status | Age |
|-----------|--------|-----|
| prometheus-grafana | 3/3 Running | 19h |
| prometheus-operator | 1/1 Running | 3d23h |
| kube-state-metrics | 1/1 Running | 3d23h |
| prometheus | 2/2 Running | 3d23h |
| node-exporter | 3/3 Running (per node) | 3d23h |
| pushgateway | 1/1 Running | 3d12h |

## 14. Arena Benchmark Scores (VPS — co-located)

| Gateway | Score | CI95 Lower | CI95 Upper | StdDev | Availability |
|---------|-------|------------|------------|--------|--------------|
| **stoa-vps** | **97.25** | 95.88 | 98.24 | 0.74 | 100% |
| **kong-vps** | **94.41** | 91.75 | 100 | 2.77 | 100% |

### Key Latencies (VPS, p50 in ms)

| Scenario | STOA | Kong |
|----------|------|------|
| sequential | 1.2 | 1.0 |
| burst_10 | 6.0 | 5.9 |
| burst_50 | 6.5 | 4.4 |
| burst_100 | 12.1 | 9.1 |
| sustained | 0.9 | 1.0 |
| health | 6.3 | 7.0 |

**Note**: K8s arena CronJob had a FailureTarget on last run. VPS scores are the authoritative benchmark.

## 15. Services Summary

| Service | URL | Status | Version |
|---------|-----|--------|---------|
| Control Plane API | api.gostoa.dev | Healthy | 2.0.0 |
| Console | console.gostoa.dev | Healthy | — |
| Portal | portal.gostoa.dev | Healthy | — |
| MCP Gateway | mcp.gostoa.dev | Healthy | Rust |
| Keycloak | auth.gostoa.dev | Healthy | — |
| Grafana | console.gostoa.dev/grafana | Healthy | — |
| OpenSearch | opensearch.gostoa.dev | Yellow (expected) | — |
| ArgoCD | argocd.gostoa.dev | Synced+Healthy | — |

## 16. Known Issues at Freeze

| Issue | Severity | Impact |
|-------|----------|--------|
| OpenSearch yellow status | Low | Expected: 1-node cluster, replica shards unassigned |
| Kong-arena restarts (15) | Low | Arena-only, not production traffic |
| Gravitee arena scaled to 0 | Info | Intentionally disabled |
| K8s arena CronJob failing | Low | VPS scores are authoritative |
| Traffic generator Error pod | Low | Old run (2d17h), succeeded runs following |

## Freeze Checklist

- [x] All core pods Running (0 CrashLoopBackOff)
- [x] All 5 public endpoints returning 200
- [x] ArgoCD Synced + Healthy
- [x] Redpanda zero lag on all consumer groups
- [x] Operator up (stoa_operator_up = 1.0)
- [x] Monitoring stack complete (Prometheus, Grafana, node-exporters)
- [x] 6 CRDs installed
- [x] Keycloak 7 realms, 9 clients in stoa realm
- [x] Git HEAD documented
- [x] Arena baseline captured

**Verdict: PROD is GO for freeze.**
