---
description: Gateway Arena benchmark lab — adding gateways, reading results, troubleshooting
globs: "k8s/arena/**,scripts/traffic/**,docker/observability/grafana/**"
---

# Gateway Arena — Benchmark Lab

## Overview

Continuous comparative benchmarking across STOA, Kong, and Gravitee gateways.
CronJob runs every 30 min on OVH K8s, pushes metrics to Pushgateway, visualized in Grafana.

## Adding a New Gateway

1. Add entry to `GATEWAYS` JSON in `k8s/arena/cronjob-prod.yaml`:
   ```json
   {"name": "new-gw", "health": "http://host:port/health", "proxy": "http://host:port/path", "proxy_headers": {"Key": "Value"}}
   ```
2. Ensure health + proxy endpoints are accessible from OVH K8s pods
3. Update ConfigMap: `kubectl create configmap gateway-arena-script --from-file=scripts/traffic/gateway-arena.py -n stoa-system --dry-run=client -o yaml | kubectl apply -f -`
4. Run manual job to validate: `kubectl create job --from=cronjob/gateway-arena arena-test-$(date +%s) -n stoa-system`

## Reading Results

| Score | Rating | Interpretation |
|-------|--------|----------------|
| >80 | Excellent | STOA target |
| 60-80 | Acceptable | Normal for external gateways with network hop |
| <60 | Investigate | Connection issues or high error rate |

Score formula: `0.15*Base + 0.25*Burst50 + 0.25*Burst100 + 0.15*Avail + 0.10*Error + 0.10*Consistency`

6 scenarios: health, proxy_sequential(20), burst_10, burst_50, burst_100, sustained(100).
Scoring caps: 500ms (sequential), 3s (burst_50), 5s (burst_100) — tuned for K8s→VPS remote benchmarking.

## Fair Comparison — Local Echo Backend

Arena uses a local nginx echo server (static JSON, <1ms) on each VPS so benchmarks
measure pure gateway overhead, not backend/network latency.

| Gateway | VPS IP | Health | Proxy | Backend |
|---------|--------|--------|-------|---------|
| STOA | `51.83.45.13:8080` | `/health` | `/echo/get` | echo-local:8888 (Docker) |
| Kong | `51.83.45.13:8000` | `:8001/status` | `/echo/get` | echo-local:8888 (Docker) |
| Gravitee | `54.36.209.237:8082` | `:8083/management/...` | `/echo/get` | echo-local:8888 (Docker) |

### Docker Network Setup (critical)

All gateways run in Docker. The echo container MUST be on the same Docker network:
- Kong VPS: `docker network connect kong_default echo-local && docker network connect stoa_default echo-local`
- Gravitee VPS: `docker network connect gravitee_default echo-local`
- Backend URL must be `http://echo-local:8888` (container name, NOT localhost)
- STOA's SSRF blocklist blocks `localhost` — use container name or public IP

### Deploy Echo + Configure Routes

```bash
./deploy/vps/echo/deploy-all.sh
```

This script: deploys echo on both VPS, connects Docker networks, registers routes on all 3 gateways.

## Key Files

| File | Purpose |
|------|---------|
| `scripts/traffic/gateway-arena.py` | Benchmark script (6 scenarios x N gateways) |
| `k8s/arena/cronjob-prod.yaml` | CronJob manifest (every 30 min) |
| `k8s/arena/pushgateway.yaml` | Pushgateway deployment + service |
| `k8s/arena/pushgateway-servicemonitor.yaml` | Prometheus auto-discovery |
| `k8s/arena/deploy.sh` | K8s deploy script (idempotent) |
| `docker/observability/grafana/dashboards/gateway-arena.json` | Grafana leaderboard dashboard |
| `deploy/vps/echo/deploy-all.sh` | VPS echo + route setup |
| `deploy/vps/echo/docker-compose.yml` | Echo server (nginx:alpine) |
| `deploy/vps/echo/nginx.conf` | Static JSON response config |
| `deploy/vps/stoa/docker-compose.yml` | STOA VPS deployment (standalone) |

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
