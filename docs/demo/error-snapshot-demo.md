# Error Snapshot Demo — "Error Correlation in Real-Time"

> **CAB-550** | Duration: 2 minutes
> Segment type: Technical deep-dive (add-on to main demo)

---

## Overview

| Segment | Time | What |
|---------|------|------|
| Setup | 0:00 - 0:20 | Context: why error correlation matters |
| Trigger | 0:20 - 0:50 | Fire API calls that produce errors |
| Show | 0:50 - 1:40 | OpenSearch dashboard with correlated traces |
| Close | 1:40 - 2:00 | Takeaway |

---

## Architecture

```
Client ──▶ API Gateway ──▶ MCP Gateway ──▶ Backend Service
  │              │                │                │
  └──trace_id────┴────trace_id───┴────trace_id────┘
                                                    │
                                            OpenSearch ◀──┘
                                          (all errors correlated
                                           by trace_id)
```

Each request gets a unique `trace_id` propagated through the entire chain. When an error occurs at any layer, all logs share the same `trace_id` for instant correlation.

---

## 0:00 - 0:20 | SETUP

> "When something breaks in a distributed system, the first question is always: **where** did it break? With traditional gateways, you get a 500 error and good luck finding the root cause."

> "STOA traces every request end-to-end. Let me show you."

---

## 0:20 - 0:50 | TRIGGER

**[Switch: terminal]**

Run the live demo script against production:

```bash
./scripts/demo/opensearch-live-demo.sh --prod --cleanup
```

> "I'm firing real errors through the gateway, then seeding 50 error snapshots."

The script runs 6 phases automatically:
1. **Phase 0**: 5 controlled gateway errors (401, 404, 400) — live, real requests
2. **Phase 1**: 50 error snapshots seeded into OpenSearch (`stoa-errors-*`)
3. **Phases 2-4**: Terminal analysis — type, tenant, and severity distribution
4. **Phase 5**: Live trace lookup — one random error with full details

> "Each error has a unique trace ID. Let's see what that looks like."

---

## 0:50 - 1:40 | SHOW

**[Switch: browser — OpenSearch Dashboards at https://opensearch.gostoa.dev]**

1. Open **Discover** tab (pre-authenticated — see `OPENSEARCH_AUTH` env var)
2. Select index pattern `stoa-errors-*`
3. Filter by last 15 minutes → 50+ errors visible

> "50 errors — each with a trace ID, tenant, and classification."

4. Click on any error entry
5. Show the full document with fields:
   - `trace_id` — unique request identifier
   - `tenant_id` — which organization this error belongs to
   - `error_type` — classification (validation, auth, rate_limit, timeout...)
   - `error_message` — human-readable root cause
   - `http_status` — error code
   - `endpoint` — which API endpoint failed
   - `response_time_ms` — how long it took

> "From error to root cause in one click. No grepping, no guessing, no 3-team investigation."

---

## 1:40 - 2:00 | CLOSE

> "In a traditional setup, this investigation takes 30 minutes and involves 3 teams. With STOA, it takes **one click** and **10 seconds**."

> "Every API call, every error, every trace — correlated automatically."

---

## Presenter Notes

### Prerequisites

- OpenSearch Dashboards accessible at `https://opensearch.gostoa.dev` (auth: `$OPENSEARCH_AUTH` from Infisical `prod/opensearch`)
- Gateway accessible at `https://mcp.gostoa.dev`
- Index pattern `stoa-errors-*` (created automatically by the seed script)

### Pre-Demo Setup

```bash
# Verify OpenSearch is up (get password from Infisical: prod/opensearch/ADMIN_PASSWORD)
curl -sk -u "admin:${OPENSEARCH_ADMIN_PASSWORD}" https://opensearch.gostoa.dev/_cluster/health | python3 -m json.tool

# Verify gateway is up
curl -sk https://mcp.gostoa.dev/health

# Optional: dry run the seed script first
python3 scripts/demo/seed-error-snapshot.py --seed-opensearch \
  --opensearch-url https://opensearch.gostoa.dev \
  --opensearch-auth "admin:${OPENSEARCH_ADMIN_PASSWORD}" --count 5

# Pre-open OpenSearch Dashboards in a browser tab
```

### If OpenSearch Is Down

Skip this segment entirely. Mention:

> "We also have full error correlation via OpenSearch — I'll share the dashboard link after the session."

Show a pre-captured screenshot instead (keep in slide deck as backup).

### Timing Checkpoints

| Time | Checkpoint | If Late |
|------|-----------|---------|
| 0:20 | Context done | Skip to trigger |
| 0:50 | Errors fired | Skip terminal, go to dashboard |
| 1:40 | Dashboard shown | Go straight to close |
