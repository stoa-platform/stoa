# Demo Script — "ESB is Dead, AI Agents Are Here"

> **Date**: 24 February 2026 | **Duration**: ~20 min
> **Presenter**: Christophe Aboulicam | **Platform**: STOA
> **Setup**: OVH Production (`*.gostoa.dev`) or Docker Compose local

---

## Overview

| Act | Time | What | Key Moment |
|-----|------|------|------------|
| 1 | 0:00 - 3:00 | Console: create tenant + publish API | "Admin in 3 min" |
| 2 | 3:00 - 6:00 | Portal: register consumer, get credentials, token exchange | "5 days → 5 minutes" |
| 3 | 6:00 - 8:00 | Rust Gateway: API call, JWT, zero latency | "Sub-millisecond proxy" |
| 3b | 8:00 - 11:00 | mTLS: enterprise certificate binding (RFC 8705) | "100 clients, zero trust" |
| 4 | 11:00 - 12:00 | Grafana: live dashboards | "Full observability" |
| 5 | 12:00 - 14:00 | OpenSearch: error snapshots, trace search | "Every error, traced" |
| 6 | 14:00 - 16:00 | Keycloak: federation login cross-tenant | "Zero trust, multi-org" |
| 7 | 16:00 - 18:00 | MCP Bridge: OpenAPI → MCP in 3s + AI agent call | "The paradigm shift" |
| 8 | 18:00 - 20:00 | Born GitOps + AI Factory | "The bombshell" |

---

## Pre-Demo Setup (Production)

```bash
# Verify OVH cluster is ready
export KUBECONFIG=~/.kube/config-stoa-ovh
kubectl get pods -n stoa-system
kubectl get pods -n monitoring
kubectl get pods -n opensearch
kubectl get ingress -A
kubectl get certificates -A | grep -v True  # all should be True

# Verify all HTTPS endpoints
for svc in console portal api gateway mcp auth; do
  echo -n "${svc}.gostoa.dev: "
  curl -sI "https://${svc}.gostoa.dev" -o /dev/null -w "%{http_code}"
  echo ""
done
curl -sI https://console.gostoa.dev/grafana -o /dev/null -w "grafana: %{http_code}\n"
curl -sI https://opensearch.gostoa.dev -o /dev/null -w "opensearch: %{http_code}\n"

# Validate mTLS pipeline (Act 3b pre-flight)
./scripts/demo/validate-mtls-flow.sh
# Expected: ALL 8 CHECKS PASSED — if not, fix before demo
```

### Browser Tabs (pre-authenticated)

| Tab | URL | User | Purpose |
|-----|-----|------|---------|
| 1 | https://console.gostoa.dev | halliday | Console (Platform Admin) |
| 2 | https://portal.gostoa.dev | (not logged in) | Portal (developer flow) |
| 3 | Terminal | — | Gateway + curl commands |
| 4 | https://console.gostoa.dev/grafana | admin | Grafana dashboards |
| 5 | https://opensearch.gostoa.dev | admin | OpenSearch Dashboards |
| 6 | https://auth.gostoa.dev | admin | Keycloak admin |

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

## Act 2 — Portal: Register Consumer, Get Credentials, Token Exchange (3 min)

**[Tab 2: Portal — logged in as art3mis (developer)]**

> "Now I switch sides. I'm a developer. I need API access."

### 2.1 — Consumer Registration (1 min)

1. On the Portal **Dashboard**, click **"Register as Consumer"** in Quick Actions
2. Fill the form:
   - Name: "Acme Payments App"
   - Email: "dev@acme.com"
   - Company: "Acme Corp"
3. Click **Register**
4. **CredentialsModal appears** — point out: `client_id`, `client_secret`, `token_endpoint`, cURL snippet

> "Self-service registration. OAuth2 credentials generated instantly. Not in 5 days — right now."

### 2.2 — Get OAuth2 Token (30s)

**[Tab 3: Terminal]** — copy the cURL from CredentialsModal

```bash
# Get a client_credentials token (copy from CredentialsModal)
TOKEN=$(curl -s -X POST ${STOA_AUTH_URL}/realms/stoa/protocol/openid-connect/token \
  -d "grant_type=client_credentials" \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
echo $TOKEN | cut -c1-50
```

> "Standard OAuth2 client_credentials grant. The token is a JWT — signed, auditable, time-limited."

### 2.3 — Token Exchange (1 min)

**[Tab 2: Portal — CredentialsModal still open]**

1. Click the **Token Exchange** tab in the CredentialsModal
2. Paste the `$TOKEN` from the terminal
3. Click **Exchange Token**
4. Show the decoded claims: `consumer_id`, `tenant_id`, scopes
5. Copy the gateway cURL snippet

> "RFC 8693 token exchange. The consumer gets a gateway-scoped token — per-consumer quotas, per-tenant isolation. Enterprise-grade from day one."

### 2.4 — Call Gateway with Exchanged Token (30s)

**[Tab 3: Terminal]**

```bash
# Use the exchanged token to call the gateway
curl -s -H "Authorization: Bearer $EXCHANGED_TOKEN" \
  ${STOA_GATEWAY_URL}/mcp/v1/tools | python3 -m json.tool
```

> "One token, one gateway call. Authentication, rate limiting, audit trail — all automatic."

---

## Act 3 — Rust Gateway: API Call, JWT, Zero Latency (2 min)

**[Tab 3: Terminal]**

> "Now let's use this token. The request goes through our Rust Gateway — built for zero-latency API management."

### 3.1 — Health Check (15s)

```bash
curl https://gateway.gostoa.dev/health
# → OK
```

> "Gateway healthy. Rust. Sub-millisecond overhead."

### 3.2 — Authenticated MCP Call (45s)

```bash
# Use the token from Act 2 — call petstore via MCP protocol
curl -s -X POST https://mcp.gostoa.dev/mcp/v1/tools/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}'
# → {"content": [{"type": "text", "text": "{...httpbin response...}"}]}
```

> "JWT validated, MCP tool invoked, backend called, response in under 50ms. One unified protocol for humans AND AI agents."

### 3.3 — Rate Limiting Demo (1 min)

```bash
# Rapid-fire requests to trigger rate limit
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code} " \
    -X POST https://mcp.gostoa.dev/mcp/v1/tools/invoke \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}'
done
# → 200 200 200 ... 429 429
```

> "Per-consumer rate limiting. The 429 means: 'slow down'. Automatic protection, per plan, per consumer. No configuration needed."

---

## Act 3b — mTLS: Enterprise Certificate Binding (3 min)

**[Tab 3: Terminal]**

> "Now the enterprise killer feature. Your clients have X.509 certificates — from F5, from their PKI. We bind those certificates to OAuth2 tokens. RFC 8705."

### 3b.1 — Show Bulk Onboarding Result (30s)

> "We just onboarded 100 enterprise clients with certificates. Each one got an OAuth2 client with automatic certificate binding. No manual configuration."

```bash
# Pre-seed with mixed profile (run the weekend before the demo):
#   ./scripts/demo/generate-mtls-certs.sh --profile=mixed --count 100
#   python3 scripts/demo/seed-mtls-demo.py --profile=mixed
# Result: 85 active, 8 expiring (7d), 5 expired (1d — naturally expired by demo), 2 revoked

# Show consumer count
curl -s "$API_URL/v1/consumers/acme-corp?page_size=3" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python3 -m json.tool
# → 100 consumers, mixed statuses: active, expiring, expired, revoked
```

### 3b.2 — Show Certificate-Bound Token (45s)

```bash
# Get a cert-bound token (cnf claim embedded automatically by Keycloak)
TOKEN_MTLS=$(curl -s -X POST "$AUTH_URL/realms/stoa/protocol/openid-connect/token" \
  -d "grant_type=client_credentials" \
  -d "client_id=$CONSUMER_CLIENT_ID" \
  -d "client_secret=$CONSUMER_CLIENT_SECRET" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Decode to show the cnf claim
echo $TOKEN_MTLS | python3 -c "
import sys, json, base64
token = sys.stdin.read().strip().split('.')[1]
token += '=' * (4 - len(token) % 4)
claims = json.loads(base64.urlsafe_b64decode(token))
print(json.dumps({'cnf': claims.get('cnf', {}), 'consumer_id': claims.get('consumer_id', '')}, indent=2))
"
# → { "cnf": { "x5t#S256": "<base64url fingerprint>" } }
```

> "Look at the token. The `cnf` claim contains the certificate fingerprint. This token is cryptographically bound to one specific certificate."

### 3b.3 — Correct Certificate → Access Granted (30s)

```bash
# Call gateway with correct certificate headers (F5 injects these after mTLS handshake)
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST "$GATEWAY_URL/mcp/v1/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_MTLS" \
  -H "X-SSL-Client-Verify: SUCCESS" \
  -H "X-SSL-Client-Fingerprint: $CORRECT_FINGERPRINT" \
  -H "X-SSL-Client-S-DN: CN=api-consumer-001,OU=tenant-acme,O=Acme Corp,C=FR" \
  -H "X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR" \
  -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}'
# → HTTP 200 ✅ — Certificate matches token binding
```

> "200 OK. Certificate matches the token. Access granted."

### 3b.4 — Wrong Certificate → Binding Mismatch (45s)

```bash
# Same token, DIFFERENT certificate fingerprint → stolen token scenario
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST "$GATEWAY_URL/mcp/v1/tools/invoke" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN_MTLS" \
  -H "X-SSL-Client-Verify: SUCCESS" \
  -H "X-SSL-Client-Fingerprint: 0000000000000000000000000000000000000000000000000000000000000000" \
  -H "X-SSL-Client-S-DN: CN=attacker,OU=evil-corp,O=Evil Inc,C=XX" \
  -H "X-SSL-Client-I-DN: CN=STOA Demo CA,O=STOA Platform,C=FR" \
  -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}'
# → HTTP 403 MTLS_BINDING_MISMATCH 🚫 — Stolen token detected!
```

> "403. Binding mismatch. Even with a valid JWT, the wrong certificate means instant rejection. This is how you detect stolen tokens."

### 3b.5 — Wrap-Up (30s)

> "RFC 8705. 100 clients onboarded in seconds. Certificate-token binding verified in microseconds. Zero trust, end to end."
>
> "In production, F5 handles TLS termination and injects these headers. The STOA Gateway validates the binding. Rotate a certificate — the binding updates automatically. Revoke one — instant block."

---

## Act 4 — Grafana: Live Dashboards (1 min)

**[Tab 4: Grafana — https://console.gostoa.dev/grafana]**

> "Every request we just made — including the mTLS calls — is already visible in real-time."

### 4.1 — Gateway Metrics (1 min)

1. Open **STOA Gateway Metrics** dashboard
2. Point out:
   - Tool calls/sec graph (shows all the calls we just made)
   - Latency percentiles: p50, p90, p99
   - mTLS binding verifications (if mTLS metrics panel exists)
   - Active SSE connections

> "Real-time gateway metrics. Every API call measured, every mTLS binding verified, every tenant tracked."

---

## Act 5 — OpenSearch: Error Snapshots (2 min)

**[Tab 3: Terminal → then Tab 5: OpenSearch Dashboards]**

> "What happens when things go wrong? Let me show you our error tracking."

### 5.1 — Error Injection + Analysis (1 min)

```bash
# Fire controlled errors through the gateway + seed 50 error snapshots
./scripts/demo/opensearch-live-demo.sh --prod --cleanup
```

Point out terminal output as it runs:
- **Phase 0**: 5 real gateway errors (401, 404, 400) fired live
- **Phase 1**: 50 error snapshots seeded into OpenSearch
- **Phase 2**: Distribution by type (7 types: validation, auth, rate limit, timeout, internal, tool_not_found, contract_violation)
- **Phase 3**: Distribution by tenant (4 tenants, multi-tenant isolation)
- **Phase 4**: Severity breakdown (critical / error / warning)
- **Phase 5**: Live trace lookup — random error with full detail

> "50 errors indexed, classified by type, tenant, and severity. Every one has a trace ID."

### 5.2 — OpenSearch Drill-Down (1 min)

**[Tab 5: OpenSearch Dashboards — https://opensearch.gostoa.dev]**

1. Open **Discover** tab
2. Select index pattern `stoa-errors-*`
3. Filter: last 15 minutes → show 50+ errors
4. Click one error document → show fields:
   - `trace_id` — unique per request
   - `tenant_id` — multi-tenant isolation
   - `error_type` — classification
   - `error_message` — human-readable root cause
   - `endpoint` — which API failed
   - `response_time_ms` — performance data

> "From error to root cause in one click. No grepping, no guessing, no 3-team investigation."

---

## Act 6 — Keycloak: Federation Cross-Tenant (2 min)

**[Tab 6: Keycloak Admin — https://auth.gostoa.dev]**

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
TOKEN_A=$(curl -s -X POST "https://auth.gostoa.dev/realms/demo-org-alpha/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=federation-demo&client_secret=alpha-demo-secret&username=demo-alpha&password=demo" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Decode to show stoa_realm claim
echo $TOKEN_A | python3 -c "import sys,json,base64; t=sys.stdin.read().strip().split('.')[1]; t+='='*(4-len(t)%4); d=json.loads(base64.urlsafe_b64decode(t)); print(json.dumps({k:d[k] for k in ['iss','stoa_realm','preferred_username']}, indent=2))"
# → {"iss": "https://auth.gostoa.dev/realms/demo-org-alpha", "stoa_realm": "demo-org-alpha", "preferred_username": "demo-alpha"}

# Get token from org-beta (different org, different secret)
TOKEN_B=$(curl -s -X POST "https://auth.gostoa.dev/realms/demo-org-beta/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=federation-demo&client_secret=beta-demo-secret&username=demo-beta&password=demo" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Compare issuers — different realms, different tokens, different trust boundaries
echo $TOKEN_B | python3 -c "import sys,json,base64; t=sys.stdin.read().strip().split('.')[1]; t+='='*(4-len(t)%4); d=json.loads(base64.urlsafe_b64decode(t)); print(json.dumps({k:d[k] for k in ['iss','stoa_realm','preferred_username']}, indent=2))"
# → {"iss": "https://auth.gostoa.dev/realms/demo-org-beta", "stoa_realm": "demo-org-beta", "preferred_username": "demo-beta"}
```

> "Zero trust. Two organizations, two realms, two issuers. A token from Organization Alpha cannot impersonate Organization Beta. Enforced cryptographically — different signing keys, different trust boundaries."

---

## Act 7 — MCP Bridge: Legacy API → AI Agent (3 min)

**[Tab 3: Terminal]**

> "Here's the paradigm shift. Everything we've built — APIs, authentication, rate limiting — all of that becomes available to AI agents."

### 7.1 — OpenAPI → MCP Bridge (1 min)

```bash
# Bridge any OpenAPI spec into MCP tools — one command, 3 seconds
stoactl bridge petstore.yaml --namespace tenant-acme \
  --include-tags pets --apply --server-name petstore-mcp
# → ✓ Parsed OpenAPI spec: Petstore v1.0.0
# → ✓ Mapped 5 operations to Tool CRDs
# → Created MCP server "petstore-mcp" (id=...)
# →   + list-pets
# →   + create-pet
# →   + get-pet-by-id
# →   + update-pet
# →   + delete-pet
# → Registered 5 tools on MCP server "petstore-mcp"
```

> "One command. Five tools registered. Three seconds. Any OpenAPI spec becomes MCP-ready."

### 7.2 — MCP Tool Discovery (30s)

```bash
# List available MCP tools (each published API = one MCP tool)
curl -s https://mcp.gostoa.dev/mcp/v1/tools | jq '.[].name'
# → "petstore"
# → "account-management"
# → "payments"
# → "stoa_catalog"
# → ... (12 platform tools + 3 API tools)
```

> "Every API in our catalog is automatically exposed as an MCP tool. Define Once, Expose Everywhere — that's our Universal API Contract."

### 7.3 — AI Agent Call (1:30 min)

```bash
# An AI agent invokes the Petstore API tool
curl -s -X POST https://mcp.gostoa.dev/mcp/v1/tools/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}'
# → {"content": [{"type": "text", "text": "{...httpbin echo...}"}]}

# Now the Payments API — same pattern, different tool
curl -s -X POST https://mcp.gostoa.dev/mcp/v1/tools/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tool": "payments", "arguments": {"action": "get-status"}}'
# → {"content": [{"type": "text", "text": "{...httpbin echo...}"}]}
```

> "A Claude agent, a GPT agent, any MCP-compatible agent — they can now call your enterprise APIs. With authentication, rate limiting, monitoring, and audit trail. All the governance you need, none of the friction."

> "This is not an API gateway. This is a **bridge** between your legacy enterprise and the AI-native future."

---

## Act 8 — Born GitOps + AI Factory (3 min)

**[Slide: "How We're Different"]**

> "Before I tell you how we built this, let me tell you why we're different."

### 8.1 — Born GitOps (1:30 min)

> "Every API management platform you know — Kong, Apigee, MuleSoft, Gravitee — they all started with a database. A UI. Click to deploy. Then, years later, they bolted on GitOps. A CLI here, a Maven plugin there."

> "STOA is different. We're **Born GitOps**. Git IS the control plane — not a sync target."

**[Slide: Competitive landscape table]**

| | GitOps | Source of Truth | Prod Approval |
|---|--------|----------------|---------------|
| Kong | decK (2019, retrofit) | Database | PR reviews |
| Apigee | Maven (2015, retrofit) | Database | RBAC only |
| Gravitee | GKO (2023, semi-native) | Database + Cockpit | Cockpit SaaS |
| **STOA** | **Born GitOps (2026)** | **Git** | **Git PR + CODEOWNERS** |

> "What does that mean concretely?"

**[Slide: Promote with Confidence workflow]**

```
Console (staging) → "Promote to Prod" →
  1. Git PR generated automatically (with staging health report)
  2. CODEOWNERS review (your team approves, not ours)
  3. Merge → ArgoCD sync → Canary deploy (10% → 50% → 100%)
  4. If metrics degrade → automatic rollback via git revert
```

> "Every production change is a Git commit. Every rollback is a git revert. Your compliance team can audit everything. Your DSI sleeps at night."

> "Our Universal API Contract — the UAC — travels intact from staging to production. Same artifact, different configuration. Define Once, Promote Everywhere."

### 8.2 — AI Factory (1:30 min)

**[Terminal showing git log]**

> "Now, how did we build all of this?"

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
| 11:00 | Act 3b done | Skip wrong-cert demo (step 3b.4), just show success + explain |
| 12:00 | Act 4 done | Show 1 dashboard, 30s max |
| 14:00 | Act 5 done | Skip drill-down, show table only |
| 16:00 | Act 6 done | Skip curl demo, show Keycloak realms only |
| 18:00 | Act 7 done | Pre-record MCP call as video backup |
| 20:00 | Act 8 done | Skip GitOps slide, go straight to AI Factory punchline |

## If Something Breaks

| Problem | Immediate Action |
|---------|-----------------|
| Console won't load | Show Portal instead (Acts 1-2 combined) |
| Gateway returns 500 | Show pre-recorded terminal output |
| Grafana empty | Show screenshot in slides |
| OpenSearch down | "Error tracking is indexing, let me show you the architecture" |
| mTLS binding fails | Show pre-decoded JWT with cnf claim (screenshot) + explain RFC 8705 |
| Federation token fails | Show Keycloak admin UI realms (visual proof) |
| MCP endpoint missing | "The MCP bridge is in development — let me show you the architecture" |
| Everything down | Switch to video backup (offline, pre-recorded) |

## Personas & Credentials

| Persona | URL | Credentials | Role |
|---------|-----|-------------|------|
| halliday | Console | _(see realm JSON)_ | Platform Admin |
| parzival | Console | _(see realm JSON)_ | Tenant Admin (OASIS Gunters) |
| art3mis | Portal | _(see realm JSON)_ | Developer |
| admin | Grafana | _(OIDC SSO)_ | Monitoring |
| admin | OpenSearch | _(Infisical `prod/opensearch`)_ | Logs |
| admin | Keycloak | _(Infisical `prod/keycloak`)_ | Auth Admin |
| demo-alpha | Federation (alpha) | _(see federation realm)_ | Demo Org Alpha user |
| demo-beta | Federation (beta) | _(see federation realm)_ | Demo Org Beta user |

---

*Generated for the "ESB is Dead" demo — 24 February 2026*
