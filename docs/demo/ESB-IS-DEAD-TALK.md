# "ESB is Dead, AI Agents Are Here" — Presentation Script

> **Date**: 24 February 2026 | **Duration**: 25 min (15 min talk + 10 min Q&A)
> **Presenter**: Christophe Aboulicam
> **Context**: Paired with the STOA live demo. This talk provides the strategic frame.
> **Ticket**: CAB-710

---

## Narrative Arc

```
PART 1 — The Autopsy (5 min)      → Why ESBs died
PART 2 — The Bridge (3 min)       → From ESB to API Gateway to AI Gateway
PART 3 — Live Proof (12 min)      → STOA demo (Acts 1-6 from DEMO-NARRATIVE.md)
PART 4 — n8n: The New ESB (3 min) → AI-powered workflow orchestration
PART 5 — Close (2 min)            → Three things to remember
```

Total: ~25 min. Adjust Part 3 (demo) to fit time constraints.

---

## PART 1 — The Autopsy: Why ESBs Died (0:00 - 5:00)

**[Slide: "ESB is Dead"]**

> Let me tell you about something that happened between 2005 and 2020.

> Every enterprise bought an ESB. MuleSoft. TIBCO. IBM Integration Bus. Software AG webMethods. The promise was beautiful: one bus to connect everything. Message routing, transformation, orchestration. SOA heaven.

**[Pause]**

> Here's what actually happened.

**1.1 — The Three Sins (2 min)**

> **Sin #1: Centralization.**
> The ESB became the single point of failure. Every message goes through one bus. The bus goes down, the company goes down. I've seen enterprises where a webMethods outage meant no invoices, no orders, no logistics.

> **Sin #2: Vendor lock-in.**
> You wrote your integrations in BPML, in BPEL, in proprietary DSLs that only ran on one vendor's runtime. Switching from TIBCO to MuleSoft? That's 18 months and 2 million euros. I know — I've lived it.

> **Sin #3: Accidental complexity.**
> The ESB was supposed to simplify. Instead, every team added "just one more mediation flow." Five years later, you have 400 flows, nobody knows which ones are active, and your ESB runs on a Java 8 VM that nobody dares restart.

**1.2 — What Killed the ESB (1 min)**

> Three things killed it:
> - **Microservices** said: "decentralize, smart endpoints, dumb pipes." The exact opposite of ESB.
> - **API Gateways** said: "expose your services as APIs, not SOAP messages."
> - **Kubernetes** said: "service mesh handles routing, load balancing, and mTLS at the infrastructure level."
>
> By 2020, every analyst report said the same thing: the ESB is a legacy pattern. Gartner moved it to the "retire" quadrant.

**1.3 — But the Problem Remains (2 min)**

> Here's the thing nobody talks about: the ESB solved a real problem. Enterprises need to orchestrate services. They need governance. They need auditability. They need someone to say "this consumer can call this service 100 times per minute, with these credentials, and we need a log of every call."
>
> API gateways solved part of it. But most API gateways are just ESBs with better marketing. Kong, Apigee, MuleSoft Anypoint — they centralize again. One vendor, one control plane, one bill.
>
> And now, in 2026, there's a new problem the ESB never imagined.

**[Pause — look at the audience]**

> AI agents need your APIs. Not through SOAP. Not through REST. Through a new protocol called MCP — Model Context Protocol. Claude, GPT, Gemini — they all need to call your enterprise services. And your API gateway has no idea what MCP is.

---

## PART 2 — The Bridge: ESB → API Gateway → AI Gateway (5:00 - 8:00)

**[Slide: Evolution Timeline]**

| Era | Pattern | What Routes | Source of Truth |
|-----|---------|-------------|-----------------|
| 2005-2015 | **ESB** | SOAP messages between services | WSDL + mediation flows |
| 2015-2024 | **API Gateway** | REST calls from consumers to APIs | OpenAPI + gateway config |
| 2025+ | **AI Gateway** | MCP tool calls from agents to APIs | Universal API Contract |

> The evolution is clear:
> - The ESB routed **messages** between **internal services**.
> - The API gateway routes **HTTP requests** from **external consumers** to **APIs**.
> - The AI gateway routes **tool calls** from **AI agents** to **any service**.

> Each generation absorbed the previous one. API gateways can do what ESBs did (routing, transformation, security). AI gateways can do what API gateways do — plus agent orchestration.

**2.1 — What an AI Gateway Actually Does (1 min)**

> An AI gateway is not an LLM proxy. Litellm, Portkey, LangChain — those are LLM routers. They route prompts to models.
>
> An AI gateway does something different: it takes your **enterprise APIs** and makes them available to **AI agents** as **tools**. With authentication. With rate limiting. With audit trail. With PII protection. With multi-tenant isolation.
>
> In other words: everything an ESB promised, but for the AI era.

**2.2 — STOA: The Control Plane (1 min)**

> This is what STOA does. STOA is not another gateway. It's a **control plane** that manages any gateway — including your existing one.
>
> You keep your Kong. You keep your webMethods. You keep your Gravitee. STOA sits above them all. One console, one catalog, one developer portal, one set of policies. And it adds what none of them have: an MCP bridge that turns any OpenAPI spec into AI-ready tools.
>
> Let me show you.

---

## PART 3 — Live Proof: STOA Demo (8:00 - 20:00)

**Run the main demo from DEMO-NARRATIVE.md (Acts 1-6).**

Refer to `DEMO-NARRATIVE.md` for the full script. Key moments to emphasize in the "ESB is Dead" context:

| Act | ESB Parallel | What to Say |
|-----|-------------|-------------|
| Act 1 (Console) | "In ESB world, this config took XML + deploy + restart" | "Three clicks, live in production" |
| Act 2 (Portal) | "ESB had no developer portal — you emailed WSDLs" | "Self-service. The developer never calls you" |
| Act 3 (Gateway + mTLS) | "ESB used WS-Security — XML signatures, nobody understood" | "mTLS with RFC 8705. Standards, not proprietary" |
| Act 4 (Observability) | "ESB logs? Good luck searching 10 GB of Java stack traces" | "Every call, every error, traced and searchable" |
| Act 5 (MCP Bridge) | "ESBs couldn't even do REST well, let alone MCP" | "Any API becomes an AI tool in 3 seconds" |
| Act 6 (GitOps) | "ESB changes went through a change board + manual deploy" | "Git PR → code review → ArgoCD sync → production" |

---

## PART 4 — n8n: The New ESB (20:00 - 23:00)

**[Slide: "n8n + STOA = ESB Replacement"]**

> Now let me address the elephant in the room. If the ESB is dead, who does the orchestration?
>
> The answer is: workflow engines. Specifically, open-source ones. n8n, Temporal, Apache Airflow.

**4.1 — n8n as the Modern Integration Layer (1 min)**

> n8n is the anti-ESB. It's open source. It runs in Docker. It orchestrates workflows visually — but under the hood, it's just HTTP calls. No proprietary runtime. No lock-in.
>
> At STOA, we use n8n for our own operations. Let me show you a real workflow.

**[Show architecture diagram or n8n screenshot if available]**

```
STOA AI Factory Workflow (live in production):

  Linear webhook (ticket moves to "In Progress")
    → n8n receives the event
    → n8n calls GitHub Actions (dispatch CI pipeline)
    → n8n sends Slack notification ("Pipeline started for CAB-XXX")
```

> This workflow runs every time we start work on a ticket. It's our internal dogfooding. The old way? Someone watches Linear, manually triggers Jenkins, copies the ticket ID into Slack. Three manual steps. Now? Zero. n8n does it.

**4.2 — n8n + STOA: AI-Powered Orchestration (1 min)**

> Here's where it gets interesting. n8n is great at orchestrating HTTP calls. But when you add STOA as the AI gateway, n8n workflows gain AI capabilities — with governance.

```
Use Case: AI Ticket Classification

  Customer ticket arrives (webhook)
    → n8n sends ticket text to STOA /mcp/v1/tools/invoke
    → STOA routes to Claude (Marketing tenant, 50K token/day quota)
    → STOA applies PII guardrails (masks email, phone before sending)
    → Claude classifies: "billing", "technical", "complaint"
    → n8n routes to the right Slack channel
    → If Claude is slow → STOA fallback chain switches to GPT-4
```

> This is the ESB replacement. But instead of BPML mediation flows on a Java 8 bus, it's n8n + STOA + AI. Open source. Standards-based. Auditable.

**4.3 — Why Not Just Call the LLM Directly? (1 min)**

> You could. n8n has an OpenAI node. You can call Claude directly.
>
> But then who enforces quotas per team? Who masks PII before it reaches the model? Who fails over to another provider when Claude has an outage? Who logs every call for DORA compliance?
>
> That's what STOA does. STOA is the governance layer between your workflows and your AI providers. Just like an API gateway sits between consumers and backends — but for AI.

| Direct LLM Call | Through STOA |
|----------------|-------------|
| No quota per team | Per-tenant rate limiting |
| PII sent to model | PII detected and redacted |
| Single provider | Fallback chain (Claude → GPT-4 → local) |
| No audit trail | Every call logged + traced |
| No mTLS | Certificate-bound tokens (RFC 8705) |

---

## PART 5 — Close: Three Things to Remember (23:00 - 25:00)

**[Slide: "Three Things"]**

> Let me leave you with three things.

> **1. The ESB is dead. But the problem it solved is not.**
> Enterprises still need orchestration, governance, and auditability. The new answer is API gateways + workflow engines + AI gateways. Not a monolithic bus.

> **2. Your existing gateway is not the enemy. Lock-in is.**
> You don't need to rip and replace Kong or webMethods. You need a control plane that abstracts them. That's what STOA does — one console, any gateway.

> **3. AI agents are not a feature. They're a new integration paradigm.**
> MCP is doing to AI what REST did to SOA. Every API will need to be AI-ready. The question is not "if" but "how fast." With STOA, the answer is 3 seconds.

**[Slide: "Let's Talk"]**

> If you want to see this running on your infrastructure, with your APIs, alongside your existing gateway — let's schedule a 2-hour technical workshop. We'll map your API landscape and identify the first three APIs to onboard.

> Thank you.

---

## Q&A Preparation — "ESB is Dead" Specific

These questions are specific to the "ESB is Dead" framing. See also `DEMO-NARRATIVE.md` for the general FAQ.

### "We still use webMethods. Are you saying we should rip it out?"

> Absolutely not. STOA has a webMethods adapter. We've tested it live — same API definition, deployed to webMethods and to our Rust gateway simultaneously. Keep webMethods for what it does well. Use STOA to add the developer portal, the MCP bridge, the unified catalog. When you're ready to migrate specific APIs, you can — one by one, not big bang.

### "n8n is not enterprise-ready. How can it replace TIBCO?"

> n8n handles orchestration — the "glue" between services. It doesn't need to handle 10,000 messages per second. For that, you have Kafka, Redpanda, your message broker. n8n is the workflow layer, not the transport layer. And it's Apache 2.0, self-hosted, no vendor lock-in. Compare that to TIBCO's licensing model.

### "What about MuleSoft Anypoint? They have AI features now."

> MuleSoft added AI capabilities recently — and that's great. But MuleSoft is a $40K+/year platform with a proprietary runtime. STOA is Apache 2.0, runs on any Kubernetes cluster, costs us 198 EUR/month to run in production. And our MCP bridge is native, not an add-on.
>
> *(Content compliance note: no specific MuleSoft pricing — use "significant licensing cost" if challenged on the number.)*

### "Is MCP actually a standard? Or is it just Anthropic's thing?"

> MCP is open source, published under the MIT license, with implementations from Anthropic, Microsoft, Google, and dozens of open-source projects. It's not a standard in the ISO sense — yet. But neither was REST in 2005. By the time it's an RFC, you'll want to be ready.

### "How does STOA compare to Portkey / LiteLLM / LangChain?"

> Those are LLM routers — they route prompts to models. STOA is an API-to-agent bridge — it makes your enterprise APIs available as MCP tools. They operate at different layers. You might use LiteLLM inside your AI agent to pick the best model, and STOA to give that agent access to your APIs. They're complementary.

### "What about event-driven architecture? ESBs were good at pub/sub."

> ESBs were indeed event brokers. But Kafka, Redpanda, and NATS do pub/sub far better — purpose-built, horizontally scalable, open source. STOA's gateway already integrates with Redpanda for event streaming. The ESB pattern of "one bus does everything" is what failed. Specialized tools for specialized jobs.

---

## Speaker Notes

### Pacing

| Section | Duration | Energy Level |
|---------|----------|-------------|
| Part 1 (Autopsy) | 5 min | High — storytelling, audience recognition |
| Part 2 (Bridge) | 3 min | Medium — educational, timeline visual |
| Part 3 (Demo) | 12 min | High — live demo, engagement peaks |
| Part 4 (n8n) | 3 min | Medium-high — concrete, production example |
| Part 5 (Close) | 2 min | High — memorable, call to action |

### Key Pivots

- If audience is **ESB-heavy** (webMethods, TIBCO users): spend more time on Part 1, emphasize "keep your existing gateway" message in Parts 2 and 5.
- If audience is **cloud-native** (Kubernetes, microservices): abbreviate Part 1, expand Part 4 (n8n workflows) and Act 5 (MCP bridge).
- If audience is **AI-focused** (AI teams, data scientists): abbreviate Parts 1-2, expand Act 5 and Part 4, emphasize guardrails and PII protection.

### Audience Calibration (first 30 seconds)

> Before starting, ask: "Quick show of hands — who here is currently running an ESB or iPaaS in production?"
>
> - **Many hands**: they'll relate to Part 1. Lean into the pain.
> - **Few hands**: they're cloud-native. Skip the ESB war stories, go straight to "the problem remains."

### Timing Buffer

If running short on time:
- **Cut first**: Part 1.3 ("But the Problem Remains") — fold into Part 2
- **Cut second**: Part 4.3 ("Why Not Just Call the LLM Directly?") — the table is self-explanatory
- **Never cut**: Part 5 (close with three pillars) — this is what they remember

---

*Generated for CAB-710 — "ESB is Dead" presentation script*
*Companion to: DEMO-NARRATIVE.md (Acts 1-6), DEMO-SLIDES.md (10 slides), DEMO-PITCH-5MIN.md*
*Last updated: 2026-02-15*
