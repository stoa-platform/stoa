# What's New in STOA Platform v2.2.0

> Release date: 2026-03 (pending)
> Previous version: v2.1.0

## Highlights

- **LLM Proxy & Cost Management**: Multi-provider LLM routing (OpenAI, Azure, Mistral) with per-tenant budget tracking, circuit breakers, and a dedicated cost dashboard
- **Self-Service Signup**: End-to-end tenant provisioning flow — portal signup page, API provisioning endpoint, trial limits enforcement
- **MCP Protocol 2025-11-25**: Upgraded protocol with resources, prompts, completion endpoints, lazy discovery, and tool schema validation
- **OAuth 2.1 Hardening**: DPoP proof-of-possession binding, sender-constraint middleware, RFC 7592 DCR management
- **Skills System**: Gateway-native skills CRUD with circuit breaker health tracking and lazy MCP discovery
- **UAC (Universal API Contract)**: JSON Schema v1.0 validator, OpenAPI reverse transform, and round-trip conversion

## Gateway

### New Capabilities

- LLM provider router with cost tracking, circuit breaker, and multi-provider proxy (OpenAI, Azure OpenAI, Mistral)
- Subscription-aware Azure OpenAI routing with multi-namespace support
- Skills system with CRUD operations and circuit breaker health tracking
- MCP protocol bump to 2025-11-25 with resources, prompts, and completion REST endpoints
- Lazy MCP discovery with cache-first pattern
- Tool schema validation at registration time
- W3C traceparent propagation through proxy hops
- DPoP sender-constraint middleware for token binding
- RFC 7592 DCR management endpoints
- Proxy hardening with circuit breaker + retry for OAuth and CP calls
- Arena observability: metrics export, OpenSearch integration, persistent volumes
- LLM token tracking Grafana dashboard

### Performance

- Arena benchmark enterprise layer (20 dimensions across 4 categories)
- OpenSearch export for arena benchmark results

## Control Plane API

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/tenants/provision` | Self-service tenant provisioning |
| `POST` | `/v1/tenants/export` | Tenant export for disaster recovery |
| `POST` | `/v1/tenants/import` | Tenant import/restore |
| `GET/POST` | `/v1/billing/budgets` | LLM budget service + provider config |
| `GET/POST` | `/v1/billing/consumers` | Billing consumer CRUD |
| `GET/POST` | `/v1/billing/models` | Billing models + budget check |
| `GET/POST` | `/v1/contracts` | Contract lifecycle management |
| `GET/POST` | `/v1/data-governance` | Data governance endpoints |
| `GET/POST` | `/v1/pii` | PII masking middleware + admin endpoints |
| `GET` | `/v1/security/posture` | Security posture scanner service |
| `GET` | `/v1/system/info` | System info with edition/licensing model |
| `POST` | `/v1/signup` | Self-service signup service |

### Improvements

- UAC v1.0 JSON Schema validator library with OpenAPI reverse transform
- SCIM-to-Gateway reconciliation service
- PG audit trail with dual-write pattern
- Trial limits enforcement with per-tenant rate limiting
- Demo tenant automation for onboarding
- Seed data for Chat Completions API with 2 subscription plans

## Console UI

- Permission gates with `PermissionGate` component + Proxy Owner dashboard
- LLM Cost Management dashboard with per-tenant budget visualization
- Access Review dashboard for compliance workflows
- Enhanced Security Posture dashboard with token binding status
- Admin users, settings, and roles management pages
- Live deployment dashboard with SSE logs and step progress
- i18n framework with react-i18next (39+ nav strings extracted)
- Floating AI assistant chat widget
- Token usage dashboard widget

## Developer Portal

- Self-service signup page
- Chat Completions API enrichment panel with subscription flow
- Unified Marketplace page
- Execution taxonomy filters with 4-persona test coverage
- Advanced features panel
- Credential mapping management UI
- MCP Developer Self-Service with tenant-scoped servers
- Guided onboarding wizard
- RBAC-aware widget visibility

## Helm Chart

### New Values

| Key | Default | Description |
|-----|---------|-------------|
| `stoaGateway.llmProxy.enabled` | `false` | Enable LLM proxy routing |
| `stoaGateway.llmProxy.providers` | `[]` | LLM provider configurations |
| `stoaGateway.skills.enabled` | `false` | Enable skills system |
| `arena.enterprise.enabled` | `false` | Enable enterprise arena CronJob |

## Full Changelog

See [CHANGELOG.md](../../CHANGELOG.md) for the complete list of changes including internal improvements, refactoring, and test additions.
