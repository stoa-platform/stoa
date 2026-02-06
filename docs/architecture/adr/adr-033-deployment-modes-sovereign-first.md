# ADR-033: Deployment Modes Strategy — Sovereign First

- **Status**: Accepted
- **Date**: 2026-02-06
- **Decision Makers**: Christophe ABOULICAM
- **Linear**: [CAB-1111](https://linear.app/hlfh-workspace/issue/CAB-1111/adr-deployment-modes-strategy-sovereign-first)

## Context

STOA Platform targets regulated European organizations (banks, insurance, defense) that operate under strict data sovereignty requirements (NIS2, DORA, RGPD, CLOUD Act restrictions).

### Competitive Landscape

All major API gateway vendors push customers toward cloud-hosted control planes:

| Vendor | Strategy | Constraint |
|--------|----------|------------|
| Kong | Kong Gateway (on-prem) + Konnect (SaaS) | Pushes toward Konnect with aggressive on-prem pricing |
| Apigee | Apigee Hybrid | Control plane stays at Google, runtime on-prem requires Anthos |
| MuleSoft | Anypoint Platform | Control plane cloud-only, Mule Runtime on-prem |
| Gravitee | APIM | On-prem available but SaaS-first positioning |

**None offer a true full-sovereign mode** where both Control Plane and Data Plane run entirely within the customer's infrastructure without any external dependency.

### Problem

The initial STOA one-pager describes a "Cloud Control Plane + Gateway On-Premise" architecture (Hybrid mode). However, our primary target customers — European central banks and regulated financial institutions — often cannot accept any cloud-hosted component from a third-party vendor due to:

1. **CLOUD Act**: US-headquartered cloud providers can be compelled to hand over data regardless of where it's stored
2. **BCE/ECB requirements**: Central banking infrastructure must be fully controllable
3. **NIS2 Directive**: Critical infrastructure must demonstrate supply chain sovereignty
4. **DORA**: Financial entities must ensure ICT third-party risk is fully managed

## Decision

STOA will support **three deployment modes**, shipped in phases:

### Deployment Modes

| Mode | Control Plane | Data Plane | Target | Phase |
|------|--------------|------------|--------|-------|
| **Sovereign** | Customer on-prem | Customer on-prem | Banks, defense, regulated EU | **Phase 1 (now)** |
| **Hybrid** | STOA Cloud | Customer on-prem | Standard enterprise | Phase 2 (post-v1.0) |
| **SaaS** | STOA Cloud | STOA Cloud | Startups, SMBs | Phase 3 |

### Why Sovereign First

1. **Market fit**: Target customers (ECB, central banks, insurance) cannot place the Control Plane with a third party
2. **Competitive moat**: Kong/Apigee do not offer true full on-prem without cloud dependencies
3. **Credibility**: Proving we work in the most constrained mode makes less constrained modes trivial
4. **EU trajectory**: NIS2, DORA, RGPD — regulation is moving toward more control, not less
5. **Reference customer**: First beta reference is a major EU central bank → Sovereign is the only acceptable mode

### Version Support Strategy

| Type | Support Window | Target |
|------|---------------|--------|
| Latest | 6 months | Early adopters, contributors |
| LTS | 2 years | Enterprise |
| Extended | 3 years (paid) | Regulated sectors |

### Certified Environments

| Platform | Minimum Version |
|----------|----------------|
| Kubernetes | 1.28+ |
| Helm | 3.12+ |
| OpenShift | 4.14+ |
| EKS / GKE / AKS | Current - 2 |

Bare metal without an orchestrator (Rancher, OpenShift minimum) is **not supported**.

### Telemetry by Mode

| Mode | Telemetry | Detail |
|------|-----------|--------|
| SaaS | Full (included) | Metrics, logs, traces — real-time |
| Hybrid | Anonymized (opt-out paid) | Version, uptime, feature usage, error count |
| Sovereign | Opt-in quarterly report | Anonymized PDF, no continuous data flow |

Sovereign mode will never require outbound network connectivity. The optional quarterly report is generated locally and transmitted manually by the customer.

### Pricing Guidance

| Mode | Relative Price | Typical Margin | Includes |
|------|---------------|----------------|----------|
| SaaS | $X/month | ~80% | Everything |
| Hybrid | $2X/month | ~60% | Cloud CP + support |
| Sovereign | $4X/month + mandatory support | ~40% | License + dedicated support |

The pricing structure naturally steers customers toward Hybrid/SaaS unless they have genuine sovereignty requirements (air-gapped, defense, healthcare, central banking).

## Consequences

### Positive

- **Unique positioning** in the EU API gateway market — no competitor offers true sovereign mode
- **Trust signal** for regulated industries — "we don't need to see your data"
- **Simplifies Phase 1 architecture** — no multi-tenant cloud infrastructure to build yet
- **Reference customer alignment** — first beta customer requires Sovereign mode
- **Credibility cascade** — if it works air-gapped, it works everywhere

### Negative

- **Version fragmentation risk** — mitigated by LTS + Extended support tiers with contractual upgrade obligations
- **Higher support costs per customer** — mitigated by mandatory support contracts in Sovereign pricing and certified environment matrix
- **No telemetry by default** — mitigated by health check endpoints + optional quarterly reports
- **Slower feedback loop** — mitigated by design partner program with direct communication channels
- **Delayed cloud revenue** — acceptable trade-off given that Phase 1 target customers would not buy a cloud-only product

### Impact on Existing Artifacts

| Artifact | Impact |
|----------|--------|
| One-pager Hybrid (current) | **Keep as-is** for demo Feb 24 — Hybrid is simpler to pitch in 5 min |
| Demo Feb 24 | Mention Sovereign orally as "One More Thing" for RSSI/architect audience |
| One-pager Sovereign | Create post-demo for central banking prospects |
| Architecture docs | Update to show all 3 modes with Sovereign as default |
| Helm charts | Must work fully offline (no external image pulls in Sovereign mode) |

## Alternatives Considered

### A. Hybrid First (rejected)

Start with Cloud Control Plane + On-Prem Data Plane. Rejected because:
- Primary target customers cannot accept cloud Control Plane
- Would delay first reference customer engagement
- Requires building cloud infrastructure before having revenue

### B. All Three Modes Simultaneously (rejected)

Ship all three modes from day one. Rejected because:
- Too much surface area for a solo founder
- Cloud infrastructure (multi-tenant, billing, SLA) is a separate product
- Sovereign is the superset — Hybrid and SaaS are subsets with managed infrastructure

### C. SaaS Only (rejected)

Follow the market toward cloud-only. Rejected because:
- Ignores the primary target market (regulated EU)
- No differentiation vs Kong Konnect / Apigee
- Contradicts EU sovereignty positioning

## References

- [Kong Gateway Pricing](https://konghq.com/products/kong-gateway)
- [Apigee Hybrid Architecture](https://cloud.google.com/apigee/docs/hybrid)
- [Gravitee APIM](https://www.gravitee.io)
- [NIS2 Directive](https://digital-strategy.ec.europa.eu/en/policies/nis2-directive)
- [DORA Regulation](https://www.eiopa.europa.eu/browse/regulation-and-policy/digital-operational-resilience-act-dora_en)
- STOA Internal Analysis (2026-02-06)
