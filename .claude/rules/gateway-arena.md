---
globs: "scripts/traffic/arena/**,k8s/arena/**,deploy/vps/bench/**"
---

# Gateway Arena — Benchmark Lab

## Overview

Three-layer continuous verification: L0 (proxy baseline, k6, 30min), L1 (enterprise AI readiness, k6, 1h), L2 (platform CUJs, curl, 15min). All push to Pushgateway → Grafana. Methodology: median of 5 runs (1 warm-up discarded), CI95 confidence intervals.

## Architecture

- **L0**: CronJob `gateway-arena` → `run-arena.sh` → k6 per gateway × 5 runs → `run-arena.py` (scorer) → Pushgateway
- **L1**: CronJob `gateway-arena-enterprise` → `run-arena-enterprise.sh` → k6 → `run-arena-enterprise.py` → Pushgateway
- **L2**: CronJob `gateway-arena-verify` → `run-arena-verify.sh` → curl CUJs → Pushgateway + Healthchecks ping
- **VPS Sidecar**: same image, host cron 30min, pushes to `pushgateway.gostoa.dev` (IP-whitelisted)

## Adding a New Gateway

**K8s**: Add to `GATEWAYS` JSON in `k8s/arena/cronjob-prod.yaml` → update ConfigMap → manual job test.
**VPS**: Add config to `deploy/vps/bench/deploy.sh` → deploy → verify Pushgateway.

## L0 Scoring

Formula: `0.15*Base + 0.25*Burst50 + 0.25*Burst100 + 0.15*Avail + 0.10*Error + 0.10*Consistency`. Scores: >95 excellent, 80-95 good, 60-80 acceptable, <60 investigate. 7 scenarios: warmup, health, sequential(20), burst_10/50/100, sustained(100). Caps: 400ms sequential, 2.5s burst_50, 4s burst_100. Consistency: IQR-based CV.

## Echo Backend (Fair Comparison)

Local nginx echo (static JSON, <1ms) ensures benchmarks measure gateway overhead only.

**K8s**: stoa-k8s (`stoa-gateway.stoa-system.svc`), kong-k8s (`:8000`), gravitee-k8s (`:8082`) — all → echo-backend:8888
**VPS**: stoa-vps, kong-vps, gravitee-vps — all → echo-local:8888 (Docker, same network required)

VPS gotcha: echo container MUST be on gateway's Docker network. STOA SSRF blocklist blocks `localhost` — use container name.

## Deploy

- K8s: `KUBECONFIG=~/.kube/<KUBECONFIG_OVH> ./k8s/arena/deploy.sh`
- VPS sidecars: `./deploy/vps/bench/deploy.sh`
- VPS echo: `./deploy/vps/echo/deploy-all.sh`

## Key Files

| File | Purpose |
|------|---------|
| `scripts/traffic/arena/benchmark.js` | k6 L0 (7 scenarios) |
| `scripts/traffic/arena/benchmark-enterprise.js` | k6 L1 (20 dimensions) |
| `scripts/traffic/arena/run-arena.sh` / `run-arena.py` | L0 orchestrator + scorer |
| `scripts/traffic/arena/run-arena-enterprise.sh` / `.py` | L1 orchestrator + scorer |
| `scripts/traffic/arena/run-arena-verify.sh` | L2 CUJ verifier |
| `k8s/arena/cronjob-prod.yaml` | L0 CronJob (30min) |
| `k8s/arena/cronjob-enterprise.yaml` | L1 CronJob (hourly) |
| `k8s/arena/cronjob-verify.yaml` | L2 CronJob (15min) |
| `k8s/arena/deploy.sh` | K8s deploy (idempotent, 9 steps) |

Supporting: `kong.yaml`, `gravitee.yaml`, `echo-backend.yaml`, `pushgateway*.yaml`, Grafana dashboards (`gateway-arena.json`, `gateway-arena-enterprise.json`, `platform-health.json`), VPS compose files in `deploy/vps/`.

## L1: Enterprise AI Readiness

20 dimensions in 4 categories measuring AI-native gateway capabilities. No MCP = score 0.

**Composite**: `sum(weight_i * dimension_i)`. Dimension: `0.6*availability + 0.4*latency_score`. Latency: `max(0, 100*(1-p95/cap))`.

| Category | Dims | Weight | Key Dimensions |
|----------|------|--------|----------------|
| Core | 8 | 0.51 | MCP Discovery/Tool (0.18), Auth Chain (0.08), Policy (0.06), Guardrails (0.06), Rate Limit (0.05), Resilience (0.05), Governance (0.03) |
| LLM Intelligence | 3 | 0.17 | Routing (0.07), Cost (0.05), Circuit Breaker (0.05) |
| MCP Depth | 3 | 0.13 | Native Tools CRUD (0.05), API Bridge (0.04), UAC Binding (0.04) |
| Security & Compliance | 3 | 0.10 | PII Detection (0.04), Distributed Tracing (0.03), Prompt Cache (0.03) |
| Platform Ops | 3 | 0.09 | Skills Lifecycle (0.03), Federation (0.03), Diagnostic (0.03) |

Features gate: gateways declare `features` array in GATEWAYS JSON. Missing = score 0. Blue Ocean: 49% on STOA-unique features.

**MCP Protocol**: STOA = custom REST (`/mcp/capabilities`, `/mcp/tools/list|call`), Gravitee 4.8 = Streamable HTTP (JSON-RPC 2.0), Kong OSS = none (Enterprise-only plugin).

Scores: STOA ~85-95, Kong ~5-8, Gravitee ~47-50.

## L2: Platform Continuous Verification

3 CUJs every 15 min: (1) Health chain (API+GW+KC return 2xx), (2) Auth flow (OIDC → authenticated call), (3) MCP Discovery→Call.

Prerequisites: K8s Secret `arena-verify-config` (OIDC client secret + Healthchecks URL), Keycloak client `stoa-healthcheck`.

6 alerts: `PlatformCUJFailing` (30m critical), `PlatformVerifyStale` (5m warning), `PlatformDegraded` (45m), `PlatformAuthFlowDown` (15m critical), `PlatformMCPDown` (15m critical), `PlatformCUJSlow` (30m).

## Prometheus Metrics

L0: `gateway_arena_{score,score_stddev,score_ci_lower,score_ci_upper,runs,availability,latency_seconds,p50/p95/p99_seconds,requests_total}`
L1: `gateway_arena_enterprise_{score,dimension,score_ci_lower,score_ci_upper,score_stddev,runs,latency_p95}`
L2: `platform_verify_{cuj_status,cuj_duration_seconds,overall_score,total,last_run_timestamp}`, recording rules `platform:verify_health:ratio`, `platform:cuj_availability_1h:ratio`

## Docker Image

`ghcr.io/stoa-platform/arena-bench:0.2.0` — k6 0.54.0 + jq + curl + bash + python3. Scripts via ConfigMap.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Gateway unreachable | Check firewall, `kubectl run curl --rm -it --image=curlimages/curl -- curl -s http://host:port/health` |
| Score = 0 | Check CronJob logs: `kubectl logs -n stoa-system job/gateway-arena --tail=50` |
| Pushgateway empty | Verify pod: `kubectl get pods -n monitoring -l app=pushgateway` |
| STOA 403 "Backend URL blocked" | Use container name, not localhost (SSRF blocklist) |
| Kong 502 on echo | `docker network connect kong_default echo-local` |
| Gravitee 404 | Lifecycle: create → plan → publish plan → deploy → start |

## Manual Run

```bash
# L0
kubectl create job --from=cronjob/gateway-arena arena-manual -n stoa-system
# L1
kubectl create job --from=cronjob/gateway-arena-enterprise arena-ent-manual -n stoa-system
# L2
kubectl create job --from=cronjob/gateway-arena-verify verify-manual -n stoa-system
# Cleanup: kubectl delete job <name> -n stoa-system
```
