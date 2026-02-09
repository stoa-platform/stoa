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

Run the seed script to generate controlled errors:

```bash
python scripts/demo/seed-error-snapshot.py \
  --api-url https://api.<BASE_DOMAIN> \
  --execute
```

> "I'm sending 3 types of requests that will fail at different layers."

Point out each error type as it fires:

1. **400 Bad Request** — invalid payload, caught at API layer
2. **500 Internal Server Error** — backend failure, propagated through gateway
3. **504 Gateway Timeout** — slow upstream, gateway times out

> "Each error has a unique trace ID. Let's see what that looks like."

---

## 0:50 - 1:40 | SHOW

**[Switch: browser — OpenSearch Dashboards]**

1. Navigate to `https://opensearch.<BASE_DOMAIN>/_dashboards`
2. Open the **STOA Error Correlation** dashboard (or Discover tab)
3. Filter by last 5 minutes

> "Here are all 3 errors, each with their trace ID."

4. Click on the **500 Internal Server Error** entry
5. Show the trace_id field
6. Filter by that trace_id

> "One click — and I see the entire request journey. From the client, through the gateway, to the backend that failed. The exact line, the exact service, the exact timestamp."

7. Point out the fields:
   - `trace_id` — same across all log entries
   - `service` — which component logged it
   - `status_code` — error code at each layer
   - `duration_ms` — time spent at each hop
   - `error.message` — root cause

> "No more grepping through 5 different log files. No more guessing which service failed."

---

## 1:40 - 2:00 | CLOSE

> "In a traditional setup, this investigation takes 30 minutes and involves 3 teams. With STOA, it takes **one click** and **10 seconds**."

> "Every API call, every error, every trace — correlated automatically."

---

## Presenter Notes

### Prerequisites

- OpenSearch Dashboards accessible at `https://opensearch.<BASE_DOMAIN>`
- Index pattern `stoa-gateway-*` configured
- Seed script tested in dry-run mode first

### Pre-Demo Setup

```bash
# Verify OpenSearch is up
curl -s https://opensearch.<BASE_DOMAIN>/_cluster/health | python3 -m json.tool

# Dry-run the seed script
python scripts/demo/seed-error-snapshot.py --api-url https://api.<BASE_DOMAIN> --dry-run

# Pre-open dashboard in a browser tab
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
