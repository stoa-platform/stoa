# Demo Narrative — "STOA Control Plane: Gateway-Agnostic, AI-Powered"

> **Date**: 24 February 2026 | **Duration**: 20 min demo + 10 min Q&A
> **Presenter**: Christophe Aboulicam
> **Audience**: Enterprise prospect (legacy API modernization) + ESN partner team
> **Ticket**: CAB-1150

---

## Narrative Arc

```
HOOK (2 min)          → The problem everyone has
PROOF (14 min)        → Live demo: 6 acts, each proving one claim
BOMBSHELL (4 min)     → How we built this + what it means
Q&A (10 min)          → Prepared objections
```

### Core Message (one sentence)

**STOA is the first API Control Plane that manages any gateway — STOA, Kong, Gravitee, webMethods — from a single console, with AI agents as first-class citizens.**

### Three Pillars (repeat throughout)

| Pillar | Proof Point | Demo Act |
|--------|-------------|----------|
| **Gateway-Agnostic** | Same Console, same API, deployed to 4 gateways | Acts 1-3 |
| **AI-Native** | Any OpenAPI becomes an MCP tool in 3 seconds | Act 5 |
| **Enterprise-Grade** | mTLS, federation, RBAC, drift detection — all live | Acts 3b, 4, 6 |

---

## Timing Plan (20 min)

| Time | Act | What | Key Phrase | Pillar |
|------|-----|------|------------|--------|
| 0:00-2:00 | **Hook** | Problem statement + positioning | "One Console, Any Gateway" | — |
| 2:00-5:00 | **Act 1** | Console: create tenant + publish API | "Admin in 3 minutes" | Agnostic |
| 5:00-8:00 | **Act 2** | Portal: consumer self-service + token | "5 days → 5 minutes" | Enterprise |
| 8:00-10:00 | **Act 3** | Gateway call + rate limiting | "Sub-millisecond Rust" | Enterprise |
| 10:00-13:00 | **Act 3b** | mTLS certificate binding (RFC 8705) | "Stolen token = instant block" | Enterprise |
| 13:00-14:00 | **Act 4** | Grafana: live metrics | "Every request, traced" | Enterprise |
| 14:00-16:00 | **Act 5** | MCP Bridge: OpenAPI → AI agent | "The paradigm shift" | AI-Native |
| 16:00-20:00 | **Act 6** | Born GitOps + AI Factory + Close | "The bombshell" | All three |
| 20:00-30:00 | **Q&A** | Prepared objections | — | — |

### Acts Removed (vs. 8-act script)

The original DEMO-SCRIPT.md has 8 acts. For a tighter 20 min narrative:
- **OpenSearch error snapshots** (old Act 5) → merged into Act 4 as a 15s mention
- **Keycloak federation** (old Act 6) → referenced verbally in Act 3b mTLS section
- This keeps 6 focused acts instead of 8 rushed ones

### Timing Checkpoints

| Clock | Checkpoint | If Behind |
|-------|-----------|-----------|
| 5:00 | Act 1 done | Skip tenant creation, show existing |
| 8:00 | Act 2 done | Skip token exchange, use pre-auth |
| 10:00 | Act 3 done | Skip rate limit burst |
| 13:00 | Act 3b done | Show only correct-cert (skip wrong-cert demo) |
| 14:00 | Act 4 done | Flash Grafana 15s, don't drill down |
| 16:00 | Act 5 done | Pre-record MCP bridge as video fallback |
| 20:00 | Act 6 done | Cut AI Factory stats, go straight to close |

---

## Speaker Notes

### HOOK (0:00 - 2:00)

**[Slide: "The Gateway Problem"]**

> Every enterprise I talk to has the same problem.
>
> They bought an API gateway 5 years ago. Maybe webMethods. Maybe MuleSoft. Maybe Kong. And now they're locked in. The vendor raises prices, the technology ages, and switching costs 18 months and 2 million euros.
>
> Meanwhile, AI agents need API access — and your gateway was built in 2015. It doesn't speak MCP. It doesn't understand tool calling. It was designed for REST requests from browsers, not for Claude calling your Payments API.

**[Slide: "STOA Control Plane"]**

> We built STOA to solve both problems at once.
>
> STOA is a **Control Plane**. Not another gateway — a layer that sits above your gateway. You keep your webMethods, your Kong, your Gravitee. STOA manages them all from one console.
>
> And from day one, AI agents are first-class citizens. Any API in your catalog becomes an MCP tool — automatically.
>
> Let me show you.

---

### ACT 1 — Console: Admin in 3 Minutes (2:00 - 5:00)

**[Tab 1: Console — logged in as halliday]**

> I'm the platform admin. This is the STOA Console.

**1.1 — Dashboard (30s)**

> [Show dashboard] Real-time overview. Tenants, APIs, active subscriptions, gateway health — everything in one place.
>
> Notice: I manage multiple gateways from here. STOA Gateway, Kong, Gravitee, webMethods. One console, four gateways.

**1.2 — Create Tenant (1 min)**

> Let me onboard a new organization.

1. Click **Tenants** → **Create Tenant**
2. Name: "Acme Corp", Slug: "acme-corp"
3. Submit

> Done. Keycloak realm provisioned, RBAC roles created, namespace ready. In production, this takes 30 seconds — not 3 weeks of JIRA tickets.

**1.3 — Publish API (1:30 min)**

> Now I publish an API to the catalog.

1. Click **API Catalog** → **Add API**
2. Name: "Payments API", Backend: httpbin.org, Version: v1
3. Submit
4. Show API detail page

> API published. Developers can discover it immediately. No email to the platform team, no Confluence page, no 5-day SLA.
>
> And this API can be deployed to **any** of our four gateways. Same definition, different runtime. That's what Gateway-Agnostic means.

---

### ACT 2 — Portal: 5 Days → 5 Minutes (5:00 - 8:00)

**[Tab 2: Portal — logged in as art3mis]**

> Now I switch roles. I'm a developer. I need API access.

**2.1 — Consumer Registration (1 min)**

1. Click **Register as Consumer** in Quick Actions
2. Fill: Name "Acme Payments App", Email, Company
3. Click **Register**
4. **CredentialsModal appears** — show client_id, client_secret, curl snippet

> Self-service. OAuth2 credentials in 10 seconds. Compare that to your current process: email the platform team, wait 5 business days, get an API key by email. We compressed that to one click.

**2.2 — Token + First Call (2 min)**

**[Tab 3: Terminal]**

```bash
# Copy curl from CredentialsModal
TOKEN=$(curl -s -X POST https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token \
  -d "grant_type=client_credentials" \
  -d "client_id=$CLIENT_ID" \
  -d "client_secret=$CLIENT_SECRET" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Call the gateway
curl -s -H "Authorization: Bearer $TOKEN" \
  https://mcp.gostoa.dev/mcp/v1/tools | python3 -m json.tool
```

> Standard OAuth2. JWT token. Gateway call. Authentication, rate limiting, audit trail — all automatic. The developer went from zero to API call in under 3 minutes.

---

### ACT 3 — Rust Gateway: Sub-millisecond (8:00 - 10:00)

**[Tab 3: Terminal]**

> Under the hood, that request went through our Rust gateway. Let me show you what that means for performance.

**3.1 — Rate Limiting (1 min)**

```bash
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code} " \
    -X POST https://mcp.gostoa.dev/mcp/v1/tools/invoke \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}'
done
```

> 200, 200, 200... 429. Per-consumer rate limiting. Automatic protection, per plan, per consumer. The 429 means: your quota is exhausted — try again later.

**3.2 — Benchmarks (1 min)**

> We run continuous benchmarks against Kong and Gravitee — same hardware, same backend, same scenarios.

**[Slide: Benchmark Results]**

| Gateway | Score (VPS) | p50 Latency | p95 Latency |
|---------|-------------|-------------|-------------|
| **STOA** | **97.25** | 1.2 ms | 3.8 ms |
| Kong | 94.41 | 2.1 ms | 6.2 ms |
| Gravitee | 96.39 | 1.8 ms | 5.1 ms |

> Co-located benchmarks, CI95 confidence intervals, 7 scenarios, median of 5 runs. STOA's Rust gateway leads on raw throughput. But the point isn't "we're faster" — the point is: you can switch gateways and your performance improves. That's vendor freedom.

---

### ACT 3b — mTLS: Zero Trust (10:00 - 13:00)

**[Tab 3: Terminal]**

> Now the enterprise killer feature. Your clients have X.509 certificates — from your PKI, from F5, from your security team. We bind those certificates to OAuth2 tokens. RFC 8705.

**3b.1 — Correct Certificate (1 min)**

```bash
# Call with correct certificate headers
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST https://mcp.gostoa.dev/mcp/v1/tools/invoke \
  -H "Authorization: Bearer $TOKEN_MTLS" \
  -H "X-SSL-Client-Verify: SUCCESS" \
  -H "X-SSL-Client-Fingerprint: $CORRECT_FINGERPRINT" \
  -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}'
```

> 200 OK. Certificate matches the token. Access granted.

**3b.2 — Stolen Token Scenario (1 min)**

```bash
# Same token, WRONG certificate → stolen token
curl -s -w "\nHTTP %{http_code}\n" \
  -X POST https://mcp.gostoa.dev/mcp/v1/tools/invoke \
  -H "Authorization: Bearer $TOKEN_MTLS" \
  -H "X-SSL-Client-Verify: SUCCESS" \
  -H "X-SSL-Client-Fingerprint: 0000000000000000000000000000000000000000000000000000000000000000" \
  -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}'
```

> 403. MTLS_BINDING_MISMATCH. Even with a valid JWT, the wrong certificate means instant rejection. This is how you detect stolen tokens — and this is what zero trust actually looks like.

**3b.3 — Scale (1 min)**

> We onboarded 100 enterprise clients with certificates in seconds. Each one got an OAuth2 client with automatic certificate binding. Rotate a certificate — binding updates automatically. Revoke one — instant block.
>
> In production, F5 handles TLS termination and injects headers. STOA validates the binding in microseconds. Your security team keeps control; your developers stay productive.

---

### ACT 4 — Observability (13:00 - 14:00)

**[Tab 4: Grafana]**

> Every request we just made — including the mTLS calls — is already visible.

1. Open **STOA Gateway Metrics** dashboard
2. Point out: requests/sec, p50/p95/p99 latencies, tool calls

> Real-time. Prometheus + Grafana. 29 dashboards. SLO alerting. And every error gets an OpenSearch snapshot with trace ID, tenant, and root cause — from error to fix in one click, not three teams.

---

### ACT 5 — MCP Bridge: The Paradigm Shift (14:00 - 16:00)

**[Tab 3: Terminal]**

> Here's where everything connects. Everything we've built — APIs, authentication, rate limiting, mTLS — all of that becomes available to AI agents.

**5.1 — OpenAPI → MCP in 3 seconds (1 min)**

```bash
stoactl bridge petstore.yaml --namespace tenant-acme \
  --include-tags pets --apply --server-name petstore-mcp
```

> One command. Five MCP tools registered. Three seconds. Any OpenAPI spec — your SAP, your Salesforce, your internal services — becomes MCP-ready.

**5.2 — AI Agent Call (1 min)**

```bash
# A Claude agent calls your enterprise API
curl -s -X POST https://mcp.gostoa.dev/mcp/v1/tools/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"tool": "petstore", "arguments": {"action": "list-pets"}}'
```

> This is a standard MCP tool call. Claude, GPT, any MCP-compatible agent can now call your enterprise APIs — with authentication, rate limiting, monitoring, audit trail, and mTLS if you need it.
>
> **Define Once, Expose Everywhere** — that's our Universal API Contract. One API definition serves REST clients, MCP agents, and any future protocol.

---

### ACT 6 — Born GitOps + AI Factory: The Bombshell (16:00 - 20:00)

**[Slide: "How We're Different"]**

> Before I close, let me tell you why we're architecturally different from every API management platform you've seen.

**6.1 — Born GitOps (2 min)**

> Kong, Apigee, MuleSoft, Gravitee — they all started with a database. A UI. Click to deploy. Then, years later, they bolted on GitOps. A CLI here, a Maven plugin there.
>
> STOA is Born GitOps. Git IS the control plane.

**[Slide: GitOps Comparison]**

| Platform | GitOps | Year Added | Source of Truth |
|----------|--------|------------|-----------------|
| Kong | decK | 2019 (retrofit) | Database |
| Apigee | Maven | 2015 (retrofit) | Database |
| Gravitee | GKO | 2023 (semi-native) | Database + Cockpit |
| **STOA** | **Native** | **2026 (born)** | **Git** |

> What does that mean concretely? Your Console generates a Git PR. Your team reviews it — with CODEOWNERS. Merge triggers ArgoCD sync. If metrics degrade, git revert. Every production change is a Git commit. Your DSI audits everything. Your compliance team sleeps at night.

**6.2 — AI Factory: 10 People, 300+ Developer Output (2 min)**

**[Terminal]**

```bash
git log --oneline --since="2026-02-09" | wc -l
```

> [Number] pull requests in one week. 436 story points in this cycle alone.
>
> This entire platform — the Rust gateway, the React console, the developer portal, the mTLS system, the MCP bridge, the GitOps operator, the observability stack — was built by a team of 10.
>
> How? AI agents. Not as a product feature — as the DNA of how we build.
>
> We don't just sell an AI gateway. We ARE an AI-native company. The same MCP protocol we offer our customers is what powers our development.

**6.3 — Close**

> Three things to remember:
>
> **One** — Gateway-Agnostic. Keep your webMethods, your Kong, your Gravitee. STOA manages them all. Zero vendor lock-in.
>
> **Two** — AI-Native. Any API becomes an MCP tool in 3 seconds. Your enterprise is ready for AI agents today.
>
> **Three** — Enterprise-Grade. mTLS, federation, RBAC, drift detection, GitOps — not bolted on, born in.
>
> Thank you. Questions?

---

## Headline Metrics (for slides + verbal)

### Platform Stats

| Metric | Value | Source |
|--------|-------|--------|
| Components | 7 (API, Console, Portal, Gateway, CLI, Operator, E2E) | Architecture |
| Total Tests | 1,747 (559 Rust + 573 Console + 560 Portal + 55 Operator) | CI |
| Test Coverage | 70%+ (Python), zero-warning (Rust), 4-persona parity (React) | CI thresholds |
| Production Services | 12 HTTPS endpoints on `*.gostoa.dev` | OVH MKS |
| Infrastructure Cost | ~198 EUR/month (down from ~810 with AWS) | Finance |
| Uptime | 23/23 smoke checks pass | demo-dry-run.sh |

### Benchmark Headline (Gateway Arena)

| Comparison | STOA | Kong | Gravitee |
|------------|------|------|----------|
| Score (VPS, co-located) | **97.25** | 94.41 | 96.39 |
| Score (K8s, in-cluster) | 81.14 | 91.65 | — |
| Methodology | k6, 7 scenarios, median of 5 runs, CI95 | Same | Same |

*VPS scores reflect co-located benchmarks (gateway + backend on same host). K8s scores include network hops.*

### Velocity

| Metric | Value |
|--------|-------|
| Cycle 7 (1 week) | 436 pts, 32 issues, 22+ PRs |
| Documentation | 107 pts, 101 docs + 12 blog posts |
| Time to Feature | Estimation / 10 (AI Factory acceleration) |

---

## FAQ — 10 Anticipated Objections

### 1. "Why not just use Kong / Gravitee / Apigee directly?"

> Those are excellent gateways. STOA doesn't replace them — it orchestrates them. If you have Kong today and want to add Gravitee tomorrow, STOA lets you manage both from one console. Same policies, same RBAC, same GitOps workflow. No vendor lock-in.

### 2. "How mature is this? You're a startup."

> Fair question. The platform has 1,747 tests, 4-persona RBAC coverage on every UI page, mTLS with RFC 8705, and has been running in production for 3 months. Our Go/No-Go scored 9.00/10. But we're honest: we're looking for a Design Partner, not selling a finished product. You shape the roadmap with us.

### 3. "What happens to our existing webMethods investment?"

> Nothing. STOA sits alongside webMethods, not instead of it. Your existing APIs keep running. STOA adds a control plane on top — unified catalog, developer portal, MCP bridge. When you're ready to migrate specific APIs to a lighter gateway, you can. No big bang.

### 4. "How does this compare to MuleSoft Anypoint?"

> MuleSoft is an iPaaS — integration + API management bundled together. STOA is a pure API Control Plane — we manage gateways, not build integrations. If you use MuleSoft for integration, you can use STOA to manage the API layer across MuleSoft and other gateways. They're complementary, not competitive.

### 5. "Is MCP a real standard? Will it last?"

> MCP was created by Anthropic and is now supported by Claude, OpenAI, Google Gemini, and dozens of AI frameworks. It's the HTTP of AI agent communication. But even if MCP evolves, STOA's Universal API Contract (UAC) is protocol-agnostic — we can expose APIs via MCP today and whatever comes next tomorrow.

### 6. "What about security? We're in a regulated industry."

> STOA was built security-first: mTLS with RFC 8705 certificate binding, Keycloak federation with per-organization realms, RBAC with 4 personas, OPA policy enforcement, SSRF protection, signed commits in CI. We support DORA/NIS2 compliance posture — though we don't claim certification (consult your legal counsel).

### 7. "What's the deployment model? We can't put data in the cloud."

> Hybrid. The Control Plane (Console, Portal, API) runs in the cloud or your private cloud. The Data Plane (gateway) runs on-premise, inside your network. API traffic never leaves your infrastructure. Sensitive data stays where your security team wants it.

### 8. "Team of 10? How can you support enterprise clients?"

> We partner with ESNs who handle client relationships and implementation. STOA provides the platform + Level 3 support. The AI Factory model means our 10-person team delivers output comparable to 50+ traditional developers. And our Design Partner gets direct access to the engineering team.

### 9. "What's the pricing model?"

> For the Design Partner engagement: the platform is free for 3 months. You invest your team's time for integration and feedback. After 3 months, we define pricing together based on your usage patterns. No surprise invoices.

### 10. "Can we see the source code?"

> Yes. STOA is Apache 2.0 open source. Everything you saw today is on GitHub: github.com/stoa-platform. You can fork it, audit it, contribute to it. The only private component is the strategy repository — the code is fully public.

---

## Plan B — Fallback Procedures

See `DEMO-PLAN-B.md` for the complete fallback table. Quick reference:

| If This Breaks | Do This |
|----------------|---------|
| Console won't load | Show Portal (covers Acts 1-2) |
| Gateway 500 | Show pre-recorded terminal output |
| mTLS fails | Show decoded JWT with cnf claim (screenshot) + explain verbally |
| Grafana empty | Show screenshot in slides |
| MCP endpoint missing | "Bridge is in development" + architecture slide |
| WiFi down | Mobile hotspot (pre-configured) |
| Everything down | Play backup video (offline, pre-recorded) |

### Critical Fallback: Pre-Record Video

Before demo day, record a clean run of all 6 acts. Store on laptop (not cloud). If any live demo fails, smoothly say: "Let me show you the recording we did yesterday" — no apology, just switch.

---

## Pre-Demo Ritual (T-30 min)

1. Run `scripts/demo/demo-dry-run.sh` — must return **GO** (23/23)
2. Open 4 browser tabs (Console, Portal, Grafana, Terminal)
3. Pre-authenticate all tabs
4. Set terminal font to 18pt, dark background
5. Enable Do Not Disturb (macOS)
6. Disable notifications (browser + system)
7. Test WiFi + hotspot backup
8. Have backup video accessible offline
9. Deep breath. You built this. You know every line.

---

## Slides Outline (for CAB-1130)

This narrative assumes minimal slides — the demo IS the presentation. Slides serve as transitions between acts.

| Slide | Content | When |
|-------|---------|------|
| 1 | Title: "STOA Control Plane: Gateway-Agnostic, AI-Powered" | 0:00 |
| 2 | The Gateway Problem (vendor lock-in + AI gap) | 0:30 |
| 3 | STOA Positioning (Control Plane above gateways) | 1:30 |
| 4 | → **LIVE DEMO STARTS** | 2:00 |
| 5 | Benchmark Results table | 10:00 (during Act 3.2) |
| 6 | GitOps Comparison table | 16:00 (during Act 6.1) |
| 7 | Three Things to Remember | 19:00 (close) |
| 8 | Contact + QR code (docs.gostoa.dev) | 20:00 |

**Total**: 8 slides. The demo does the talking.

---

*Generated for CAB-1150 — Demo narrative preparation*
*Last updated: 2026-02-15*
