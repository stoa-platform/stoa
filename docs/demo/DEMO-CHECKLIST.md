# Demo Pre-Flight Checklist

> **Date**: 24 February 2026 | "ESB is Dead, AI Agents Are Here"
> Run this checklist **30 minutes before** the presentation.

---

## T-24h: Preparation

- [ ] Full dry-run completed (< 20 min, all 8 acts)
- [ ] Video backup recorded and accessible offline
- [ ] Slide deck exported as PDF (backup)
- [ ] QR code generated and tested (https://docs.gostoa.dev)
- [ ] Terminal font size 18pt+ (readable from back of room)

## T-30min: Infrastructure

### Start Services

```bash
cd deploy/docker-compose

# Start all services with federation
docker compose --profile federation up -d

# Wait for all healthy
../../scripts/demo/check-health.sh --wait --federation

# Seed demo data
ANORAK_PASSWORD=readyplayerone ../../scripts/demo/seed-all.sh --federation
```

### Service Health

```bash
# Quick check all services
../../scripts/demo/check-health.sh --federation
```

- [ ] All 16+ services: HEALTHY
- [ ] One-shot services (db-migrate, opensearch-init): DONE (exited 0)

### Individual Service Checks

| Service | Check | Expected |
|---------|-------|----------|
| Console | `curl -s http://localhost` | 200 (HTML) |
| Portal | `curl -s http://localhost:3002` | 200 (HTML) |
| API | `curl -s http://localhost:8000/health` | 200 |
| Gateway | `curl -s http://localhost:8081/health` | 200 JSON |
| Keycloak | `curl -s http://localhost/auth/realms/stoa` | 200 JSON |
| Grafana | `curl -s http://localhost/grafana/api/health` | 200 |
| OpenSearch | `curl -sfk https://localhost:9200 -u admin:${OPENSEARCH_ADMIN_PASSWORD}` | 200 |
| Federation GW | `curl -s http://localhost:9000/health` | 200 |

- [ ] All services respond 200

### Connectivity

- [ ] Wifi stable (speed test done)
- [ ] Hotspot mobile ready as backup
- [ ] VPN disconnected (avoid latency)

---

## T-15min: Browser Setup

### Open Tabs (Chrome, 125% zoom)

| Tab | URL | Pre-condition |
|-----|-----|---------------|
| 1 | http://localhost | Logged in as **halliday** |
| 2 | http://localhost/portal | NOT logged in (fresh) |
| 3 | Terminal (full screen) | Font 18pt, dark background |
| 4 | http://localhost/grafana | Logged in as **admin** |
| 5 | http://localhost/logs | Logged in as **admin** |
| 6 | http://localhost/auth | Logged in as **admin** |

### Pre-Auth Sessions

1. **Console (Tab 1)** — Login as halliday / readyplayerone
   - [ ] Dashboard loads with stats
   - [ ] Sidebar visible: APIs, Tenants, Consumers, Monitoring

2. **Portal (Tab 2)** — Do NOT login (developer flow starts fresh)
   - [ ] Landing page visible

3. **Grafana (Tab 4)** — Login as admin / admin
   - [ ] STOA Platform Overview dashboard loads
   - [ ] Navigate to STOA Gateway Metrics — verify data exists

4. **OpenSearch (Tab 5)** — Login as admin (password from Infisical: `prod/opensearch/ADMIN_PASSWORD`)
   - [ ] Discover page shows stoa-errors-* index

5. **Keycloak (Tab 6)** — Login as admin / admin
   - [ ] 6 realms visible (stoa + 5 federation)

### Browser State

- [ ] Notifications disabled
- [ ] "Do Not Disturb" enabled (macOS)
- [ ] History/favorites bar hidden
- [ ] Zoom at 125%
- [ ] Dark mode disabled (better for projector)
- [ ] Personal tabs closed

---

## T-5min: Verify Each Act

### Act 1 — Console

- [ ] API Catalog page loads with APIs
- [ ] Tenants page loads
- [ ] Create Tenant form accessible

### Act 2 — Portal

- [ ] API Catalog loads with searchable APIs
- [ ] "Payments" search returns results
- [ ] Subscribe button visible on API detail page

### Act 3 — Gateway

```bash
# Test gateway health
curl -s http://localhost/gateway/health | python3 -m json.tool
```
- [ ] Gateway health returns 200 with mode: "edge-mcp"

### Act 4 — Grafana

- [ ] Gateway Metrics dashboard has data
- [ ] Platform Overview dashboard has data

### Act 5 — OpenSearch

- [ ] Error Snapshots dashboard has data (from seed)
- [ ] Recent Errors table shows entries

### Act 6 — Federation

```bash
# Test federation token (org-alpha)
curl -s -X POST "http://localhost:8080/realms/demo-org-alpha/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=demo-client&username=alice&password=alice123" | python3 -c "import sys,json; t=json.load(sys.stdin); print('OK' if 'access_token' in t else 'FAIL: ' + str(t))"
```
- [ ] Token issued for alice in demo-org-alpha

### Act 7 — MCP Bridge

```bash
# Test MCP tool discovery
curl -s http://localhost:8081/mcp/v1/tools | python3 -m json.tool | head -5
```
- [ ] MCP tools endpoint responds

### Act 8 — Git Stats

```bash
git log --oneline --since="2026-02-09" | wc -l
```
- [ ] Shows 20+ PRs

---

## Terminal Commands (Pre-Typed)

Prepare these in a script or terminal history:

```bash
# Act 3.1 — Gateway health
curl http://localhost/gateway/health | python3 -m json.tool

# Act 3.2 — Authenticated call (replace TOKEN)
export TOKEN="<paste from Act 2>"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8081/v1/proxy/payments/status

# Act 3.3 — Rate limit burst
for i in $(seq 1 20); do curl -s -o /dev/null -w "%{http_code} " -H "Authorization: Bearer $TOKEN" http://localhost:8081/v1/proxy/payments/status; done; echo

# Act 6.2 — Federation token
TOKEN_A=$(curl -s -X POST "http://localhost:8080/realms/demo-org-alpha/protocol/openid-connect/token" -d "grant_type=password&client_id=demo-client&username=alice&password=alice123" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -H "Authorization: Bearer $TOKEN_A" http://localhost:9000/api/org-beta/resource

# Act 7.1 — MCP tools
curl http://localhost:8081/mcp/v1/tools | python3 -m json.tool

# Act 7.2 — MCP invoke
curl -X POST http://localhost:8081/mcp/v1/tools/invoke -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d '{"tool": "payments-api", "arguments": {"action": "get-status"}}'

# Act 8 — Git stats
git log --oneline --since="2026-02-09" | wc -l
```

---

## Plan B: If Something Breaks

| Scenario | Immediate Action |
|----------|-----------------|
| Wifi down | Switch to mobile hotspot |
| Console down | Use Portal for admin demo |
| Gateway 500 | Show pre-recorded terminal output |
| Grafana empty | Show screenshot in slides |
| OpenSearch down | "Indexing in progress" + show architecture slide |
| Federation fails | Show Keycloak admin UI (6 realms visible) |
| MCP endpoint missing | "Bridge is in development" + show architecture |
| Everything down | Switch to video backup (offline) |

---

## Post-Demo

- [ ] Collect contacts (business cards / LinkedIn QR)
- [ ] Note questions asked
- [ ] Screenshot slide with QR code (share on LinkedIn)
- [ ] Write down any bugs noticed during demo
- [ ] Update DRY-RUN report with findings
