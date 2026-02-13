---
description: Gateway Arena benchmark lab — adding gateways, reading results, troubleshooting
globs: "k8s/arena/**,scripts/traffic/**,docker/observability/grafana/**"
---

# Gateway Arena — Benchmark Lab

## Overview

Continuous comparative benchmarking: 6 gateways (3 K8s + 3 VPS) across STOA, Kong, and Gravitee.
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
HTTP keepalive: `requests.Session` + `HTTPAdapter(pool_maxsize=200)` + 5-request warm-up.
Scoring caps: 400ms (sequential), 2.5s (burst_50), 4s (burst_100) — calibrated for keepalive over K8s→VPS.
Consistency: IQR-based CV (robust to bimodal network latency).

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

**VPS echo + routes**: `./deploy/vps/echo/deploy-all.sh`

## Key Files

| File | Purpose |
|------|---------|
| `scripts/traffic/gateway-arena.py` | Benchmark script (6 scenarios x N gateways) |
| `k8s/arena/cronjob-prod.yaml` | CronJob manifest (every 30 min, 6 gateways) |
| `k8s/arena/kong.yaml` | Kong DB-less in-cluster (ConfigMap + Deploy + Svc) |
| `k8s/arena/gravitee.yaml` | Gravitee APIM in-cluster (Mongo + Mgmt + GW + Init Job) |
| `k8s/arena/echo-backend.yaml` | Shared echo backend (nginx, port 8888) |
| `k8s/arena/pushgateway.yaml` | Pushgateway deployment + service |
| `k8s/arena/pushgateway-servicemonitor.yaml` | Prometheus auto-discovery |
| `k8s/arena/deploy.sh` | K8s deploy script (idempotent, 9 steps) |
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
