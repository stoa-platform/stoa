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

Score formula: `0.40 * Latency + 0.30 * Availability + 0.20 * ErrorRate + 0.10 * Consistency`

## Key Files

| File | Purpose |
|------|---------|
| `scripts/traffic/gateway-arena.py` | Benchmark script (3 scenarios x N gateways) |
| `k8s/arena/cronjob-prod.yaml` | CronJob manifest (every 30 min) |
| `k8s/arena/pushgateway.yaml` | Pushgateway deployment + service |
| `docker/observability/grafana/dashboards/gateway-arena.json` | Grafana leaderboard dashboard |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Gateway unreachable | VPS firewall or port blocked | Check `curl` from a pod: `kubectl run curl --rm -it --image=curlimages/curl -- curl -s http://host:port/health` |
| Score = 0 | All requests failed | Check CronJob logs: `kubectl logs -n stoa-system job/gateway-arena --tail=50` |
| Pushgateway empty | Script not pushing or Pushgateway down | Verify pod: `kubectl get pods -n monitoring -l app=pushgateway` |
| Metrics not in Prometheus | Scrape config missing | Verify Pushgateway target in Prometheus targets page |
| Stale metrics | CronJob not running | Check: `kubectl get cronjob gateway-arena -n stoa-system` |

## Manual Run

```bash
# Trigger a one-off benchmark
kubectl create job --from=cronjob/gateway-arena arena-manual -n stoa-system

# Watch logs
kubectl logs -n stoa-system -l job-name=arena-manual --follow

# Cleanup
kubectl delete job arena-manual -n stoa-system
```
