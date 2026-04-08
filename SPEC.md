# Spec: CAB-2009 — Deploy Observability Stack on OVH Prod

> Council: 8.25/10 Go (ticket), 8.5/10 Go (spec).

## Problem

The observability stack is partially deployed on OVH prod. Tempo runs via ArgoCD but OpenSearch was manually helm-installed (no ArgoCD app, no ISM policies, missing index templates). Data Prepper does not exist. Gateway traces reach Tempo but are not indexed in OpenSearch.

## Goal

All three components fully managed by ArgoCD, with end-to-end trace flow: gateway OTEL -> Tempo -> Data Prepper -> OpenSearch, verified within 60s.

## Infrastructure Contract

No API changes. Pure infra. All configs in git (stoa-infra for Helm/ArgoCD, stoa for verification).

### Current Cluster State (verified 2026-04-08)

| Component | Pods | ArgoCD App | Health | Missing |
|-----------|------|------------|--------|---------|
| Tempo | `stoa-tempo-0` Running 23d | `stoa-tempo` Synced+Healthy | OK | Nothing |
| OpenSearch | `opensearch-cluster-master-0` Running 21d | **NONE** (manual helm install) | Yellow (expected, single-node) | ArgoCD app, 2 index templates, ISM policies |
| OpenSearch Dashboards | `opensearch-dashboards-*` Running 21d | **NONE** | OK | ArgoCD app |
| Data Prepper | Not deployed | **NONE** | N/A | Everything |

**OpenSearch has data**: 600K+ security audit events, `stoa-logs` template exists, OIDC configured, security init completed 54d ago.

### What Needs to Be Done

| Phase | Work | Repo | LOC |
|-------|------|------|-----|
| 1 | Tempo — verify only (already done) | N/A | 0 |
| 2a | OpenSearch ArgoCD Application | stoa-infra | ~40 |
| 2b | Apply missing index templates (gateway-logs, audit) | stoa-infra | ~20 |
| 2c | Apply ISM retention policies | stoa-infra | ~30 |
| 3a | Create Data Prepper Helm chart | stoa-infra | ~150 |
| 3b | Data Prepper ArgoCD Application | stoa-infra | ~30 |
| 4 | E2E verification script | stoa | ~250 |

### Data Flow

```
stoa-gateway (OTEL gRPC)
    -> Tempo (monitoring:4317)
    -> Data Prepper (monitoring:21890, OTLP -> OpenSearch sink)
    -> OpenSearch (opensearch:9200, index: trace-analytics-raw)
```

## Acceptance Criteria

- [ ] AC1: Tempo pods Running + Ready in `monitoring` namespace
- [ ] AC2: Tempo OTLP gRPC port 4317 exposed on service
- [ ] AC3: OpenSearch cluster health is Green or Yellow (single-node) in `opensearch` namespace
- [ ] AC4: OpenSearch security init completed (`.opendistro_security` index exists)
- [ ] AC5: OpenSearch index templates exist: `stoa-logs`, `gateway-logs`, `audit`
- [ ] AC6: OpenSearch OIDC configuration present in security config
- [ ] AC7: Data Prepper pods Running in `monitoring` namespace
- [ ] AC8: Data Prepper health endpoint responds on :21890
- [ ] AC9: E2E: trace visible in OpenSearch `trace-analytics-raw` index within 60s of gateway call
- [ ] AC10: ArgoCD Applications for all 3 components show Synced + Healthy
- [ ] AC11: All observability resources managed by ArgoCD (zero manual kubectl apply)
- [ ] AC12: ISM retention policies active (free=7d, pro=90d, enterprise=365d)

## Edge Cases

| Case | Scenario | Expected | Priority |
|------|----------|----------|----------|
| B2-15 memory pressure | 3x15GB nodes, OS 2GB heap | Stay within 4GB total for observability | Must |
| DP before OS ready | Data Prepper starts, OS not responding | Retry with backoff, no CrashLoop | Must |
| Kyverno blocks pod | Missing `privileged: false` | Explicit securityContext on all pods | Must |
| ArgoCD adopts manual install | Existing helm release conflicts | `selfHeal: true` + `prune: true` | Must |
| Single-node Yellow | No replica shards assignable | Accept Yellow for AC3 (expected) | Must |

## Out of Scope

- Kafka OpenSearch connector, Fluent Bit, custom dashboards, alerting rules
- Monitoring the observability stack itself
- Console UI integration with live trace data

## Security Considerations

- [ ] OpenSearch creds via Vault External Secrets
- [ ] OIDC via Keycloak realm `stoa`
- [ ] Data Prepper non-root, `privileged: false`
- [ ] No public ingress for OpenSearch API

## Dependencies

- **stoa-infra**: Helm charts, ArgoCD apps (primary work)
- **Vault**: `stoa/k8s/opensearch` credentials
- **ESO, Keycloak, ArgoCD**: already deployed on cluster
