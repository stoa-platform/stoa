# STOA Technology Choices — Architecture Decision Records

> **"Each tool to its purpose"** — No one-size-fits-all

This document explains the technology choices for the STOA stack and why each component was selected over alternatives.

---

## Overview

| Category | STOA Choice | Alternatives Considered | Reason |
|----------|-------------|-------------------------|--------|
| **Messaging** | Kafka (Redpanda) | RabbitMQ, UM, NATS | Event sourcing, replay, scale |
| **Database** | PostgreSQL | MySQL, MongoDB, CockroachDB | ACID, JSON, extensions |
| **Auth** | Keycloak | Auth0, Okta, Authelia | Self-hosted, full OIDC |
| **Observability** | Prometheus + Grafana + Loki | Datadog, ELK, Splunk | Open source, K8s-native |
| **GitOps K8s** | ArgoCD | Flux, Jenkins, Spinnaker | UI, multi-cluster, adoption |
| **Non-K8s Automation** | AWX (Ansible) | Terraform, scripts | Idempotent, auditable, UI |
| **Gateway v1** | webMethods | Kong, APISIX, Gravitee | Existing expertise, legacy |
| **Gateway v2** | Rust + eBPF | Go, C++ | Performance, safety, modern |
| **Search** | OpenSearch | Elasticsearch, Meilisearch | Free fork, AWS-free |

---

## Messaging: Kafka (Redpanda) vs RabbitMQ vs UM

| Criteria | Kafka/Redpanda | RabbitMQ | Universal Messaging (UM) |
|----------|----------------|----------|---------------------------|
| **Paradigm** | Event log (append-only) | Message queue (FIFO) | Message queue |
| **Replay** | ✅ Native (offset) | ❌ Messages deleted after ACK | ❌ Limited |
| **Throughput** | 1M+ msg/s | ~50K msg/s | Variable |
| **Ordering** | ✅ Per partition | ❌ Not guaranteed | ✅ Per queue |
| **Persistence** | ✅ Disk by default | Optional | Optional |
| **K8s-native** | ✅ (Strimzi, Redpanda) | ✅ (Operator) | ❌ Legacy |
| **License** | Apache 2.0 | MPL 2.0 | Proprietary SAG |
| **Event sourcing** | ✅ Designed for | ❌ Not suitable | ❌ Not suitable |

### Why Kafka/Redpanda?

1. **Event Sourcing** — Every action (subscription, rotation, invocation) is an immutable event
2. **Replay** — State can be reconstructed from events
3. **Auditability** — Permanent log for compliance
4. **Decoupling** — Independent producers and consumers
5. **Redpanda** — Kafka-compatible, no JVM, simpler to operate

### Why not RabbitMQ?

- No native replay — messages are deleted after consumption
- Classic queue model — not suitable for event sourcing
- **Good for**: async tasks, work distribution, RPC

### Why not Universal Messaging?

- Proprietary SAG license
- Not cloud-native
- webMethods expertise but vision = move away from legacy

---

## Database: PostgreSQL vs MySQL vs MongoDB

| Criteria | PostgreSQL | MySQL | MongoDB |
|----------|------------|-------|----------|
| **ACID** | ✅ Full | ✅ (InnoDB) | ⚠️ Eventual |
| **Native JSON** | ✅ JSONB indexable | ✅ JSON (less performant) | ✅ Native BSON |
| **Extensions** | ✅ pgvector, PostGIS, pg_cron | ❌ Limited | ❌ N/A |
| **Transactions** | ✅ Advanced MVCC | ✅ | ⚠️ Limited multi-doc |
| **Full-text search** | ✅ Native | ✅ Basic | ✅ Atlas Search |
| **Horizontal scaling** | ⚠️ (Citus, partitioning) | ⚠️ (Vitess) | ✅ Native sharding |
| **License** | PostgreSQL (free) | GPL (Oracle) | SSPL (restrictive) |

### Why PostgreSQL?

1. **Guaranteed ACID** — Subscriptions, API keys = critical data
2. **JSONB** — Flexibility for tool metadata without migrations
3. **Extensions** — pgvector for future RAG/embeddings, pg_cron for jobs
4. **Maturity** — 30+ years, battle-tested
5. **License** — Truly free, no Oracle/MongoDB traps

### Why not MongoDB?

- Restrictive SSPL license (post-2018)
- Less strict ACID = risk of inconsistent data
- **Good for**: rapid prototyping, highly variable schema

---

## Auth: Keycloak vs Auth0 vs Okta

| Criteria | Keycloak | Auth0 | Okta |
|----------|----------|-------|------|
| **Hosting** | Self-hosted | SaaS | SaaS |
| **Cost** | Free | ~$23/1K MAU | ~$2/user/mo |
| **OIDC/SAML** | ✅ Complete | ✅ | ✅ |
| **Customization** | ✅ Full (themes, SPI) | ⚠️ Limited | ⚠️ Limited |
| **Multi-tenant** | ✅ Realms | ✅ Organizations | ✅ |
| **Data residency** | ✅ Your infra | ❌ US/EU per plan | ❌ |
| **License** | Apache 2.0 | Proprietary | Proprietary |

### Why Keycloak?

1. **Self-hosted** — Data stays in our infrastructure
2. **Free** — No per-user cost
3. **Open source** — 100% customizable
4. **Standard** — Complete OIDC/SAML/OAuth2
5. **Multi-tenant** — One realm per tenant possible

### Why not Auth0/Okta?

- Cost explodes with number of users
- External SaaS dependency
- **Good for**: rapid MVP, team without IAM expertise

---

## Observability: Prometheus + Grafana + Loki vs Datadog vs ELK

| Criteria | Prometheus/Grafana/Loki | Datadog | ELK Stack |
|----------|-------------------------|---------|------------|
| **Cost** | Free (self-hosted) | ~$15-30/host/mo | Free or Elastic Cloud |
| **K8s-native** | ✅ De facto standard | ✅ Agent | ⚠️ Heavier |
| **Metrics** | Prometheus (pull) | Agent (push) | Metricbeat |
| **Logs** | Loki (labels) | Integrated logs | Logstash → ES |
| **Traces** | Jaeger/Tempo | Integrated APM | Elastic APM |
| **Query** | PromQL, LogQL | Proprietary | Lucene/KQL |
| **Alerting** | Alertmanager | Integrated | Watcher/ElastAlert |

### Why Prometheus + Grafana + Loki?

1. **K8s standard** — Native integration, massive community
2. **Free** — No per-host/volume cost
3. **Labels** — Same paradigm as K8s (selector)
4. **Grafana** — Unified dashboards for metrics + logs
5. **Open source** — No lock-in

### Why not Datadog?

- Prohibitive cost at scale
- Vendor lock-in
- **Good for**: teams wanting all-in-one managed solution

---

## GitOps: ArgoCD vs Flux vs Jenkins

| Criteria | ArgoCD | Flux | Jenkins |
|----------|--------|------|----------|
| **UI** | ✅ Rich Web UI | ❌ CLI only | ✅ UI (aging) |
| **Paradigm** | Pull-based GitOps | Pull-based GitOps | Push-based CI/CD |
| **Multi-cluster** | ✅ Native | ✅ | ⚠️ Complex |
| **Helm/Kustomize** | ✅ | ✅ | Via plugins |
| **Diff/Preview** | ✅ Visualization | ❌ | ❌ |
| **RBAC** | ✅ Integrated | ⚠️ K8s RBAC | Jenkins RBAC |
| **CNCF Adoption** | Graduated | Graduated | N/A |

### Why ArgoCD?

1. **UI** — Sync state visualization (demo-friendly!)
2. **Pull-based** — Cluster pulls from Git (security)
3. **Diff** — See what will change before apply
4. **CNCF Graduated** — Proven maturity
5. **Multi-cluster** — Ready for Enterprise scale

### Why not Flux?

- No native UI — less accessible for demo/debug
- **Good for**: CLI-first teams, GitOps purists

---

## Non-K8s Automation: AWX (Ansible) vs Terraform

| Criteria | AWX/Ansible | Terraform |
|----------|-------------|------------|
| **Paradigm** | Procedural + idempotent | Declarative (state) |
| **Target** | Everything (SSH, API, cloud) | Infrastructure-as-Code |
| **State** | No state file | State file required |
| **Config mgmt** | ✅ Designed for | ❌ Not its role |
| **UI/Scheduling** | ✅ AWX | ❌ (Terraform Cloud paid) |
| **Audit** | ✅ AWX job history | ⚠️ Via CI/CD |

### Why AWX/Ansible?

1. **webMethods** — Need to push config via REST API
2. **Idempotent** — Can replay without side effects
3. **AWX UI** — Scheduling, audit, RBAC, credentials vault
4. **Versatile** — Not limited to cloud infrastructure

### Why not Terraform for webMethods?

- Terraform = provision infrastructure (VMs, networks, cloud resources)
- Not suitable for post-deployment application configuration
- **Good for**: creating K8s cluster, S3 buckets, VPCs

---

## Gateway v2: Rust + eBPF vs Go vs C++

| Criteria | Rust | Go | C++ |
|----------|------|-----|-----|
| **Memory safety** | ✅ Compile-time | ✅ GC | ❌ Manual |
| **Performance** | ~C/C++ | Very good | Optimal |
| **Async** | ✅ Tokio (zero-cost) | ✅ Goroutines | ⚠️ Complex |
| **eBPF** | ✅ Aya (native) | ⚠️ Cilium/libbpf | ✅ libbpf |
| **Binaries** | Static, small | Static, medium | Dependencies |
| **Learning curve** | High | Low | Very high |
| **Cloud-native ecosystem** | Growing | Dominant (K8s, Docker) | Legacy |

### Why Rust for stoa-proxy?

1. **eBPF + Aya** — Native Rust ↔ eBPF integration
2. **Memory safety** — No buffer overflow, data races
3. **Performance** — Zero-cost abstractions, no GC pause
4. **Async** — Tokio/Hyper = high-perf HTTP stack
5. **Modern** — Attracts contributors, avoids technical debt

### Why not Go?

- Go = CLI, API, orchestration (stoa-cli, stoa-api)
- For critical data path (proxy) = Rust more suitable
- Cilium uses Go + C/eBPF, not pure Go

---

## Search: OpenSearch vs Elasticsearch vs Meilisearch

| Criteria | OpenSearch | Elasticsearch | Meilisearch |
|----------|------------|---------------|-------------|
| **License** | Apache 2.0 | SSPL (restrictive) | MIT |
| **Fork of** | ES 7.10 | Original | N/A |
| **Features** | Complete | Complete | Simplified |
| **K8s Operator** | ✅ | ✅ (ECK paid features) | ✅ |
| **ML/Vector** | ✅ k-NN | ✅ (paid) | ⚠️ Basic |
| **Adoption** | AWS, community | Elastic, legacy | Startups |

### Why OpenSearch?

1. **Apache 2.0 License** — Truly free
2. **ES Fork** — Compatible, easy migration
3. **AWS-free** — Can run on-prem
4. **k-NN** — Vector search for future RAG

### Why not Elasticsearch anymore?

- SSPL license since 2021 — cloud restrictions
- Elastic vs AWS drama = vendor risk

---

## Summary of Principles

| Principle | Application |
|-----------|-------------|
| **Open Source first** | Avoid lock-in, contribute upstream |
| **K8s-native** | Operators, CRDs, GitOps |
| **Right tool for the job** | Kafka for events, PostgreSQL for ACID, etc. |
| **Self-hosted possible** | No mandatory SaaS dependency |
| **Permissive license** | Apache 2.0, MIT, PostgreSQL — avoid GPL, SSPL |
| **Cloud-agnostic** | No mandatory managed service |

---

## Current Implementation (January 2026)

### Production Stack Deployed

| Component | Technology | Version | Status |
|-----------|------------|---------|--------|
| **Control Plane UI** | React + TypeScript | 18.x | ✅ Prod |
| **Developer Portal** | React + Vite + TailwindCSS | - | ✅ Prod |
| **Control Plane API** | FastAPI + Python | 3.11 | ✅ Prod |
| **MCP Gateway** | FastAPI + Python | 3.11 | ✅ Prod |
| **Database** | PostgreSQL | 16.x | ✅ Prod |
| **Auth** | Keycloak | 24.x | ✅ Prod |
| **Messaging** | Redpanda (Kafka-compatible) | - | ✅ Prod |
| **API Gateway** | webMethods | Trial | ✅ Prod |
| **Orchestration** | Kubernetes (EKS) | 1.29 | ✅ Prod |
| **Secrets** | HashiCorp Vault | - | ✅ Prod |
| **Observability** | Prometheus + Grafana + Loki | - | ✅ Prod |
| **GitOps** | ArgoCD | - | ✅ Prod |

### Recent Features

| Feature | Ticket | Description |
|---------|--------|-------------|
| **MCP Subscriptions** | CAB-247 | Subscription API with secure API keys |
| **API Key Rotation** | CAB-314 | Rotation with grace period (1-168h) |
| **Webhook Notifications** | CAB-315 | Events: created, approved, revoked, key_rotated |
| **2FA Key Reveal** | - | TOTP step-up auth to reveal API keys |
| **PostgreSQL Backup** | CAB-309 | Daily CronJob + S3 + 7-day retention |
| **Gateway Healthcheck** | - | CronJob every 2 minutes with auto-restart |

### Production URLs

| Service | URL |
|---------|-----|
| Console (Admin) | https://console.stoa.cab-i.com |
| Developer Portal | https://portal.stoa.cab-i.com |
| API (direct) | https://api.stoa.cab-i.com |
| API Gateway Runtime | https://apis.stoa.cab-i.com |
| MCP Gateway | https://mcp.stoa.cab-i.com |
| Auth (Keycloak) | https://auth.stoa.cab-i.com |
| Monitoring (Grafana) | https://grafana.stoa.cab-i.com |
| ArgoCD | https://argocd.stoa.cab-i.com |

### Backup Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Backup Strategy                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PostgreSQL (CAB-309)                                       │
│  ├── CronJob: 02:00 UTC daily                              │
│  ├── Format: pg_dump + gzip                                │
│  ├── Storage: S3 (stoa-backups/postgres/)                  │
│  ├── Retention: 7 days                                      │
│  └── Restore: scripts/backup/backup-postgres.sh --restore  │
│                                                             │
│  Vault Snapshots                                           │
│  ├── CronJob: Scheduled                                    │
│  ├── Format: Raft snapshot                                 │
│  └── Storage: S3 (stoa-backups/vault/)                     │
│                                                             │
│  Gateway Healthcheck                                        │
│  ├── CronJob: */2 * * * * (every 2 min)                    │
│  └── Action: Auto-restart if unhealthy                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### RBAC Roles

| Role | Scope | Permissions |
|------|-------|-------------|
| `cpi-admin` | Platform | Full access (stoa:admin) |
| `tenant-admin` | Tenant | Manage own tenant APIs, webhooks |
| `devops` | Tenant | Deploy, promote APIs |
| `viewer` | Tenant | Read-only access |

---

## Links

- [CAB-367 GitOps Reconciliation](https://linear.app/hlfh-workspace/issue/CAB-367)
- [STOA Data Stack Architecture](https://www.notion.so/2e1faea66cb881b9ac7bd9e78dd07bcb)
- [STOA Open Core Strategy](https://www.notion.so/2defaea66cb88122ad7cd27ea8da4ae7)
- [GitHub Repository](https://github.com/cab-i/apim-aws)
