---
description: Gateway Arena benchmark lab — adding gateways, reading results, troubleshooting
globs: "k8s/arena/**,scripts/traffic/**,docker/observability/grafana/**"
---

# Gateway Arena — Benchmark Lab

## Overview

Continuous comparative benchmarking: 5 gateways (3 K8s co-located + 2 VPS co-located) across STOA, Kong, and Gravitee.
**Engine**: k6 (replaced Python requests in Feb 2026, PR #438).
**Methodology**: Median of 5 runs (1 discarded as warm-up), CI95 confidence intervals.
K8s CronJob runs every 30 min on OVH K8s (3 gateways). VPS sidecars run on host cron (1 gateway each).
Metrics pushed to Pushgateway, visualized in Grafana.

## Architecture

```
K8s CronJob (OVH MKS, every 30 min):
  run-arena.sh (orchestrator)
    └── For each K8s gateway (3):
        └── For each run (5):
            ├── k6 run --env SCENARIO=warmup → /dev/null
            └── k6 run --env SCENARIO={health,sequential,...} → /tmp/{gw}/{run}/{scenario}.json
  run-arena.py (scorer)
    └── Reads JSON summaries → median → score → CI95 → Prometheus text
    └── curl → Pushgateway

VPS Sidecar (host cron, every 30 min):
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

## Manual Run

```bash
# Trigger a one-off benchmark
kubectl create job --from=cronjob/gateway-arena arena-manual -n stoa-system

# Watch logs
kubectl logs -n stoa-system -l job-name=arena-manual --follow

# Cleanup
kubectl delete job arena-manual -n stoa-system
```
