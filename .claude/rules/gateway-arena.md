---
globs: "scripts/traffic/arena/**,k8s/arena/**,deploy/vps/bench/**"
---

# Gateway Arena — Benchmark Lab

## Overview

Three-layer continuous verification system:

| Layer | Purpose | Frequency | Engine |
|-------|---------|-----------|--------|
| **L0 — Proxy Baseline** | Raw throughput, burst, latency | 30 min | k6 |
| **L1 — Enterprise AI Readiness** | 8 MCP dimensions | 1 hour | k6 |
| **L2 — Platform Verification** | 3 CUJs (health, auth, MCP) | 15 min | curl/bash |

**L0/L1 Engine**: k6 (replaced Python requests in Feb 2026, PR #438).
**L0/L1 Methodology**: Median of 5 runs (1 discarded as warm-up), CI95 confidence intervals.
**L2 Engine**: curl-based CUJs, pass/fail + duration. Dead man's switch via Healthchecks.
All layers push to Pushgateway, visualized in Grafana.

## Architecture

```
K8s CronJob (OVH MKS, every 30 min — L0):
  run-arena.sh (orchestrator)
    └── For each K8s gateway (3):
        └── For each run (5):
            ├── k6 run --env SCENARIO=warmup → /dev/null
            └── k6 run --env SCENARIO={health,sequential,...} → /tmp/{gw}/{run}/{scenario}.json
  run-arena.py (scorer)
    └── Reads JSON summaries → median → score → CI95 → Prometheus text
    └── curl → Pushgateway

K8s CronJob (OVH MKS, every 15 min — L2):
  run-arena-verify.sh (platform verifier)
    └── CUJ 1: API Health Chain (curl /health on API + Gateway + Keycloak)
    └── CUJ 2: Auth Flow (OIDC token → authenticated API call)
    └── CUJ 3: MCP Discovery→Call (/mcp/capabilities → /mcp/tools/list)
    └── Results → Pushgateway + Healthchecks ping

VPS Sidecar (host cron, every 30 min — L0):
  Same image + scripts, benchmarks 1 local gateway
  Pushes to https://pushgateway.gostoa.dev (IP-whitelisted)
```

## Adding a New Gateway

### K8s gateway (in-cluster)
1. Add entry to `GATEWAYS` JSON in `k8s/arena/cronjob-prod.yaml`:
   ```json
   {"name": "new-gw", "health": "http://svc.stoa-system.svc:port/health", "proxy": "http://svc.stoa-system.svc:port/echo/get"}
   ```
2. Ensure health + proxy endpoints are accessible from OVH K8s pods
3. Update ConfigMap: `kubectl create configmap gateway-arena-scripts --from-file=scripts/traffic/arena/benchmark.js --from-file=scripts/traffic/arena/run-arena.sh --from-file=scripts/traffic/arena/run-arena.py -n stoa-system --dry-run=client -o yaml | kubectl apply -f -`
4. Run manual job to validate: `kubectl create job --from=cronjob/gateway-arena arena-test-$(date +%s) -n stoa-system`

### VPS gateway (co-located sidecar)
1. Add VPS config to `deploy/vps/bench/deploy.sh`
2. Deploy: `./deploy/vps/bench/deploy.sh`
3. Verify: check Pushgateway at `https://pushgateway.gostoa.dev/metrics`

## Reading Results

| Score | Rating | Interpretation |
|-------|--------|----------------|
| >95 | Excellent | Co-located gateway, minimal overhead |
| 80-95 | Good | Normal for well-configured gateways |
| 60-80 | Acceptable | Check network or resource constraints |
| <60 | Investigate | Connection issues or high error rate |

Score formula: `0.15*Base + 0.25*Burst50 + 0.25*Burst100 + 0.15*Avail + 0.10*Error + 0.10*Consistency`

7 scenarios: warmup (discarded), health, sequential(20), burst_10, burst_50, burst_100, sustained(100).
Burst 50/100 use `ramping-vus` executor (5s ramp-up, 10s hold, 3s ramp-down).
Scoring caps: 400ms (sequential), 2.5s (burst_50), 4s (burst_100).
Consistency: IQR-based CV `(P75-P25)/P50` (robust to bimodal network latency).
CI95: t-distribution confidence intervals (Python stdlib, 5 runs → df=3 after discard).

## Fair Comparison — Local Echo Backend

Arena uses a local nginx echo server (static JSON, <1ms) so benchmarks
measure pure gateway overhead, not backend/network latency.

### In-Cluster (K8s — OVH MKS)

| Gateway | Service | Health | Proxy | Backend |
|---------|---------|--------|-------|---------|
| stoa-k8s | `stoa-gateway.stoa-system.svc` | `/health` | `/echo/get` | echo-backend:8888 |
| kong-k8s | `kong-arena.stoa-system.svc:8000` | `:8001/status` | `/echo/get` | echo-backend:8888 |
| gravitee-k8s | `gravitee-arena-gw.stoa-system.svc:8082` | `:18082/_node/health` | `/echo/get` | echo-backend:8888 |

### VPS (External)

| Gateway | VPS IP | Health | Proxy | Backend |
|---------|--------|--------|-------|---------|
| stoa-vps | `51.83.45.13:8080` | `/health` | `/echo/get` | echo-local:8888 (Docker) |
| kong-vps | `51.83.45.13:8000` | `:8001/status` | `/echo/get` | echo-local:8888 (Docker) |
| gravitee-vps | `54.36.209.237:8082` | `:8083/management/...` | `/echo/get` | echo-local:8888 (Docker) |

### Docker Network Setup (VPS only)

VPS gateways run in Docker. The echo container MUST be on the same Docker network:
- Kong VPS: `docker network connect kong_default echo-local && docker network connect stoa_default echo-local`
- Gravitee VPS: `docker network connect gravitee_default echo-local`
- Backend URL must be `http://echo-local:8888` (container name, NOT localhost)
- STOA's SSRF blocklist blocks `localhost` — use container name or public IP

### Deploy

**K8s (all 3 gateways)**: `KUBECONFIG=~/.kube/config-stoa-ovh ./k8s/arena/deploy.sh`

**VPS sidecars**: `./deploy/vps/bench/deploy.sh`

**VPS echo + routes**: `./deploy/vps/echo/deploy-all.sh`

## Key Files

| File | Purpose |
|------|---------|
| `scripts/traffic/arena/benchmark.js` | k6 benchmark (7 scenarios, env-driven) |
| `scripts/traffic/arena/run-arena.sh` | Shell orchestrator (gateway × run × scenario loop) |
| `scripts/traffic/arena/run-arena.py` | Python scorer (median, composite score, CI95) |
| `scripts/traffic/arena/Dockerfile` | arena-bench image (k6 + jq + curl + bash + python3) |
| `k8s/arena/cronjob-prod.yaml` | CronJob manifest (every 30 min, 3 K8s gateways) |
| `k8s/arena/kong.yaml` | Kong DB-less in-cluster (ConfigMap + Deploy + Svc) |
| `k8s/arena/gravitee.yaml` | Gravitee APIM in-cluster (Mongo + Mgmt + GW + Init Job) |
| `k8s/arena/echo-backend.yaml` | Shared echo backend (nginx, port 8888) |
| `k8s/arena/pushgateway.yaml` | Pushgateway deployment + service |
| `k8s/arena/pushgateway-ingress.yaml` | Pushgateway ingress (IP-whitelisted for VPS) |
| `k8s/arena/pushgateway-servicemonitor.yaml` | Prometheus auto-discovery |
| `k8s/arena/deploy.sh` | K8s deploy script (idempotent, 9 steps) |
| `docker/observability/grafana/dashboards/gateway-arena.json` | Grafana leaderboard + CI95 dashboard |
| `deploy/vps/bench/docker-compose.yml` | VPS sidecar benchmark (1 gateway per VPS) |
| `deploy/vps/bench/deploy.sh` | SSH deploy sidecars to VPS hosts |
| `deploy/vps/echo/deploy-all.sh` | VPS echo + route setup |
| `deploy/vps/echo/docker-compose.yml` | Echo server (nginx:alpine) |
| `deploy/vps/echo/nginx.conf` | Static JSON response config |
| `deploy/vps/stoa/docker-compose.yml` | STOA VPS deployment (standalone) |

## Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `gateway_arena_score` | gauge | Composite score (median of valid runs) |
| `gateway_arena_score_stddev` | gauge | Run-to-run standard deviation |
| `gateway_arena_score_ci_lower` | gauge | CI95 lower bound |
| `gateway_arena_score_ci_upper` | gauge | CI95 upper bound |
| `gateway_arena_runs` | gauge | Number of valid runs (after warm-up discard) |
| `gateway_arena_availability` | gauge | Health check success rate |
| `gateway_arena_latency_seconds` | gauge | Median response time (per scenario) |
| `gateway_arena_p50/p95/p99_seconds` | gauge | Percentile latencies |
| `gateway_arena_requests_total` | gauge | Total requests sent |

## Docker Image

```bash
# Build (manual, only needed on k6 version bump)
docker buildx build --platform linux/amd64 -t ghcr.io/stoa-platform/arena-bench:0.1.0 --push scripts/traffic/arena/

# Image contents: k6 0.54.0 + jq + curl + bash + python3
# Scripts mounted via ConfigMap (not baked into image)
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Gateway unreachable | VPS firewall or port blocked | Check `curl` from a pod: `kubectl run curl --rm -it --image=curlimages/curl -- curl -s http://host:port/health` |
| Score = 0 | All requests failed | Check CronJob logs: `kubectl logs -n stoa-system job/gateway-arena --tail=50` |
| Pushgateway empty | Script not pushing or Pushgateway down | Verify pod: `kubectl get pods -n monitoring -l app=pushgateway` |
| Metrics not in Prometheus | Scrape config missing | Verify Pushgateway target in Prometheus targets page |
| Stale metrics | CronJob not running | Check: `kubectl get cronjob gateway-arena -n stoa-system` |
| STOA 403 "Backend URL blocked" | SSRF blocklist blocks localhost | Use Docker container name (`echo-local`) or public IP as backend URL |
| Kong 502 on echo | Kong container can't reach host localhost | Connect echo to Kong Docker network: `docker network connect kong_default echo-local` |
| Gravitee "no published plan" | Plan created in STAGING status | Explicitly publish: `POST /apis/{id}/plans/{planId}/_publish` |
| Gravitee 404 | API not started or not deployed | Lifecycle: create → plan → publish plan → deploy → start |
| Staging ServiceMonitor not discovered | Wrong Prometheus selector labels | Staging uses `release: prometheus` (not `kube-prometheus-stack`) |

## Layer 1: Enterprise AI Readiness

Separate benchmark measuring 8 enterprise dimensions that define AI-native gateway capabilities.
Gateways without MCP score **0** (not N/A). The spec is open — any gateway can implement and re-run.

### Architecture

```
Layer 0 — Proxy Baseline (existing, unchanged)
  Score: Kong ~87 | STOA ~73
  Measures: raw throughput, burst, ramp-up
  Schedule: every 30 min (CronJob: gateway-arena)

Layer 1 — Enterprise AI Readiness (NEW)
  Score: STOA ~95 | Kong ~5 | Gravitee ~5
  Measures: 8 enterprise dimensions
  Schedule: hourly (CronJob: gateway-arena-enterprise)
```

### 8 Enterprise Dimensions

| # | Dimension | Weight | Scenario | Endpoint | Cap |
|---|-----------|--------|----------|----------|-----|
| 1 | MCP Discovery | 0.15 | `ent_mcp_discovery` | `GET /mcp/capabilities` | 500ms |
| 2 | MCP Tool Execution | 0.20 | `ent_mcp_toolcall` | `POST /mcp/tools/list` (JSON-RPC) | 500ms |
| 3 | Auth Chain | 0.15 | `ent_auth_chain` | JWT + tool call | 1s |
| 4 | Policy Engine | 0.15 | `ent_policy_eval` | OPA evaluation overhead | 200ms |
| 5 | AI Guardrails | 0.10 | `ent_guardrails` | PII in payload blocked/redacted | 1s |
| 6 | Rate Limiting | 0.10 | `ent_quota_burst` | 429 enforcement | 1s |
| 7 | Resilience | 0.10 | `ent_resilience` | Bad tool call → 4xx (not 500) | 1s |
| 8 | Agent Governance | 0.05 | `ent_governance` | Session/governance endpoints | 2s |

**Composite**: `Enterprise Readiness Index = sum(weight_i * dimension_i)`

**Dimension score**: `0.6 * availability_score + 0.4 * latency_score`
- `availability_score = passes / (passes + fails) * 100`
- `latency_score = max(0, 100 * (1 - p95 / cap))`

### Enterprise Key Files

| File | Purpose |
|------|---------|
| `scripts/traffic/arena/benchmark-enterprise.js` | k6 enterprise scenarios (8 dimensions) |
| `scripts/traffic/arena/run-arena-enterprise.sh` | Shell orchestrator (gateway × run × scenario) |
| `scripts/traffic/arena/run-arena-enterprise.py` | Python scorer (per-dimension, composite, CI95) |
| `k8s/arena/cronjob-enterprise.yaml` | Enterprise CronJob (hourly) |
| `k8s/arena/deploy-enterprise.sh` | Standalone deploy for enterprise CronJob |
| `docker/observability/grafana/dashboards/gateway-arena-enterprise.json` | Enterprise Grafana dashboard |

### Enterprise Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `gateway_arena_enterprise_score` | gauge | Composite Enterprise Readiness Index (0-100) |
| `gateway_arena_enterprise_dimension` | gauge | Per-dimension score (0-100) |
| `gateway_arena_enterprise_score_ci_lower` | gauge | CI95 lower bound |
| `gateway_arena_enterprise_score_ci_upper` | gauge | CI95 upper bound |
| `gateway_arena_enterprise_score_stddev` | gauge | Run-to-run standard deviation |
| `gateway_arena_enterprise_runs` | gauge | Number of valid enterprise runs |
| `gateway_arena_enterprise_latency_p95` | gauge | P95 latency per dimension |

### Enterprise CronJob Config

```yaml
# GATEWAYS JSON — mcp_base: null means "no MCP support, score 0"
# mcp_protocol: "stoa" (REST paths) or "streamable-http" (JSON-RPC 2.0 on single endpoint)
[
  {"name":"stoa-k8s", "target":"http://stoa-gateway:8080", "mcp_base":"http://stoa-gateway:8080/mcp", "mcp_protocol":"stoa"},
  {"name":"kong-k8s",  "target":"http://kong-arena:8000",  "mcp_base":null},
  {"name":"gravitee-k8s", "target":"http://gravitee-arena-gw:8082", "mcp_base":"http://gravitee-arena-gw:8082/mcp", "mcp_protocol":"streamable-http"}
]
```

### MCP Protocol Variants

| Gateway | MCP Protocol | Endpoint Pattern | License |
|---------|-------------|-----------------|---------|
| STOA | Custom REST (`mcp_protocol: "stoa"`) | `GET /mcp/capabilities`, `POST /mcp/tools/list`, `POST /mcp/tools/call` | Apache 2.0 |
| Gravitee 4.8 | Streamable HTTP (`mcp_protocol: "streamable-http"`) | `POST /mcp` with JSON-RPC 2.0 | Apache 2.0 |
| Kong OSS | None (`mcp_base: null`) | N/A — `ai-mcp-proxy` plugin is Enterprise-only | Apache 2.0 (OSS) |

The benchmark script (`benchmark-enterprise.js`) uses `MCP_PROTOCOL` env var to switch between request formats.

### Open Participation

Any gateway can participate in Layer 1:
1. Implement MCP endpoints (either REST or Streamable HTTP)
2. Add gateway entry to GATEWAYS JSON with `mcp_base` + `mcp_protocol`
3. Deploy and run: `kubectl create job --from=cronjob/gateway-arena-enterprise arena-ent-test -n stoa-system`

The benchmark is fair: same k6 scenarios, same scoring formula, same CI95 methodology.

## Layer 2: Platform Continuous Verification

Continuous CUJ (Critical User Journey) testing — verifies the platform works end-to-end every 15 minutes.
Unlike L0/L1 which measure performance, L2 answers: "Does the platform work right now?"

### 3 CUJs

| # | CUJ | What It Tests | Pass Criteria |
|---|-----|---------------|---------------|
| 1 | API Health Chain | `/health` on API, Gateway, Keycloak | All 3 return 2xx |
| 2 | Auth Flow | OIDC client_credentials → authenticated API call | Token obtained + API returns 2xx/3xx |
| 3 | MCP Discovery→Call | `GET /mcp/capabilities` + `POST /mcp/tools/list` | Both return 2xx with valid JSON |

### Prerequisites

- K8s Secret `arena-verify-config` in `stoa-system` namespace:
  - `oidc-client-secret`: Keycloak `stoa-healthcheck` client secret
  - `healthchecks-url`: Healthchecks ping URL (e.g., `https://hc.gostoa.dev/ping/<UUID>`)
- Keycloak client `stoa-healthcheck` (confidential, client_credentials grant, stoa realm)

### Layer 2 Key Files

| File | Purpose |
|------|---------|
| `scripts/traffic/arena/run-arena-verify.sh` | CUJ verification script (curl-based) |
| `k8s/arena/cronjob-verify.yaml` | CronJob manifest (every 15 min) |
| `docker/observability/prometheus/rules/platform-verify-alerts.yaml` | PrometheusRule (6 alerts) |
| `docker/observability/grafana/dashboards/platform-health.json` | Grafana dashboard |

### Layer 2 Prometheus Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `platform_verify_cuj_status` | gauge | CUJ pass (1) or fail (0), label: `cuj` |
| `platform_verify_cuj_duration_seconds` | gauge | CUJ execution duration, label: `cuj` |
| `platform_verify_overall_score` | gauge | Number of CUJs passing (0-3) |
| `platform_verify_total` | gauge | Total number of CUJs (3) |
| `platform_verify_last_run_timestamp` | gauge | Unix timestamp of last run |
| `platform:verify_health:ratio` | recording | Overall health ratio (0-1) |
| `platform:cuj_availability_1h:ratio` | recording | Per-CUJ 1h rolling availability |

### Layer 2 Alerts

| Alert | Condition | Duration | Severity |
|-------|-----------|----------|----------|
| `PlatformCUJFailing` | Any CUJ status == 0 | 30m | critical |
| `PlatformVerifyStale` | Last run > 20 min ago | 5m | warning |
| `PlatformDegraded` | Some but not all CUJs passing | 45m | warning |
| `PlatformAuthFlowDown` | Auth CUJ == 0 | 15m | critical |
| `PlatformMCPDown` | MCP CUJ == 0 | 15m | critical |
| `PlatformCUJSlow` | Any CUJ duration > 3s | 30m | warning |

### Deploy Layer 2

```bash
# 1. Create Keycloak client (manual — see DoD)
# 2. Create K8s secret
kubectl create secret generic arena-verify-config \
  --from-literal=oidc-client-secret=<SECRET> \
  --from-literal=healthchecks-url=https://hc.gostoa.dev/ping/<UUID> \
  -n stoa-system

# 3. Update ConfigMap (add verify script)
kubectl create configmap gateway-arena-scripts \
  --from-file=scripts/traffic/arena/benchmark.js \
  --from-file=scripts/traffic/arena/benchmark-enterprise.js \
  --from-file=scripts/traffic/arena/run-arena.sh \
  --from-file=scripts/traffic/arena/run-arena-enterprise.sh \
  --from-file=scripts/traffic/arena/run-arena.py \
  --from-file=scripts/traffic/arena/run-arena-enterprise.py \
  --from-file=scripts/traffic/arena/run-arena-verify.sh \
  -n stoa-system --dry-run=client -o yaml | kubectl apply -f -

# 4. Apply CronJob + PrometheusRule
kubectl apply -f k8s/arena/cronjob-verify.yaml
kubectl apply -f docker/observability/prometheus/rules/platform-verify-alerts.yaml

# 5. Provision Grafana dashboard
# Copy platform-health.json to Grafana provisioning path

# 6. Manual test
kubectl create job --from=cronjob/gateway-arena-verify verify-test -n stoa-system
kubectl logs -n stoa-system -l job-name=verify-test --follow
kubectl delete job verify-test -n stoa-system
```

## Manual Run

```bash
# Layer 0 (baseline) — one-off benchmark
kubectl create job --from=cronjob/gateway-arena arena-manual -n stoa-system
kubectl logs -n stoa-system -l job-name=arena-manual --follow
kubectl delete job arena-manual -n stoa-system

# Layer 1 (enterprise) — one-off benchmark
kubectl create job --from=cronjob/gateway-arena-enterprise arena-ent-manual -n stoa-system
kubectl logs -n stoa-system -l job-name=arena-ent-manual --follow
kubectl delete job arena-ent-manual -n stoa-system

# Layer 2 (platform verify) — one-off verification
kubectl create job --from=cronjob/gateway-arena-verify verify-manual -n stoa-system
kubectl logs -n stoa-system -l job-name=verify-manual --follow
kubectl delete job verify-manual -n stoa-system
```
