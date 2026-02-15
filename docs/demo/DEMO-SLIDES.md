---
marp: true
theme: default
paginate: true
backgroundColor: #0f172a
color: #e2e8f0
style: |
  section {
    font-family: 'Inter', 'Helvetica Neue', sans-serif;
  }
  h1 {
    color: #38bdf8;
    font-size: 2.2em;
  }
  h2 {
    color: #7dd3fc;
    font-size: 1.6em;
  }
  h3 {
    color: #94a3b8;
  }
  table {
    font-size: 0.85em;
  }
  th {
    background-color: #1e293b;
    color: #38bdf8;
  }
  td {
    background-color: #1e293b;
  }
  strong {
    color: #38bdf8;
  }
  a {
    color: #7dd3fc;
  }
  blockquote {
    border-left: 4px solid #38bdf8;
    color: #94a3b8;
    font-style: italic;
  }
  .accent {
    color: #f59e0b;
  }
  code {
    background-color: #1e293b;
    color: #38bdf8;
  }
  footer {
    color: #475569;
    font-size: 0.7em;
  }
---

<!-- _paginate: false -->
<!-- _footer: "" -->

# STOA Control Plane

## Gateway-Agnostic, AI-Powered

<br>

**Christophe Aboulicam** — Founder & CTO
February 2026

<br>

> Design Partner Presentation

---

<!-- _footer: "STOA Platform — Design Partner Presentation" -->

# The Gateway Problem

<br>

### Every enterprise has the same two problems:

<br>

**1. Vendor Lock-In**
You bought a gateway 5 years ago. Switching costs **18 months** and **2M EUR**.

<br>

**2. The AI Gap**
AI agents need your APIs — but your gateway was built for REST browsers, not MCP tool calls.

---

# STOA: One Console, Any Gateway

<br>

### Not another gateway — a **Control Plane** above your gateways.

<br>

| You keep... | STOA adds... |
|-------------|-------------|
| webMethods | Unified catalog |
| Kong | Developer portal |
| Gravitee | MCP bridge for AI agents |
| Your PKI / mTLS | GitOps audit trail |

<br>

> Same API definition. Same policies. Same RBAC. Any runtime.

---

<!-- _backgroundColor: #020617 -->

# LIVE DEMO

<br>
<br>

### Console → Portal → Gateway → mTLS → Observability → MCP Bridge

<br>

> 6 acts, 14 minutes

---

# Benchmark Results

### Gateway Arena — Co-Located (VPS, same hardware)

<br>

| Gateway | Score | p50 Latency | p95 Latency |
|---------|------:|------------:|------------:|
| **STOA (Rust)** | **97.25** | 1.2 ms | 3.8 ms |
| Gravitee | 96.39 | 1.8 ms | 5.1 ms |
| Kong | 94.41 | 2.1 ms | 6.2 ms |

<br>

**Methodology**: k6, 7 scenarios, median of 5 runs, CI95 confidence intervals
Same backend (nginx echo), same network, zero bias

---

# Born GitOps

### Git IS the Source of Truth

<br>

| Platform | GitOps | Year Added | Source of Truth |
|----------|--------|:----------:|-----------------|
| Kong | decK | 2019 (retrofit) | Database |
| Apigee | Maven | 2015 (retrofit) | Database |
| Gravitee | GKO | 2023 (semi-native) | Database + Cockpit |
| **STOA** | **Native** | **2026 (born)** | **Git** |

<br>

Console → Git PR → CODEOWNERS review → ArgoCD sync → Production
If metrics degrade → `git revert` → instant rollback

---

# Three Things to Remember

<br>
<br>

### 1. **Gateway-Agnostic**
Keep your webMethods, Kong, Gravitee. STOA manages them all.

<br>

### 2. **AI-Native**
Any API becomes an MCP tool in 3 seconds. AI-ready today.

<br>

### 3. **Enterprise-Grade**
mTLS, federation, RBAC, drift detection, GitOps — born in, not bolted on.

---

# The Platform — By the Numbers

<br>

| Metric | Value |
|--------|------:|
| Components | 7 (API, Console, Portal, Gateway, CLI, Operator, E2E) |
| Tests | 1,747 (Rust + React + Python + Operator) |
| Production services | 12 HTTPS endpoints |
| Infrastructure cost | ~198 EUR/month |
| Go/No-Go score | 9.00 / 10 |
| License | Apache 2.0 (100% open source) |

<br>

> **AI Factory**: 10 engineers → 436 story points / week

---

# Design Partner Program

<br>

### The Deal

<br>

**3 months free**. You bring a real use case.
We deploy STOA alongside your existing gateway.
Your team gives feedback. Together, we shape the roadmap.

<br>

After 3 months: usage-based pricing, defined together. No surprise invoices.

<br>

### Next Step

**2-hour technical workshop** with your architecture team.
Map your API landscape → identify first 3 APIs to onboard.

---

<!-- _paginate: false -->
<!-- _backgroundColor: #020617 -->

# Let's Talk

<br>
<br>

**docs.gostoa.dev** — Full documentation
**github.com/stoa-platform** — Source code (Apache 2.0)

<br>

Christophe Aboulicam
christophe@gostoa.dev

<br>
<br>

> _"Define Once, Expose Everywhere"_
