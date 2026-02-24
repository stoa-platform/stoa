---
name: analytics
description: Query platform data — PostgreSQL (prod), token costs, Prometheus metrics, GitHub CI stats, K8s pod status.
argument-hint: "<query-name or free-form question>"
---

# Analytics Skill

Query STOA platform data across 5 sources. All queries are **read-only**.

## Data Sources

| # | Source | Access | Auth |
|---|--------|--------|------|
| 1 | **PostgreSQL** (OVH Managed) | `psql` direct | Infisical `/prod/database` |
| 2 | **Token Observatory** | Local files | None (filesystem) |
| 3 | **Pushgateway / Prometheus** | HTTP API | None (IP-whitelisted) |
| 4 | **GitHub CI** | `gh` CLI | GitHub token (ambient) |
| 5 | **Kubernetes** | `kubectl` | kubeconfig (ambient) |

## Connection Patterns

### PostgreSQL

```bash
eval $(infisical-token)
DB_URL=$(infisical secrets get DATABASE_URL --env=prod --path=/database --plain 2>/dev/null)
psql "$DB_URL" -c "<QUERY>"
```

Fallback (direct):
```bash
psql "postgresql://avnadmin:<password>@postgresql-1a861124-o65d47357.database.cloud.ovh.net:20184/stoa_production?sslmode=require"
```

### Token Observatory

```bash
# Today's stats
cat ~/.claude/stats-cache.json | python3 -m json.tool

# Historical (metrics.log)
grep "TOKEN-SPEND" ~/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/metrics.log
```

### Pushgateway

```bash
curl -s https://pushgateway.gostoa.dev/metrics | grep gateway_arena
```

### GitHub CI

```bash
gh run list --limit 10 --json name,status,conclusion,startedAt,updatedAt
gh run view <run-id> --log-failed
```

### Kubernetes

```bash
kubectl get pods -n stoa-system -o wide
kubectl top pods -n stoa-system
```

## Pre-Built Queries

### 1. `tenant-count` — Total tenants
```sql
SELECT COUNT(*) AS total_tenants FROM tenants WHERE deleted_at IS NULL;
```

### 2. `api-count` — APIs by tenant
```sql
SELECT t.name AS tenant, COUNT(a.id) AS apis
FROM apis a JOIN tenants t ON a.tenant_id = t.id
WHERE a.deleted_at IS NULL
GROUP BY t.name ORDER BY apis DESC;
```

### 3. `user-count` — Active users
```sql
SELECT COUNT(*) AS total_users FROM users WHERE is_active = true;
```

### 4. `gateway-instances` — Registered gateways
```sql
SELECT name, gateway_type, status, base_url, last_health_check
FROM gateway_instances ORDER BY last_health_check DESC;
```

### 5. `recent-deployments` — Last 10 API deployments
```sql
SELECT a.name AS api, d.status, d.gateway_type, d.created_at
FROM deployments d JOIN apis a ON d.api_id = a.id
ORDER BY d.created_at DESC LIMIT 10;
```

### 6. `subscription-stats` — Subscriptions by status
```sql
SELECT status, COUNT(*) FROM subscriptions GROUP BY status ORDER BY count DESC;
```

### 7. `token-cost-7d` — Token costs last 7 days
```bash
grep "TOKEN-SPEND" ~/.claude/projects/-Users-torpedo-hlfh-repos-stoa/memory/metrics.log | tail -7
```

### 8. `ci-health` — CI pass rate last 20 runs
```bash
gh run list --limit 20 --json conclusion | python3 -c "
import json,sys; runs=json.load(sys.stdin)
total=len(runs); ok=sum(1 for r in runs if r['conclusion']=='success')
print(f'{ok}/{total} passed ({100*ok//total}%)')
"
```

### 9. `arena-scores` — Gateway Arena latest scores
```bash
curl -s https://pushgateway.gostoa.dev/metrics | grep 'gateway_arena_score{' | sort
```

### 10. `pod-status` — All pods health
```bash
kubectl get pods -n stoa-system --no-headers | awk '{print $1, $2, $3}'
```

### 11. `db-size` — Database size
```sql
SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;
```

### 12. `table-sizes` — Top 10 tables by size
```sql
SELECT relname AS table, pg_size_pretty(pg_total_relation_size(relid)) AS size
FROM pg_catalog.pg_statio_user_tables
ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;
```

## Usage

```
User: /analytics tenant-count
User: /analytics How many APIs are deployed on Kong?
User: /analytics token-cost-7d
User: /analytics What's the CI pass rate this week?
```

For free-form questions, map to the closest pre-built query or compose a custom one.

## Rules

- **Read-only**: never INSERT, UPDATE, DELETE, or DROP
- **Limit results**: always add `LIMIT 50` to unbounded queries
- **Sensitive data**: never display passwords, tokens, or PII columns
- **Cost**: prefer pre-built queries over full table scans
