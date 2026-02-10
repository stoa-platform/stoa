# Demo Script — "ESB is Dead, AI Agents Are Here"

> **Date**: 24 February 2026 | **Duration**: ~20 min
> **Presenter**: Christophe Aboulicam | **Platform**: STOA
> **Setup**: Docker Compose local (17 services) or EKS production

---

## Overview

| Act | Time | What | Key Moment |
|-----|------|------|------------|
| 1 | 0:00 - 3:00 | Console: create tenant + publish API | "Admin in 3 min" |
| 2 | 3:00 - 6:00 | Portal: discover, subscribe, get token | "5 days → 5 minutes" |
| 3 | 6:00 - 8:00 | Rust Gateway: API call, JWT, zero latency | "Sub-millisecond proxy" |
| 4 | 8:00 - 10:00 | Grafana: live dashboards, real-time metrics | "Full observability" |
| 5 | 10:00 - 12:00 | OpenSearch: error snapshots, trace search | "Every error, traced" |
| 6 | 12:00 - 14:00 | Keycloak: federation login cross-tenant | "Zero trust, multi-org" |
| 7 | 14:00 - 17:00 | MCP Bridge: legacy API → AI agent tool | "The paradigm shift" |
| 8 | 17:00 - 19:00 | AI Factory: how this was built | "The bombshell" |

---

## Pre-Demo Setup

```bash
# Start the platform (with federation for Act 6)
cd deploy/docker-compose
docker compose --profile federation up -d

# Wait for all services to be healthy (~60s)
../../scripts/demo/check-health.sh --wait --federation

# Seed demo data (auto-handles: Keycloak SSL, LDAP users, APIs, OpenSearch errors, federation tests)
CONTROL_PLANE_URL=http://localhost:8000 \
KEYCLOAK_URL=http://localhost:8080 \
ANORAK_USER=halliday \
ANORAK_PASSWORD=readyplayerone \
SEED_TENANT=oasis \
  ../../scripts/demo/seed-all.sh --federation

# Expected: 7/7 steps PASS, 9/9 federation isolation tests PASS
```

### Browser Tabs (pre-authenticated)

| Tab | URL | User | Purpose |
|-----|-----|------|---------|
| 1 | http://localhost | halliday | Console (Platform Admin) |
| 2 | http://localhost/portal | (not logged in) | Portal (developer flow) |
| 3 | Terminal | — | Gateway + curl commands |
| 4 | http://localhost/grafana | admin | Grafana dashboards |
| 5 | http://localhost/logs | admin | OpenSearch Dashboards |
| 6 | http://localhost/auth | admin | Keycloak admin |

---

## Act 1 — Console: Create Tenant + Publish API (3 min)

**[Tab 1: Console — logged in as halliday]**

> "I'm the platform admin. Let me show you how fast we can set up a new team."

### 1.1 — Dashboard Overview (30s)

1. Show the Dashboard: tenant count, API count, active subscriptions
2. Point out the sidebar: APIs, Tenants, Consumers, Monitoring

> "Real-time overview. Every tenant, every API, every subscription — visible instantly."

### 1.2 — Create a Tenant (1 min)

1. Click **Tenants** in sidebar
2. Click **Create Tenant**
3. Fill in: Name = "Acme Corp", Slug = "acme-corp"
4. Submit

> "New organization provisioned in seconds. Keycloak realm, RBAC roles, namespace — all automated."

### 1.3 — Publish an API (1:30 min)

1. Click **API Catalog** in sidebar
2. Click **Add API**
3. Fill in:
   - Name: "Payments API"
   - Version: "v1"
   - Backend URL: "https://httpbin.org/anything"
   - Description: "Enterprise payment processing"
4. Submit
5. Show the API detail page with endpoints

> "API published to the catalog. Developers can discover it immediately — no email, no ticket, no Confluence page."

---

## Act 2 — Portal: Discover, Subscribe, Get Token (3 min)

**[Tab 2: Portal — fresh browser, not logged in]**

> "Now I switch sides. I'm a developer. I heard there's a Payments API available."

### 2.1 — Self-Registration (30s)

1. Click **Sign Up**
2. Fill registration form (or show it's pre-configured via Keycloak)
3. Redirect to portal catalog

> "Self-service registration. No ServiceNow ticket required."

### 2.2 — API Discovery (1 min)

1. Browse the API Catalog
2. Search for "payments"
3. Click on **Payments API**
4. Show: description, endpoints, OpenAPI spec tab

> "Full API documentation, searchable, always up-to-date. Not a shared Excel file."

### 2.3 — Subscribe + Get Token (1:30 min)

1. Click **Subscribe**
2. Select application and plan
3. Confirm
4. **Show the generated API key / JWT token**

> "One click. Credentials generated instantly. Not in 5 days. Right now."

5. Copy the token for Act 3

---

## Act 3 — Rust Gateway: API Call, JWT, Zero Latency (2 min)

**[Tab 3: Terminal]**

> "Now let's use this token. The request goes through our Rust Gateway — built for zero-latency API management."

### 3.1 — Health Check (15s)

```bash
curl http://localhost/gateway/health
# → {"status":"healthy","mode":"edge-mcp","version":"0.1.0"}
```

> "Gateway healthy. Rust. Sub-millisecond overhead."

### 3.2 — Authenticated API Call (45s)

```bash
# Use the token from Act 2
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8081/v1/proxy/payments/status
# → 200 OK with response
```

> "JWT validated, request proxied to backend, response in under 10ms. Try that with your ESB."

### 3.3 — Rate Limiting Demo (1 min)

```bash
# Rapid-fire requests to trigger rate limit
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code} " \
    -H "Authorization: Bearer $TOKEN" \
    http://localhost:8081/v1/proxy/payments/status
done
# → 200 200 200 ... 429 429
```

> "Per-consumer rate limiting. The 429 means: 'slow down'. Automatic protection, per plan, per consumer. No configuration needed."

---

## Act 4 — Grafana: Live Dashboards (2 min)

**[Tab 4: Grafana — http://localhost/grafana]**

> "Every request we just made is already visible in real-time."

### 4.1 — Gateway Metrics (1 min)

1. Open **STOA Gateway Metrics** dashboard
2. Point out:
   - Tool calls/sec graph (shows the burst we just did)
   - Latency percentiles: p50, p90, p99
   - Rate limit hits (the 429s are visible)
   - Active SSE connections

> "Real-time gateway metrics. Every API call measured, every rate limit tracked."

### 4.2 — Platform Overview (1 min)

1. Open **STOA Platform Overview** dashboard
2. Show:
   - Total APIs, tenants, active subscriptions
   - Request volume over time
   - Error rate

> "Platform-wide observability. Not a black box. Every metric, every tenant, every API."

---

## Act 5 — OpenSearch: Error Snapshots (2 min)

**[Tab 5: OpenSearch Dashboards or Grafana Error Snapshots]**

> "What happens when things go wrong? Let me show you our error tracking."

### 5.1 — Error Snapshots Dashboard (1 min)

1. Open **STOA Error Snapshots** dashboard in Grafana
2. Point out:
   - Total errors count
   - Errors by status code (pie chart: 400, 401, 404, 429, 500, 504)
   - Errors by tenant (pie chart)
   - Error timeline (stacked bar chart)

> "Every error captured with context: tenant, trace ID, status code, timestamp."

### 5.2 — Trace ID Drill-Down (1 min)

1. Scroll to **Recent Errors** table
2. Click a trace ID → opens OpenSearch Dashboards
3. Show the full error document: trace_id, error_message, endpoint, method

> "Click any trace ID to get the full picture. From dashboard to root cause in one click."

---

## Act 6 — Keycloak: Federation Cross-Tenant (2 min)

**[Tab 6: Keycloak Admin — http://localhost/auth]**

> "Now the enterprise killer feature: identity federation."

### 6.1 — Show Federation Architecture (45s)

1. In Keycloak admin, show the 6 realms:
   - `stoa` (main platform)
   - `idp-source-alpha`, `idp-source-beta` (identity providers)
   - `demo-org-alpha`, `demo-org-beta`, `demo-org-gamma` (tenant orgs)
2. Click on `demo-org-gamma` → Identity Providers → show LDAP federation

> "Six realms. Each organization keeps their own identity provider — Active Directory, LDAP, SAML, OIDC. STOA federates them all."

### 6.2 — Cross-Realm Token Isolation (1:15 min)

```bash
# Get token from org-alpha (confidential client)
TOKEN_A=$(curl -s -X POST "http://localhost:8080/realms/demo-org-alpha/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=federation-demo&client_secret=alpha-demo-secret&username=demo-alpha&password=demo" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Decode to show stoa_realm claim
echo $TOKEN_A | python3 -c "import sys,json,base64; t=sys.stdin.read().strip().split('.')[1]; t+='='*(4-len(t)%4); d=json.loads(base64.urlsafe_b64decode(t)); print(json.dumps({k:d[k] for k in ['iss','stoa_realm','preferred_username']}, indent=2))"
# → {"iss": "http://localhost/auth/realms/demo-org-alpha", "stoa_realm": "demo-org-alpha", "preferred_username": "demo-alpha"}

# Get token from org-beta (different org, different secret)
TOKEN_B=$(curl -s -X POST "http://localhost:8080/realms/demo-org-beta/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=federation-demo&client_secret=beta-demo-secret&username=demo-beta&password=demo" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Compare issuers — different realms, different tokens, different trust boundaries
echo $TOKEN_B | python3 -c "import sys,json,base64; t=sys.stdin.read().strip().split('.')[1]; t+='='*(4-len(t)%4); d=json.loads(base64.urlsafe_b64decode(t)); print(json.dumps({k:d[k] for k in ['iss','stoa_realm','preferred_username']}, indent=2))"
# → {"iss": "http://localhost/auth/realms/demo-org-beta", "stoa_realm": "demo-org-beta", "preferred_username": "demo-beta"}
```

> "Zero trust. Two organizations, two realms, two issuers. A token from Organization Alpha cannot impersonate Organization Beta. Enforced cryptographically — different signing keys, different trust boundaries."

---

## Act 7 — MCP Bridge: Legacy API → AI Agent (3 min)

**[Tab 3: Terminal]**

> "Here's the paradigm shift. Everything we've built — APIs, authentication, rate limiting — all of that becomes available to AI agents."

### 7.1 — MCP Tool Discovery (1 min)

```bash
# List available MCP tools
curl http://localhost:8081/mcp/v1/tools
# → [{"name": "payments-api", "description": "Enterprise payment processing", ...}]
```

> "Every API in our catalog is automatically exposed as an MCP tool. Define Once, Expose Everywhere — that's our Universal API Contract."

### 7.2 — AI Agent Call (2 min)

```bash
# An AI agent invokes the tool
curl -X POST http://localhost:8081/mcp/v1/tools/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tool": "payments-api", "arguments": {"action": "get-status"}}'
# → {"result": {"status": "active", "last_transaction": "..."}}
```

> "A Claude agent, a GPT agent, any MCP-compatible agent — they can now call your enterprise APIs. With authentication, rate limiting, monitoring, and audit trail. All the governance you need, none of the friction."

> "This is not an API gateway. This is a **bridge** between your legacy enterprise and the AI-native future."

---

## Act 8 — AI Factory: How This Was Built (2 min)

**[Slide or terminal showing git log]**

> "One last thing. Let me tell you how we built this platform."

```bash
# Show the velocity
git log --oneline --since="2026-02-09" | wc -l
# → 22 PRs in 2 days

git shortlog --since="2026-02-09" -sn
# → 225 points delivered
```

> "225 story points. 22 pull requests. 2 days."

> "This entire platform — the Rust gateway, the React console, the developer portal, the federation system, the MCP bridge, the observability stack, the error tracking — all of it was built by a team of 10."

> "10 people doing the work of 300+ developers. How?"

> "AI Agents. Not as a feature of the product — as the DNA of how we build."

> "We don't just sell an AI gateway. We are an AI-native company."

**[Slide: "ESB is Dead. AI Agents Are Here."]**

> "Thank you."

---

## Timing Checkpoints

| Time | Checkpoint | If Behind |
|------|-----------|-----------|
| 3:00 | Act 1 done | Skip tenant creation, show existing |
| 6:00 | Act 2 done | Skip registration, use pre-auth |
| 8:00 | Act 3 done | Skip rate limit demo |
| 10:00 | Act 4 done | Show 1 dashboard instead of 2 |
| 12:00 | Act 5 done | Skip drill-down, show table only |
| 14:00 | Act 6 done | Skip curl demo, show Keycloak realms only |
| 17:00 | Act 7 done | Pre-record MCP call as video backup |
| 19:00 | Act 8 done | Shorten to 30s git stats + punchline |

## If Something Breaks

| Problem | Immediate Action |
|---------|-----------------|
| Console won't load | Show Portal instead (Acts 1-2 combined) |
| Gateway returns 500 | Show pre-recorded terminal output |
| Grafana empty | Show screenshot in slides |
| OpenSearch down | "Error tracking is indexing, let me show you the architecture" |
| Federation token fails | Show Keycloak admin UI realms (visual proof) |
| MCP endpoint missing | "The MCP bridge is in development — let me show you the architecture" |
| Everything down | Switch to video backup (offline, pre-recorded) |

## Personas & Credentials

| Persona | URL | Credentials | Role |
|---------|-----|-------------|------|
| halliday | Console | readyplayerone | Platform Admin |
| parzival | Console | copperkeystart | Tenant Admin (OASIS Gunters) |
| art3mis | Portal | samantha2045 | Developer |
| admin | Grafana | admin / admin | Monitoring |
| admin | OpenSearch | admin / StOa_Admin_2026! | Logs |
| admin | Keycloak | admin / admin | Auth Admin |
| demo-alpha | Federation (alpha) | demo | Demo Org Alpha user |
| demo-beta | Federation (beta) | demo | Demo Org Beta user |

---

*Generated for the "ESB is Dead" demo — 24 February 2026*
