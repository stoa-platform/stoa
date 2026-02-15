# Design Partner Pitch — 5 Minutes

> **Ticket**: CAB-1129
> **Format**: Word-for-word script with screen transitions
> **Audience**: Enterprise prospect (CTO/DSI/Archi) + ESN partner
> **Tone**: Confident but honest — "Design Partner", not "finished product"
> **Adaptable**: Client-agnostic — replace [CLIENT] placeholders for specific meetings

---

## Structure

```
OPENING   (0:00 - 0:30)   Problem statement
SOLUTION  (0:30 - 2:30)   STOA walkthrough (3 screens)
DEMO      (2:30 - 4:30)   Live portal + gateway call
CLOSE     (4:30 - 5:00)   Next steps
```

---

## OPENING — The Problem (0:00 - 0:30)

**[Screen: Slide 1 — "The Gateway Problem"]**

> You have APIs. You have a gateway — maybe webMethods, maybe Kong, maybe something custom. And now you have two problems.
>
> First: you're locked in. Switching costs 18 months. Second: AI agents need your APIs, and your gateway doesn't speak their language.
>
> We built STOA to solve both. Let me show you in 4 minutes.

**[TRANSITION: click to Console tab]**

---

## SOLUTION — STOA Walkthrough (0:30 - 2:30)

### Screen 1: Console Dashboard (0:30 - 1:15)

**[Screen: Console — console.gostoa.dev — logged in as halliday]**

> This is the STOA Console. One screen, four gateways.

*[Point at gateway status cards]*

> We manage STOA's own Rust gateway, Kong, Gravitee, and webMethods — all from here. Same API definition, same policies, same RBAC. You publish an API once, it deploys to any gateway you choose.

*[Point at tenant list]*

> Multi-tenant by design. Each organization gets isolated RBAC, its own Keycloak realm, separate quotas. Your security team controls who sees what.

*[Point at API catalog]*

> This is the API catalog. Every API has a lifecycle: draft, published, deprecated. Developers discover APIs here — no more Confluence pages or email threads.

**[TRANSITION: click to Portal tab]**

### Screen 2: Developer Portal (1:15 - 1:45)

**[Screen: Portal — portal.gostoa.dev — logged in as art3mis]**

> Now I'm a developer. I need API access.

*[Point at API list]*

> I see the published APIs. I click Subscribe, I get OAuth2 credentials — client ID, client secret, a ready-to-paste curl command. Self-service. No ticket, no 5-day SLA.

*[Point at Subscriptions page]*

> My active subscriptions, quotas, usage — all visible. The platform team doesn't need to handhold developers.

**[TRANSITION: click to Terminal tab]**

### Screen 3: Gateway Call (1:45 - 2:30)

**[Screen: Terminal]**

> One curl command.

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  https://mcp.gostoa.dev/mcp/v1/tools | python3 -m json.tool
```

*[Execute — show JSON response]*

> That went through our Rust gateway. Sub-millisecond overhead. Rate limiting, JWT validation, audit trail — all automatic.

> And here's the key: that same API is now available to AI agents via MCP. Any OpenAPI spec becomes an MCP tool — automatically. Your enterprise APIs are AI-ready today.

---

## DEMO — The Differentiators (2:30 - 4:30)

### mTLS — Zero Trust (2:30 - 3:15)

**[Screen: Terminal]**

> For regulated industries: mTLS certificate binding. RFC 8705.

```bash
# Correct certificate → 200 OK
curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer $TOKEN_MTLS" \
  -H "X-SSL-Client-Fingerprint: $CORRECT_FP" \
  https://mcp.gostoa.dev/mcp/v1/tools/invoke -d '...'
```

> 200. Now with a wrong certificate — simulating a stolen token:

```bash
# Wrong certificate → 403 BLOCKED
curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer $TOKEN_MTLS" \
  -H "X-SSL-Client-Fingerprint: 000...000" \
  https://mcp.gostoa.dev/mcp/v1/tools/invoke -d '...'
```

> 403. The token is valid, but the certificate doesn't match. Stolen token, instant block. That's zero trust.

### Observability (3:15 - 3:45)

**[Screen: Grafana — console.gostoa.dev/grafana]**

> Every request we just made is already here.

*[Show STOA Gateway Metrics dashboard — point at request rate, p50/p95 latencies]*

> Prometheus, Grafana, 29 dashboards. SLO alerting. Every error gets a trace ID with tenant context. From error to root cause in one click.

### Born GitOps (3:45 - 4:30)

**[Screen: Slide — "Born GitOps"]**

> Last differentiator. Kong, Apigee, Gravitee — they all started with a database and bolted on GitOps years later. STOA is Born GitOps. Git IS the source of truth.

> What does that mean for you? Every production change is a Git commit. Your team reviews with CODEOWNERS. Merge triggers ArgoCD sync. If metrics degrade, `git revert`. Full audit trail. Your DSI and compliance team get traceability for free.

> And the numbers: our Rust gateway scores 97.25 on co-located benchmarks — ahead of Kong at 94.41 and Gravitee at 96.39. Same hardware, same backend, same k6 scenarios, CI95 confidence intervals.

---

## CLOSE — Next Steps (4:30 - 5:00)

**[Screen: Slide — "Design Partner Program"]**

> We're not selling a finished product. We're looking for a Design Partner.

> Here's the deal:
>
> **3 months free**. You bring a real use case — an API migration, an AI agent integration, whatever hurts most. We deploy STOA alongside your existing gateway. Your team gives feedback. Together, we shape the roadmap.
>
> After 3 months, we define pricing based on your actual usage. No surprise invoices.

> The platform is Apache 2.0 open source. Everything I showed you is on GitHub. You can audit every line.

> **Next step**: a 2-hour technical workshop with your architecture team. We map your current API landscape and identify the first 3 APIs to onboard.

> Questions?

---

## Quick Objection Responses (if asked during/after)

| Objection | One-Liner Response |
|-----------|--------------------|
| "Too early / immature" | "1,747 tests, 3 months in production, Go/No-Go 9.00/10. But honest: Design Partner shapes the roadmap." |
| "Why not just use Kong?" | "You can. STOA manages Kong for you — plus Gravitee, webMethods, and our own gateway. One console, any runtime." |
| "What about our webMethods?" | "Keep it. STOA sits on top. Unified catalog, portal, MCP bridge. Migrate APIs when you're ready — no big bang." |
| "Is MCP real?" | "Anthropic, OpenAI, Google Gemini all support it. It's the HTTP of AI agents. But STOA's UAC is protocol-agnostic — future-proof." |
| "Security / regulated?" | "mTLS RFC 8705, Keycloak federation, 4-persona RBAC, SSRF protection, signed commits. Supports DORA/NIS2 posture." |
| "Team of 10?" | "AI Factory: 10 engineers, 436 story points/week. ESN partner handles implementation. You get direct access to the team." |
| "Pricing after 3 months?" | "Usage-based, defined together. No vendor lock-in — it's open source, you can self-host." |
| "Can we see the code?" | "Apache 2.0. github.com/stoa-platform. Fork it, audit it, contribute." |
| "Data residency?" | "Hybrid: Control Plane in your cloud, Data Plane on-prem. API traffic never leaves your infrastructure." |
| "How long to integrate?" | "First 3 APIs onboarded in 2 weeks. Full migration depends on scope — typically 4-8 weeks, not 18 months." |

---

## Adaptation Notes

### For [CLIENT] with webMethods
- Emphasize Act "mTLS" (their PKI likely uses X.509 via F5/Citrix)
- Mention webMethods adapter specifically: "we already integrate with your stack"
- Close with: "Start with 3 webMethods APIs, keep your investment, add MCP on top"

### For [CLIENT] with Kong/Gravitee
- Emphasize multi-gateway: "You already have Kong. Add STOA on top for unified governance"
- Focus on portal self-service (their devs probably email for API access today)
- Close with: "One portal for all your gateways, AI-ready from day one"

### For [CLIENT] greenfield (no gateway yet)
- Skip "gateway problem" angle, focus on "AI-native from day one"
- Emphasize MCP bridge more heavily (they care about AI agents, not migration)
- Close with: "Start with STOA Gateway, add others if you need them later"

---

## Screen Checklist (pre-pitch)

| # | Tab | URL | Pre-auth | Ready? |
|---|-----|-----|----------|--------|
| 1 | Slide deck | Local PDF/Keynote | N/A | [ ] |
| 2 | Console | console.gostoa.dev | halliday | [ ] |
| 3 | Portal | portal.gostoa.dev | art3mis | [ ] |
| 4 | Terminal | iTerm2 (18pt font) | TOKEN set | [ ] |
| 5 | Grafana | console.gostoa.dev/grafana | admin | [ ] |

**Total tabs**: 5. No tab switching chaos — linear flow left to right.

---

*Generated for CAB-1129 — Design Partner Pitch 5min*
*Complements: DEMO-NARRATIVE.md (20 min full), DEMO-SCRIPT.md (technical 8-act)*
*Last updated: 2026-02-15*
