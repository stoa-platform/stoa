<!-- AUTO-GENERATED from stoa-impact.db — DO NOT EDIT MANUALLY -->
<!-- Regenerate: python3 docs/scripts/regenerate-docs.py -->
<!-- Last generated: 2026-03-26 20:35 -->

# STOA Platform — End-to-End Scenarios

> **6** scenarios | **0** in CI | **3 P0 untested**

## P0 — Critical

### SCEN-001: Developer Self-Service Subscription
**Actor**: api-consumer | **Test**: none | **NO CI**  
Portal signup → search → subscribe → approve → credentials

| # | Component | Action | Contract | Expected Result |
|---|---|---|---|---|
| 1 | `portal` | Consumer visits signup page | `pt-cp-007` | Tenant created via self-service |
| 2 | `portal` | Consumer logs in via Keycloak OIDC | `pt-kc-001` | Authenticated session with JWT |
| 3 | `portal` | Consumer searches API catalog | `pt-cp-001` | List of published APIs matching search |
| 4 | `portal` | Consumer creates subscription | `pt-cp-002` | Subscription created with pending status |
| 5 | `control-plane-api` | CP emits app.lifecycle Kafka event | `cp-kf-007` | Subscription event dispatched |
| 6 | `console` | Admin views pending subscriptions | `cs-cp-004` | List of subscriptions awaiting approval |
| 7 | `console` | Admin approves subscription | `cs-cp-004` | Subscription activated, API key generated |
| 8 | `control-plane-api` | CP creates Keycloak client for consumer | `cp-kc-001` | OAuth client provisioned in Keycloak |
| 9 | `control-plane-api` | CP persists subscription | `cp-pg-001` | Subscription + credentials stored |
| 10 | `portal` | Consumer retrieves credentials | `pt-cp-002` | API key returned for use |

**Contracts traversed**: `cp-kc-001` **UNTYPED**, `cp-kf-007` **UNTYPED**, `cp-pg-001`, `cs-cp-004` **UNTYPED**, `pt-cp-001` **UNTYPED**, `pt-cp-002` **UNTYPED**, `pt-cp-007` **UNTYPED**, `pt-kc-001`

### SCEN-002: MCP Tool Invocation via AI Client
**Actor**: ai-client | **Test**: integration | **NO CI**  
OAuth discovery → DCR → token → tool list → tool call

| # | Component | Action | Contract | Expected Result |
|---|---|---|---|---|
| 1 | `stoa-gateway` | Claude.ai fetches /.well-known/oauth-protected-resource | `gw-oauth-001` | Returns authorization_servers pointing to gateway |
| 2 | `stoa-gateway` | Claude.ai fetches /.well-known/oauth-authorization-server | `gw-oauth-002` | Returns curated metadata with token_endpoint_auth_methods: [none] |
| 3 | `stoa-gateway` | Claude.ai registers client via POST /oauth/register | `gw-kc-002` | Client registered in KC, patched to publicClient + PKCE S256 |
| 4 | `stoa-gateway` | Claude.ai exchanges auth code for token via POST /oauth/token | `gw-kc-003` | Access token returned (proxied through gateway) |
| 5 | `stoa-gateway` | Claude.ai calls POST /mcp/tools/list | `gw-mcp-002` | Tool catalog returned with schemas |
| 6 | `stoa-gateway` | Gateway validates API key via CP API | `gw-cp-003` | API key validated, subscription confirmed |
| 7 | `stoa-gateway` | Claude.ai calls POST /mcp/tools/call with tool invocation | `gw-mcp-002` | Tool executed, result returned with credential injection |
| 8 | `stoa-gateway` | Gateway emits metering event to Kafka | `gw-kf-001` | Call metered for billing/analytics |

**Contracts traversed**: `gw-cp-003`, `gw-kc-002` **UNTYPED**, `gw-kc-003`, `gw-kf-001` **UNTYPED**, `gw-mcp-002`, `gw-oauth-001`, `gw-oauth-002`

### SCEN-003: API Deployment to Gateway
**Actor**: platform-admin | **Test**: unit | **NO CI**  
Console deploy → adapter → gateway sync → Kafka event → Slack

| # | Component | Action | Contract | Expected Result |
|---|---|---|---|---|
| 1 | `console` | Admin logs in via Keycloak | `cs-kc-001` | Authenticated with stoa:write scope |
| 2 | `console` | Admin creates deployment | `cs-cp-005` | Deployment request sent to CP API |
| 3 | `control-plane-api` | CP selects adapter via AdapterRegistry.create(gateway_type) | — | Adapter instantiated for target gateway |
| 4 | `control-plane-api` | Adapter calls sync_api() on gateway admin API | `cp-gw-001` | API definition pushed to gateway |
| 5 | `control-plane-api` | CP persists GatewayDeployment record | `cp-pg-001` | Deployment state stored in DB |
| 6 | `control-plane-api` | CP emits deployment.events Kafka event | `cp-kf-002` | Deployment progress event dispatched |
| 7 | `control-plane-api` | SyncEngine reconciles DB vs gateway state (every 300s) | — | Drift detected and corrected |

**Contracts traversed**: `cp-gw-001`, `cp-kf-002` **UNTYPED**, `cp-pg-001`, `cs-cp-005` **UNTYPED**, `cs-kc-001`

## P1 — Important

### SCEN-004: Admin Login + Dashboard
**Actor**: platform-admin | **Test**: none | **NO CI**  
Browser → OIDC → Console → CP API → metrics → SSE events

| # | Component | Action | Contract | Expected Result |
|---|---|---|---|---|
| 1 | `console` | Browser navigates to console.gostoa.dev | — | nginx serves SPA |
| 2 | `console` | Console initiates OIDC login | `cs-kc-001` | Authorization Code + PKCE flow with Keycloak |
| 3 | `console` | Console fetches platform data | `cs-cp-001` | Tenants, APIs, users loaded |
| 4 | `console` | Console fetches business metrics | `cs-cp-014` | KPIs displayed (API calls, subscribers, revenue) |
| 5 | `console` | Console opens SSE stream | `cs-cp-015` | Real-time events flowing |

**Contracts traversed**: `cs-cp-001` **UNTYPED**, `cs-cp-014` **UNTYPED**, `cs-cp-015` **UNTYPED**, `cs-kc-001`

### SCEN-005: Gateway Auto-Registration
**Actor**: gateway | **Test**: unit | **NO CI**  
Gateway startup → register → heartbeat loop → health worker check

| # | Component | Action | Contract | Expected Result |
|---|---|---|---|---|
| 1 | `stoa-gateway` | Gateway starts and calls POST /v1/gateway/internal/register | `gw-cp-001` | Gateway registered with instance ID |
| 2 | `control-plane-api` | CP creates GatewayInstance record | `cp-pg-001` | Gateway persisted in database |
| 3 | `stoa-gateway` | Gateway sends heartbeat every 30s | `gw-cp-002` | last_seen updated, status confirmed |
| 4 | `control-plane-api` | GatewayHealthWorker checks stale gateways (90s timeout) | — | Stale gateways marked offline |

**Contracts traversed**: `cp-pg-001`, `gw-cp-001`, `gw-cp-002`

### SCEN-006: Consumer mTLS Certificate Lifecycle
**Actor**: api-consumer | **Test**: none | **NO CI**  
CSR → sign → configure gateway → mTLS verify → RFC 8705

| # | Component | Action | Contract | Expected Result |
|---|---|---|---|---|
| 1 | `console` | Admin generates tenant CA via POST /v1/tenants/{tid}/ca | `cs-cp-003` | CA keypair generated in-memory |
| 2 | `console` | Admin creates consumer | `cs-cp-003` | Consumer registered in CP API |
| 3 | `console` | Consumer submits CSR, admin signs via POST /v1/tenants/{tid}/ca/sign | `cs-cp-003` | Certificate signed with tenant CA |
| 4 | `control-plane-api` | CP configures mTLS on gateway via adapter | `cp-gw-001` | Gateway updated with cert trust chain |
| 5 | `stoa-gateway` | Consumer connects with mTLS, gateway verifies cert | `gw-kc-001` | RFC 8705 certificate-bound token validated |

**Contracts traversed**: `cp-gw-001`, `cs-cp-003` **UNTYPED**, `gw-kc-001`

## Impact Summary

Components by scenario count (most critical first):

- **console**: 4 scenarios
- **control-plane-api**: 4 scenarios
- **stoa-gateway**: 3 scenarios
- **portal**: 1 scenarios

## P0 Scenarios Without CI Coverage

- **SCEN-001**: Developer Self-Service Subscription
- **SCEN-002**: MCP Tool Invocation via AI Client
- **SCEN-003**: API Deployment to Gateway
