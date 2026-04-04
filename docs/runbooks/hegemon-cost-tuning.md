# Hegemon Cost Tuning — Ops Runbook

> **Ticket**: CAB-1825 (parent: CAB-1824)
> **Last updated**: 2026-03-15

## Overview

This runbook covers operational tuning of Hegemon cost monitoring: alert thresholds, worker fleet changes, Pushgateway credentials, and Grafana dashboard maintenance.

## Architecture

```
Workers (stop-hook) → POST /traces/ingest → Control Plane API
                                              ├─ push_cost_metrics() → Pushgateway → Prometheus → Grafana
                                              └─ check_cost_alert()  → Slack (deduped 1/day)
```

**Two Pushgateway jobs**:
- `hegemon_ai_factory` — pushed by CP API on every ingest (session metrics)
- `hegemon_daemon` — pushed by daemon health check cycle (worker health + budget)

## Adjusting Alert Threshold

The cost alert fires when daily spend exceeds `HEGEMON_COST_ALERT_THRESHOLD` (default: `50` USD).

### Change threshold

1. Update the env var on the Control Plane API deployment:
   ```bash
   kubectl set env deployment/control-plane-api \
     HEGEMON_COST_ALERT_THRESHOLD=75 \
     -n stoa-system
   ```
2. Verify pod restarted:
   ```bash
   kubectl rollout status deployment/control-plane-api -n stoa-system
   ```
3. The new threshold takes effect on the next ingest call.

### Alert deduplication

Alerts are deduped to 1/day using a `cost-alert` trace marker in PostgreSQL. To reset (force a re-alert today):
```sql
-- Find today's alert marker
SELECT id, created_at FROM pipeline_traces
WHERE trigger_type = 'cost-alert'
  AND created_at >= CURRENT_DATE
ORDER BY created_at DESC;

-- Delete to allow re-alert (use with caution)
DELETE FROM pipeline_traces
WHERE trigger_type = 'cost-alert'
  AND created_at >= CURRENT_DATE;
```

### Grafana threshold lines

The "Cost Trend" panel has yellow (30 USD) and red (50 USD) threshold lines. To update:
1. Edit `k8s/grafana/dashboards/hegemon-cost.json`
2. Find panel id 20 → `fieldConfig.defaults.thresholds.steps`
3. Update the values to match your new threshold
4. Apply: `kubectl apply -f k8s/grafana/dashboards/` or restart Grafana

## Adding a New Worker

### 1. Provision the VPS

See `docs/runbooks/hegemon-vps-setup.md` for the full VPS setup procedure.

### 2. Configure the worker

The worker must send traces with a unique `worker` field in the session-summary step:
```json
{
  "name": "session-summary",
  "status": "success",
  "details": {
    "worker": "w6-new-worker",
    "cost_usd": 12.50,
    "total_tokens": 450000,
    "model": "claude-opus-4-6"
  }
}
```

### 3. Verify metrics flow

```bash
# Check Pushgateway has the new worker label
curl -s https://push.gostoa.dev/metrics | grep 'worker="w6-new-worker"'

# Check Grafana dashboard — the worker variable auto-discovers from label_values
# Open: Grafana → Hegemon Cost Intelligence → worker dropdown should list the new worker
```

### 4. Update daemon config

Add the worker to the daemon's worker list in `hegemon/daemon/config.yaml` and restart the daemon.

## Rotating Pushgateway Credentials

Pushgateway credentials are stored in Vault at `stoa/shared/pushgateway`.

### Rotation steps

1. **Generate new credentials** (human-only, never automated):
   ```bash
   # Generate new basic auth password
   openssl rand -base64 32
   ```

2. **Update Vault**:
   ```bash
   vault kv put stoa/shared/pushgateway \
     username=pushgateway \
     password=<NEW_PASSWORD>
   ```

3. **Update consumers** (all services that push to Pushgateway):
   - Control Plane API: `PUSHGATEWAY_URL` includes basic auth
   - Hegemon daemon: `PUSHGATEWAY_URL` in daemon config
   - Arena benchmarks: ConfigMap in `k8s/arena/`

4. **Restart affected services**:
   ```bash
   kubectl rollout restart deployment/control-plane-api -n stoa-system
   # Restart daemon on each worker VPS
   ssh w1 'sudo systemctl restart hegemon-agent'
   ```

5. **Verify** metrics are still flowing:
   ```bash
   curl -s -u pushgateway:<NEW_PASSWORD> https://push.gostoa.dev/metrics | head -20
   ```

## Grafana Dashboard Maintenance

### Dashboard location

| Environment | Path | Auto-provisioned |
|-------------|------|-----------------|
| K8s (prod) | `k8s/grafana/dashboards/hegemon-cost.json` | Via ConfigMap |
| Docker (local) | `stoa-infra:docker/observability/grafana/dashboards/hegemon-cost.json` | Via volume mount |

### Available metrics

**From CP API** (`job="hegemon_ai_factory"`):
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `hegemon_cost_usd_total` | gauge | — | Total cost today (USD) |
| `hegemon_tokens_total` | gauge | — | Total tokens today |
| `hegemon_sessions_total` | gauge | — | Total sessions today |
| `hegemon_cost_per_session_usd` | gauge | — | Average cost per session |
| `hegemon_success_rate` | gauge | — | Overall success rate (%) |
| `hegemon_cost_by_worker_usd` | gauge | worker | Cost per worker |
| `hegemon_tokens_by_worker` | gauge | worker | Tokens per worker |
| `hegemon_sessions_by_worker` | gauge | worker | Sessions per worker |
| `hegemon_success_rate_by_worker` | gauge | worker | Success rate per worker |
| `hegemon_cost_by_model_usd` | gauge | model | Cost per LLM model |
| `hegemon_tokens_by_model` | gauge | model | Tokens per LLM model |
| `hegemon_sessions_by_model` | gauge | model | Sessions per LLM model |

**From daemon** (`job="hegemon_daemon"`):
| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `hegemon_worker_health` | gauge | worker | Binary health (1/0) |
| `hegemon_worker_status` | gauge | worker | Status enum (0-3) |
| `hegemon_queue_depth` | gauge | — | Active dispatches |
| `hegemon_daily_cost_usd` | gauge | — | Daily cost (daemon view) |
| `hegemon_budget_remaining_usd` | gauge | — | Remaining budget |
| `hegemon_worker_daily_cost_usd` | gauge | worker | Per-worker daily cost |

### Adding a panel

1. Edit the JSON file
2. Use next available `id` (current max: 31)
3. Follow the `gridPos` grid (24 columns wide, y increments by 8 per row)
4. Always use `${DS_PROMETHEUS}` datasource and `$worker` variable for filtering

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Panels show "No data" | Pushgateway empty or unreachable | `curl -s https://push.gostoa.dev/metrics \| grep hegemon` |
| Worker missing from dropdown | No metrics pushed with that label yet | Trigger an ingest from the worker, check stop-hook |
| Alert not firing | Dedup marker exists, or threshold not reached | Check `pipeline_traces` for today's `cost-alert` entries |
| Alert fires multiple times | `record_cost_alert()` failed after Slack send | Check CP API logs for DB errors on trace commit |
| Stale metrics (old values) | Worker stopped pushing | Check worker health: `hegemon_worker_health{worker="X"}` |
| Grafana 403 | Dashboard not provisioned | `kubectl apply -f k8s/grafana/dashboards/` |
