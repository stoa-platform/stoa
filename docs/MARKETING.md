# STOA Platform v2 - Enterprise API Management Platform

> **Sovereign API management solution for regulated industries**

---

## The Challenge for Regulated Enterprises

French banks, insurance companies, and financial institutions face major challenges in their digital transformation:

| Challenge | Impact |
|-----------|--------|
| **Regulatory compliance** | GDPR, PSD2, Solvency II, ACPR/AMF requirements |
| **Data sovereignty** | Mandatory hosting on French/European territory |
| **Enhanced security** | Sensitive data protection, complete audit trail |
| **Time-to-Market** | Competitive pressure from FinTechs and InsurTechs |
| **Legacy Integration** | Connection with legacy systems (mainframes, COBOL) |
| **Multi-partner** | Open Banking ecosystem, aggregators, PSD2 |

---

## Our Solution: STOA Platform v2

### Vision

A **100% sovereign** API management platform, designed for banking and insurance sector requirements, deployable on:

- **Sovereign Cloud** (OVHcloud, Scaleway, Outscale, NumSpot)
- **Private Cloud** (VMware, OpenStack, Kubernetes on-premise)
- **Hybrid Cloud** (combination of both)

### Target Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        APIM PLATFORM v2                                      │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                      CONTROL PLANE (GitOps)                            │ │
│  │                                                                         │ │
│  │   Web Console ──► API Backend ──► GitLab (Source of Truth)             │ │
│  │        │              │                    │                            │ │
│  │        │              ▼                    ▼                            │ │
│  │        │         Keycloak            Kafka/Redpanda                     │ │
│  │        │          (SSO)               (Events)                          │ │
│  │        │              │                    │                            │ │
│  │        │              └────────┬───────────┘                            │ │
│  │        │                       │                                        │ │
│  │        │                       ▼                                        │ │
│  │        │              ┌─────────────────┐                               │ │
│  │        │              │     Jenkins     │                               │ │
│  │        │              │  (Orchestration)│                               │ │
│  │        │              └────────┬────────┘                               │ │
│  │        │                       │                                        │ │
│  │        │                       ▼                                        │ │
│  │        │              ┌─────────────────┐                               │ │
│  │        │              │      AWX        │                               │ │
│  │        │              │   (Automation)  │                               │ │
│  │        │              └────────┬────────┘                               │ │
│  │        │                       │                                        │ │
│  └────────┼───────────────────────┼────────────────────────────────────────┘ │
│           │                       │                                          │
│  ┌────────┼───────────────────────┼────────────────────────────────────────┐ │
│  │        │           DATA PLANE  │                                        │ │
│  │        │                       ▼                                        │ │
│  │        │              ┌─────────────────┐                               │ │
│  │        └─────────────►│   API Gateway   │◄──── Business APIs            │ │
│  │                       │  (Kong/wM/Apigee)│      (Backend Services)      │ │
│  │                       └─────────────────┘                               │ │
│  │                              │                                          │ │
│  │                              ▼                                          │ │
│  │                    ┌──────────────────┐                                 │ │
│  │                    │   Vault (Secrets) │                                │ │
│  │                    └──────────────────┘                                 │ │
│  │                                                                         │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                      OBSERVABILITY                                      │ │
│  │   OpenSearch (Logs) ◄──► Prometheus (Metrics) ◄──► Grafana (Dashboards) │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Value Proposition

### 1. Total Sovereignty

| Aspect | Guarantee |
|--------|-----------|
| **Hosting** | 100% France/EU, SecNumCloud certified sovereign cloud |
| **Source Code** | Open source, auditable, no vendor lock-in |
| **Data** | AES-256 encryption, customer-managed keys |
| **Compliance** | GDPR by design, immutable audit trail |

### 2. Enterprise Security

```
┌─────────────────────────────────────────────────────────────────┐
│                    SECURITY MODEL                                │
│                                                                  │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │
│   │   Keycloak   │    │    Vault     │    │  OPA/Gatekeeper│    │
│   │     (IAM)    │    │  (Secrets)   │    │   (Policies)  │     │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘      │
│          │                   │                   │               │
│          └───────────────────┼───────────────────┘               │
│                              │                                   │
│                              ▼                                   │
│                    ┌──────────────────┐                          │
│                    │  Zero Trust      │                          │
│                    │  Architecture    │                          │
│                    └──────────────────┘                          │
│                                                                  │
│   • OIDC/SAML Authentication                                    │
│   • Granular RBAC (4 levels)                                    │
│   • Automatic secrets rotation                                   │
│   • Complete audit trail (Kafka + OpenSearch)                   │
│   • Anti-self-approval for production                           │
│   • Kubernetes network policies                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Native Multi-Tenant

Designed from the ground up to manage multiple entities:

- **Banking**: Separation by subsidiaries, business lines, partners
- **Insurance**: Isolation by brands, distribution networks
- **Group**: Platform pooling, per-tenant billing

```
┌─────────────────────────────────────────────────────────────────┐
│                    MULTI-TENANCY                                 │
│                                                                  │
│   Tenant A (Retail Banking)      Tenant B (Private Banking)     │
│   ├── Account APIs               ├── Wealth Management APIs     │
│   ├── Payment APIs               ├── Reporting APIs             │
│   ├── Credit APIs                └── Compliance APIs            │
│   └── PSD2 APIs                                                  │
│                                                                  │
│   Tenant C (Auto Insurance)      Tenant D (Life Insurance)      │
│   ├── Subscription APIs          ├── Savings APIs               │
│   ├── Claims APIs                ├── Succession APIs            │
│   └── Partner APIs               └── Tax APIs                   │
│                                                                  │
│   ════════════════════════════════════════════════════════════  │
│   │              COMPLETE ISOLATION                          │  │
│   │  • Dedicated Kubernetes namespaces                       │  │
│   │  • Separate Vault secrets                                │  │
│   │  • Per-tenant quotas and rate limiting                   │  │
│   │  • Isolated billing and metrics                          │  │
│   ════════════════════════════════════════════════════════════  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. GitOps & Automation

**Infrastructure as Code** for complete traceability:

| Component | Technology | Benefit |
|-----------|------------|---------|
| Source of Truth | GitLab | Versioning, audit, rollback |
| Orchestration | Jenkins | Approval gates, pipeline as code |
| Automation | AWX/Ansible | Reproducible deployments |
| Sync | ArgoCD | Continuous reconciliation |

**Production deployment workflow**:

```
Developer ──► Pull Request ──► Review ──► Merge
                                              │
                                              ▼
                                         Jenkins Pipeline
                                              │
                                    ┌─────────┴─────────┐
                                    │   APPROVAL GATE   │
                                    │  (4-eyes principle)│
                                    └─────────┬─────────┘
                                              │
                                              ▼
                                    AWX Deployment ──► Production
                                              │
                                              ▼
                                    Notification + Audit
```

---

## Sector Use Cases

### Banking: Open Banking & PSD2

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPEN BANKING PLATFORM                         │
│                                                                  │
│   Aggregators (Bankin, Linxo)                                   │
│          │                                                       │
│          ▼                                                       │
│   ┌──────────────┐                                              │
│   │ API Gateway  │◄──── Rate Limiting (TPP quotas)              │
│   │   (PSD2)     │◄──── OAuth2 + QWAC/QSEAL                     │
│   └──────┬───────┘◄──── Consent Management                      │
│          │                                                       │
│          ▼                                                       │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐     │
│   │   AIS API    │    │   PIS API    │    │   CBPII API  │     │
│   │(Consultation)│    │  (Payment)   │    │  (Balance)   │     │
│   └──────────────┘    └──────────────┘    └──────────────┘     │
│                                                                  │
│   Compliance: PSD2, RTS SCA, EBA Guidelines                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits**:
- Native PSD2 compliance
- Integrated consent management
- Real-time TPP monitoring
- Automated regulator reporting

### Insurance: Partner Ecosystem

```
┌─────────────────────────────────────────────────────────────────┐
│                    PARTNER ECOSYSTEM                             │
│                                                                  │
│   Brokers      Comparison Sites    Bancassurance    Affiliates  │
│       │             │                   │               │        │
│       └─────────────┴───────────────────┴───────────────┘        │
│                              │                                   │
│                              ▼                                   │
│                    ┌──────────────────┐                         │
│                    │   API Gateway    │                         │
│                    │   (Partners)     │                         │
│                    └────────┬─────────┘                         │
│                             │                                    │
│       ┌─────────────────────┼─────────────────────┐             │
│       ▼                     ▼                     ▼             │
│   ┌────────┐          ┌────────┐          ┌────────┐           │
│   │ Quote  │          │ Subscr.│          │ Claims │           │
│   │  API   │          │  API   │          │  API   │           │
│   └────────┘          └────────┘          └────────┘           │
│                                                                  │
│   Features:                                                      │
│   • Self-service partner onboarding                             │
│   • API Keys with custom quotas                                 │
│   • Per-partner analytics dashboard                             │
│   • Usage-based billing                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits**:
- Reduced partner time-to-market (days vs months)
- Self-service for partners
- Complete usage visibility
- API monetization

---

## Deployment Options

### Sovereign Cloud (Recommended for Regulated Sector)

| Provider | Certification | Location |
|----------|---------------|----------|
| **OVHcloud** | SecNumCloud, HDS | France |
| **Scaleway** | ISO 27001 | France |
| **Outscale** | SecNumCloud | France |
| **NumSpot** | SecNumCloud | France |
| **S3NS** (Thales) | SecNumCloud | France |

### Private Cloud (On-Premise)

```
┌─────────────────────────────────────────────────────────────────┐
│                    ON-PREMISE DEPLOYMENT                         │
│                                                                  │
│   Customer Infrastructure                                        │
│   ├── Kubernetes (OpenShift, Rancher, vanilla K8s)              │
│   ├── VMware vSphere                                             │
│   └── Bare Metal                                                 │
│                                                                  │
│   Prerequisites:                                                 │
│   • Kubernetes 1.25+                                             │
│   • Persistent storage (Ceph, NetApp, Pure)                     │
│   • Load Balancer (F5, HAProxy, MetalLB)                        │
│   • Private registry (Harbor, Nexus)                            │
│                                                                  │
│   Deliverables:                                                  │
│   • Helm Charts                                                  │
│   • Ansible Playbooks                                            │
│   • Operational documentation                                    │
│   • Runbooks                                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Hybrid

Sovereign cloud + on-premise combination:
- **Control Plane**: Sovereign cloud (high availability)
- **Data Plane**: On-premise (sensitive data)
- **Disaster Recovery**: Cross-cloud

---

## Compliance & Certifications

| Regulation | Coverage |
|------------|----------|
| **GDPR** | Privacy by design, right to erasure, portability |
| **PSD2** | Regulatory APIs, SCA, TPP management |
| **Solvency II** | Audit trail, reporting |
| **LPM** | Sovereign hosting, OIV compatible |
| **DORA** | Operational resilience, continuity testing |
| **NIS2** | Cybersecurity, incident notification |

### Immutable Audit Trail

```
Every action ──► Kafka Event ──► OpenSearch ──► 7-year retention
                     │
                     ▼
              S3 (Legal archive)
```

---

## Competitive Comparison

| Criteria | STOA Platform v2 | US SaaS Solutions | Legacy Solutions |
|----------|------------------|-------------------|------------------|
| **Sovereignty** | ✅ 100% France/EU | ❌ USA (Cloud Act) | ⚠️ Variable |
| **Open Source** | ✅ Auditable | ❌ Proprietary | ❌ Proprietary |
| **Multi-Tenant** | ✅ Native | ⚠️ Limited | ❌ Silos |
| **GitOps** | ✅ Native | ❌ No | ❌ No |
| **Approval Gates** | ✅ Integrated | ⚠️ Add-on | ❌ Manual |
| **Cost** | 💰 Predictable | 💰💰💰 Usage-based | 💰💰 License |
| **Vendor Lock-in** | ✅ None | ❌ Strong | ❌ Strong |

---

## Business Model

### Licensing

| Tier | Target | Includes |
|------|--------|----------|
| **Community** | POC, Startup | Core features, community support |
| **Enterprise** | Mid-market | + 8x5 support, 99.5% SLA |
| **Premium** | Large Accounts | + 24x7 support, 99.9% SLA, consulting |

### Services

- **Implementation**: Turnkey deployment
- **Training**: Dev, Ops, Security teams
- **Consulting**: Architecture, migration, optimization
- **Support**: L2/L3, on-call, upgrades

---

## Roadmap

```
2025 Q1          2025 Q2          2025 Q3          2025 Q4
   │                │                │                │
   ▼                ▼                ▼                ▼
┌──────┐        ┌──────┐        ┌──────┐        ┌──────┐
│ MVP  │        │ Prod │        │Scale │        │Enter-│
│      │        │Ready │        │      │        │prise │
└──────┘        └──────┘        └──────┘        └──────┘
   │                │                │                │
   │                │                │                │
   ▼                ▼                ▼                ▼

• Core Platform   • Ticketing      • Portal        • Multi-region
• GitOps          • Jenkins        • Analytics     • Automated DR
• Monitoring      • Prod Hardening • Cost Mgmt     • Marketplace
• Multi-tenant    • SLO/SLA        • Self-service  • APIs
```

---

## Why Choose Us?

### Sector Expertise

- **15+ years** experience in Banking/Insurance IT
- **Business knowledge**: PSD2, Solvency, GDPR
- **References**: [To be completed]

### Pragmatic Approach

- **MVP in 8 weeks**
- **Production-ready in 16 weeks**
- **Agile methodology** with 2-week sprints
- **Transparency**: GitOps, everything is versioned and auditable

### Quality Commitment

- **Contractual SLA** up to 99.9%
- **French support** based in France
- **Continuous improvements** with shared roadmap

---

## Contact

**CAB Ingénierie**

- **Web**: [www.cab-i.com](https://www.cab-i.com)
- **Email**: contact@cab-i.com
- **LinkedIn**: CAB Ingénierie

---

*Confidential document - © 2025 CAB Ingénierie*
