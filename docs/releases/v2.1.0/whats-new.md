# What's New in STOA Platform v2.1.0

> Release date: 2026-03-01
> Previous version: v1.0.0
> Commits: 1091 | Features: 336 | Fixes: 300

## Highlights

- **Multi-Provider LLM Proxy**: The gateway now routes LLM requests to Azure OpenAI, Mistral, and other providers with subscription-aware namespace routing and cost tracking
- **Self-Service Signup**: New tenant provisioning flow — API endpoint + portal signup page + usage limits enforcement
- **MCP Skills System**: Tools can now be organized as skills with CRUD management, lazy discovery, and schema validation at registration
- **Gateway Arena 3-Layer Benchmark**: Continuous verification system (L0 proxy baseline, L1 enterprise AI readiness with 20 dimensions, L2 platform CUJ verification)
- **OAuth 2.1 / DPoP**: Full MCP OAuth discovery chain (RFC 9728 + RFC 8414) with DPoP sender-constraint binding and DCR management (RFC 7592)
- **UAC (Universal API Contract)**: JSON Schema v1.0 + validator + OpenAPI reverse transform enabling "Define Once, Expose Everywhere"

## Gateway (stoa-gateway)

### New Capabilities

- **LLM Proxy**: Multi-provider routing (Azure OpenAI, Mistral) with co-processors, subscription-aware namespace selection, and cost tracking per tenant
- **Sender Constraint**: DPoP `cnf.jkt` token-to-proof binding for zero-trust API access
- **Skills System**: Full CRUD lifecycle for skills, lazy MCP discovery with cache-first pattern, schema validation at tool registration
- **DCR Management**: RFC 7592 Dynamic Client Registration management endpoints
- **Proxy Hardening**: Circuit breaker + retry for OAuth and Control Plane calls, auto-RCA on failures
- **W3C Traceparent**: Distributed tracing propagation through proxy hops

### Improvements

- Arena observability with metrics export and OpenSearch integration
- Trimmed trailing slash handling for LLM proxy upstream URLs

## Control Plane API

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/tenants/provision` | Self-service tenant provisioning |
| `POST` | `/v1/tenants/export` | Tenant export for disaster recovery |
| `POST` | `/v1/tenants/import` | Tenant import/restore |
| `GET` | `/v1/system/info` | System info with edition/licensing model |
| `POST` | `/v1/contracts` | Contract lifecycle management |

### Improvements

- UAC v1.0 JSON Schema + validator library
- UAC to OpenAPI reverse transform with round-trip tests
- Trial limits enforcement for self-service tenants
- Tenant usage limits and rate limiting

## Console UI

- Permission Gate component with Proxy Owner dashboard
- Admin pages: users, settings, roles management
- LLM Cost Management dashboard
- Access Review dashboard
- Enhanced Security Posture dashboard with token binding status
- Admin access requests page

## Developer Portal

- Self-service signup page
- Chat Completions API enrichment panel with subscription flow
- Execution taxonomy filters with 4-persona tests
- Unified Marketplace page
- MCP Developer Self-Service (tenant-scoped servers)
- i18n quality gate + shared glossary
- Credential mapping management UI

## Gateway Arena (Benchmark)

- **Layer 0**: k6 proxy baseline (7 scenarios, median-of-5, CI95 confidence intervals)
- **Layer 1**: Enterprise AI Readiness expanded from 8 to 20 dimensions across 4 categories (Core, LLM Intelligence, MCP Depth, Security & Compliance)
- **Layer 2**: Platform continuous verification (3 CUJs every 15 min with dead man's switch)
- Multi-protocol support: STOA REST + Gravitee 4.8 Streamable HTTP
- VPS sidecar benchmarks for co-located gateways

## Helm Chart

No breaking changes. New values for LLM proxy and skills system configuration.

## Full Changelog

See [CHANGELOG.md](../../CHANGELOG.md) for the complete list of 1091 changes.
