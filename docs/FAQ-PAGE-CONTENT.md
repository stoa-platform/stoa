# FAQ Page Content — For stoa-docs

> **Destination:** `/docs/faq.md` in stoa-docs repository
> **Format:** Docusaurus markdown with frontmatter
> **Purpose:** Comprehensive FAQ page addressing pre-identified common questions about STOA Platform

---

## Docusaurus Frontmatter

```yaml
---
id: faq
title: Frequently Asked Questions
sidebar_label: FAQ
description: Common questions about STOA Platform, API management, MCP gateway, deployment, and enterprise integration. Get quick answers to help you get started.
keywords:
  - STOA FAQ
  - API gateway questions
  - MCP gateway FAQ
  - enterprise API management
  - open source gateway FAQ
  - self-hosted API gateway
---
```

---

## FAQ Content

# Frequently Asked Questions

Get quick answers to common questions about STOA Platform, from getting started to enterprise deployment.

## Getting Started

### What is STOA Platform?

STOA is an open-source API management platform that bridges enterprise APIs to AI agents. It provides a universal control plane to manage multiple API gateways (Kong, Gravitee, webMethods, or STOA's own Rust gateway), with native MCP (Model Context Protocol) support for AI agent integration. You define your API once and expose it everywhere — REST, GraphQL, and MCP.

See [Architecture Overview](/docs/concepts/architecture) for details.

### How long does it take to get started?

**15-20 minutes** for local Docker Compose setup. The quick start includes 17 services and demo data seeding. For Kubernetes deployment with ArgoCD, expect 1-2 hours for initial setup.

Follow the [Quick Start Guide](/docs/guides/quickstart) to get running locally.

### Is STOA free to use?

Yes. STOA is fully open source under Apache 2.0 license. You can use it, modify it, and deploy it without licensing fees. Enterprise support packages are available separately. See [LICENSE](https://github.com/stoa-platform/stoa/blob/main/LICENSE).

### What are the system requirements?

**Docker Compose (development):**
- Docker Engine 20.10+ with Docker Compose V2
- 8 GB RAM minimum (16 GB recommended)
- 20 GB disk space

**Kubernetes (production):**
- Kubernetes 1.26+
- Helm 3.0+
- 4 CPU cores, 8 GB RAM per node (minimum)
- PostgreSQL 15+, Keycloak 23+

See [Deployment Guide](/docs/deployment/hybrid) for detailed requirements.

---

## Architecture & Components

### Why not just use Kong / Gravitee / Apigee directly?

STOA doesn't replace existing gateways — it **orchestrates** them. If you have Kong today and want to add Gravitee tomorrow, STOA lets you manage both from one console with unified policies, RBAC, and GitOps workflows. This eliminates vendor lock-in and provides a consistent management layer across heterogeneous gateway infrastructure.

STOA also adds capabilities not found in traditional gateways: MCP bridge for AI agents, developer self-service portal, and multi-tenant control plane.

See [ADR-002: Gateway Adapter Pattern](/docs/architecture/adr/adr-002-gateway-adapter-pattern) for architecture details.

### What gateways does STOA support?

**Currently supported:**
- STOA Gateway (Rust) — native gateway with sub-millisecond latency
- Kong (DB-less mode) — declarative configuration via Admin API
- Gravitee APIM v4 — REST API with V4 definitions
- webMethods API Gateway 10.15+ — full OIDC integration

**Roadmap:**
- Apigee
- AWS API Gateway
- Azure APIM

The adapter pattern makes it straightforward to add new gateways. See [Gateway Adapters](/docs/reference/adapters).

### What is the Universal API Contract (UAC)?

UAC is STOA's "define once, expose everywhere" approach. You define an API specification (OpenAPI 3.0) in the control plane, and STOA automatically:
1. Provisions the API on your chosen gateway (Kong, Gravitee, etc.)
2. Creates REST endpoints with rate limiting and authentication
3. Exposes the API as MCP tools for AI agents
4. Updates the developer portal catalog

This eliminates duplicate configuration and ensures consistency across all API exposure modes.

See [Universal API Contract](/docs/concepts/uac) for details.

### How does STOA compare to MuleSoft Anypoint?

MuleSoft is an **iPaaS** — integration platform + API management bundled together. STOA is a **pure API Control Plane** — we manage gateways, not build integrations.

| Feature | STOA | MuleSoft Anypoint |
|---------|------|-------------------|
| API Management | ✅ Core focus | ✅ Included |
| Integration / ETL | ❌ Not included | ✅ Core focus |
| Multi-gateway orchestration | ✅ Yes | ❌ No (MuleSoft-only) |
| Open source | ✅ Apache 2.0 | ❌ Proprietary |
| MCP / AI agent support | ✅ Native | ❌ Not available |
| Deployment model | Hybrid (control plane + data plane) | Cloud or on-premise |

If you use MuleSoft for integration, you can use STOA to manage the API layer across MuleSoft and other gateways. They're complementary, not competitive.

---

## MCP & AI Agents

### What is MCP and why does it matter?

MCP (Model Context Protocol) is a protocol created by Anthropic for AI agent communication. It's like HTTP for AI agents — a standardized way for AI models (Claude, OpenAI, Gemini) to discover and call tools.

**Why it matters:** Without MCP, connecting AI agents to enterprise APIs requires custom integration for each model and each API. MCP standardizes this, making your APIs instantly usable by any MCP-compatible agent.

STOA acts as an **MCP gateway** — it translates your existing REST APIs into MCP tools that AI agents can discover and call, with full authentication, rate limiting, and audit trail.

See [What is MCP Gateway?](/blog/what-is-mcp-gateway) and [MCP Protocol](/docs/guides/fiches/mcp-protocol).

### Is MCP a real standard? Will it last?

MCP was created by Anthropic (2024) and is now supported by Claude, OpenAI (via plugins), Google Gemini, LangChain, and dozens of AI frameworks. It's the leading protocol for AI agent-to-service communication.

But even if MCP evolves or is replaced, STOA's **Universal API Contract** is protocol-agnostic. We expose APIs via MCP today and can support whatever protocol emerges tomorrow without changing your API definitions.

Think of it like REST vs GraphQL — your APIs are the source of truth, the transport can adapt.

### Can AI agents call my APIs without MCP?

Yes, but it requires custom integration per model and per API. The agent needs to:
1. Discover your API (manual documentation reading)
2. Understand the schema (OpenAPI parsing)
3. Authenticate (model-specific credential handling)
4. Handle rate limiting (custom retry logic)

MCP standardizes all of this. STOA's MCP gateway does the translation, so your APIs work with **any MCP-compatible agent** without custom code.

---

## Deployment & Operations

### What happens to our existing webMethods / Kong / Gravitee investment?

**Nothing changes.** STOA sits alongside your existing gateways, not instead of them. Your APIs keep running as-is. STOA adds a control plane on top — unified catalog, developer portal, MCP bridge, and GitOps workflows.

When you're ready to migrate specific APIs to a lighter gateway (like STOA's Rust gateway), you can do so incrementally. No big-bang migration required.

See [webMethods Migration Guide](/docs/guides/migration/webmethods-migration-guide).

### What's the deployment model? We can't put data in the cloud.

**Hybrid deployment:**
- **Control Plane** (Console, Portal, API, Keycloak) — runs in your cloud or private cloud
- **Data Plane** (gateway instances) — runs on-premise, inside your network

**Key security properties:**
- API traffic **never leaves your infrastructure** — requests go directly to the data plane gateway
- The control plane only manages configuration (API specs, policies, subscriptions) — no payload data
- Sensitive data stays where your security team requires

See [Hybrid Deployment](/docs/deployment/hybrid) for architecture diagrams.

### How mature is STOA? You're a startup.

STOA has been in production use since November 2025 (3 months as of February 2026). Current maturity indicators:
- **1,800+ tests** across all components (Python, TypeScript, Rust, E2E)
- **4-persona RBAC** coverage on every UI page
- **mTLS with RFC 8705** certificate-bound tokens
- **9-job security pipeline** (Gitleaks, Bandit, Trivy, Clippy SAST, license scan)
- **12 Grafana dashboards** for observability
- **ArgoCD-driven GitOps** for deployment

We're looking for **Design Partners** — customers who shape the roadmap with us — not selling a finished product. Our Go/No-Go readiness scored 9.00/10 for enterprise deployment.

See [Roadmap](/docs/roadmap) for upcoming features.

---

## Security & Compliance

### What about security? We're in a regulated industry.

STOA was built **security-first** with enterprise requirements in mind:

**Authentication:**
- Keycloak integration with OIDC/SAML/LDAP/AD federation
- mTLS with RFC 8705 certificate-bound tokens
- JWT validation with JWKS caching

**Authorization:**
- RBAC with 4 personas (cpi-admin, tenant-admin, devops, viewer)
- OPA (Open Policy Agent) policy enforcement
- Per-tenant resource isolation

**Network Security:**
- SSRF protection (blocks internal network calls)
- TLS 1.3 enforcement
- Ingress-level rate limiting

**Audit & Compliance:**
- Centralized audit trail (all API calls logged)
- OpenSearch integration for error tracking
- Signed commits in CI/CD

**DORA/NIS2 Compliance:**
STOA provides technical capabilities that **support** regulatory compliance efforts. We do not claim certification — consult qualified legal counsel for compliance verification.

See [Security & Compliance](/docs/enterprise/security-compliance) and [ADR-005: mTLS](/docs/architecture/adr/adr-005-mtls).

### Can we audit the source code?

Yes. STOA is **100% open source** under Apache 2.0 license. Everything you see in the product is on GitHub: [github.com/stoa-platform/stoa](https://github.com/stoa-platform/stoa).

You can:
- Fork the repository
- Audit the code
- Run security scans
- Contribute improvements
- Deploy from source

The only private component is our business strategy repository — the platform code is fully transparent.

### How do you handle secrets and credentials?

STOA uses a **centralized secrets manager** approach:
- **Infisical** (self-hosted) as the source of truth for all secrets
- Secrets injected at runtime via Kubernetes secrets or environment variables
- **Never hardcoded** in code, Docker images, or Git
- Secrets rotation supported via scripts (human-triggered)

**Agent prohibition:** AI agents can read secret paths but never change passwords or credentials autonomously — all rotation is human-triggered.

See [Secrets Management](/docs/reference/secrets-management).

---

## Enterprise & Support

### Team of 10? How can you support enterprise clients?

STOA uses an **AI Factory** development model — our 10-person team delivers output comparable to 50+ traditional developers through:
- Multi-agent AI workflows for implementation
- Automated testing and security scanning
- GitOps-driven deployment
- Council validation gates for quality

**For enterprise support:**
- Design Partners get **direct access** to the engineering team
- We partner with ESNs (Engineering Service Networks) for client relationship management and implementation
- STOA provides the platform + Level 3 support

### What's the pricing model?

**Open Source:** Free forever under Apache 2.0.

**Enterprise Support Packages:** Contact us for:
- SLA-backed support
- Custom feature development
- Migration assistance
- Training and onboarding

**Design Partner Program:** Platform free for 3 months in exchange for feedback and co-development. Pricing defined collaboratively after 3 months based on usage patterns.

### Can I contribute to STOA?

Absolutely! We welcome contributions. See [CONTRIBUTING.md](https://github.com/stoa-platform/stoa/blob/main/CONTRIBUTING.md) for guidelines.

**How to contribute:**
- Report bugs via [GitHub Issues](https://github.com/stoa-platform/stoa/issues)
- Propose features via [GitHub Discussions](https://github.com/stoa-platform/stoa/discussions)
- Submit PRs (all PRs require DCO sign-off)
- Join our [Discord](https://discord.gg/j8tHSSes)

**Commit standards:**
- Conventional commits: `type(scope): description`
- Squash merge to main
- < 300 LOC per PR (micro-PR strategy)

---

## Migration & Integration

### We use webMethods. How hard is migration?

**Phase 1 (No disruption):** STOA sits alongside webMethods. Existing APIs keep running.

**Phase 2 (Selective migration):** Move specific APIs to STOA's Rust gateway incrementally:
1. Export API definition from webMethods
2. Import OpenAPI spec to STOA
3. Configure routing and policies
4. Test in shadow mode
5. Cut over traffic

**Timeline:** 1-2 weeks per API (average). Shadow validation allows zero-downtime migration.

See [webMethods Migration Guide](/docs/guides/migration/webmethods-migration-guide) for step-by-step instructions.

### Can STOA integrate with our existing identity provider (AD, Okta, Azure AD)?

Yes. STOA uses **Keycloak** for identity federation, which supports:
- Active Directory / LDAP
- SAML (Okta, Azure AD, Ping Identity)
- OIDC (Auth0, Google, GitHub)
- Social login (Google, Microsoft, GitHub)

Configuration is done via Keycloak's Admin Console. Each tenant can have its own realm with dedicated identity provider configuration.

See [Authentication Guide](/docs/guides/authentication).

### How does STOA handle multi-tenancy?

**Tenant isolation:**
- Each organization (tenant) has its own Keycloak realm
- APIs, subscriptions, and consumers are scoped to tenants
- RBAC enforces per-tenant access control
- No data leakage between tenants

**Shared infrastructure:**
- Gateway instances are shared (cost-efficient)
- Control plane API multi-tenant aware
- Observability dashboards filterable by tenant

See [Multi-Tenant Architecture](/docs/concepts/multi-tenant) and [ADR-008: Multi-Tenancy](/docs/architecture/adr/adr-008-multi-tenancy).

---

## Troubleshooting

### The Console UI won't load. What do I check?

**Quick diagnostics:**

```bash
# 1. Check control-plane-api health
curl http://localhost/api/health

# 2. Check nginx is routing
docker logs stoa-nginx

# 3. Check browser console for errors
# (F12 → Console tab)

# 4. Verify Keycloak is running
curl http://localhost/auth/health
```

**Common causes:**
- Control plane API not started: `docker compose up -d control-plane-api`
- Keycloak not reachable: check KEYCLOAK_URL in control-plane-ui env
- CORS errors: verify nginx config has correct allowed origins

See [Troubleshooting Guide](/docs/reference/troubleshooting).

### MCP tools not appearing in Claude. Why?

**Checklist:**

1. **OAuth discovery reachable:**
   ```bash
   curl http://localhost/gateway/.well-known/oauth-protected-resource
   ```

2. **Gateway admin API accessible:**
   ```bash
   curl -H "Authorization: Bearer YOUR_TOKEN" http://localhost/gateway/admin/health
   ```

3. **Tools synced:**
   ```bash
   curl http://localhost/gateway/mcp/v1/tools
   ```

4. **Claude.ai MCP server configured:**
   - Check Claude settings → Integrations → MCP
   - Verify server URL is correct

See [MCP Troubleshooting](/docs/guides/fiches/mcp-protocol#troubleshooting).

### Tests are failing in CI. How do I debug?

**Local reproduction:**

```bash
# Python (control-plane-api)
cd control-plane-api && pytest tests/ -v --tb=short

# TypeScript (console/portal)
cd control-plane-ui && npm run test -- --run

# Rust (gateway)
cd stoa-gateway && cargo test --all-features

# E2E (Playwright)
cd e2e && npx playwright test
```

**CI-specific issues:**
- Check `.github/workflows/` for exact CI commands
- Verify environment variables are set in GitHub Secrets
- Check if path filters are excluding your changes

See [CI Quality Gates](/docs/reference/ci-quality-gates).

---

## Community & Learning

### Where can I get help?

**Official channels:**
- [GitHub Discussions](https://github.com/stoa-platform/stoa/discussions) — questions, ideas, show & tell
- [Discord](https://discord.gg/j8tHSSes) — real-time chat with the team
- [Documentation](https://docs.gostoa.dev) — guides, ADRs, API reference
- [Status Page](https://status.gostoa.dev) — platform uptime monitoring

### Are there any tutorials or examples?

Yes! Check out:
- [Quick Start](/docs/guides/quickstart) — 15-minute local setup
- [Migration Guides](/docs/guides/migration/) — webMethods, Kong, Apigee, Oracle OAM
- [Blog](/blog) — in-depth tutorials and case studies
- [GitHub Repository](https://github.com/stoa-platform/stoa) — full source code with examples

**Coming soon:**
- Video tutorials on YouTube
- stoa-examples repository with reference implementations

### How do I stay updated on new features?

**Release channels:**
- [GitHub Releases](https://github.com/stoa-platform/stoa/releases) — changelog for each version
- [Blog](/blog) — monthly release notes
- [Discord Announcements](https://discord.gg/j8tHSSes) — real-time updates
- [Twitter/X](https://x.com/gostoa) — product updates

**Roadmap:**
- Public roadmap at [/docs/roadmap](/docs/roadmap)
- GitHub Discussions for feature requests
- Quarterly AMA sessions with the team

---

## Legal & Licensing

### What license is STOA under?

**Apache License 2.0** — permissive open source license.

**You can:**
- Use commercially (no restrictions)
- Modify and distribute
- Sublicense
- Grant patents

**You must:**
- Include license and copyright notice
- State significant changes
- Preserve original NOTICE file

See [LICENSE](https://github.com/stoa-platform/stoa/blob/main/LICENSE).

### Are there any trademarks or brand restrictions?

"STOA Platform" is a trademark of CAB Ingenierie. You can:
- Use the name to reference the project
- Use the logo in documentation (with attribution)

You cannot:
- Imply endorsement without permission
- Use the name for commercial products without licensing

See [Trademarks](/legal/trademarks).

### Can I offer commercial support for STOA?

Yes. The Apache 2.0 license allows you to offer commercial services (hosting, support, custom development) based on STOA. We encourage the ecosystem.

**We ask that you:**
- Clearly distinguish your offering from official STOA support
- Contribute improvements back to the open source project (encouraged, not required)
- Follow trademark guidelines

---

## Still have questions?

**Didn't find your answer?** Ask the community:
- [GitHub Discussions](https://github.com/stoa-platform/stoa/discussions) — searchable Q&A
- [Discord](https://discord.gg/j8tHSSes) — live help from the team

**Found an error in this FAQ?** [Edit this page on GitHub](https://github.com/stoa-platform/stoa-docs/edit/main/docs/faq.md) or [open an issue](https://github.com/stoa-platform/stoa-docs/issues).

---

**Last updated:** 2026-02-20
