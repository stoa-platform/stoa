# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- Phase 17: AI Gateway with LLM cost optimization
- Phase 18: Community launch
- eBPF acceleration (Phase 2)
- B2B Protocol Binders (EDI, SWIFT)

## [0.1.0] - 2026-01-31

Initial release of STOA Platform - The Agent Gateway for Enterprise.

### Added

#### MCP Gateway
- MCP (Model Context Protocol) native support for AI agent tools
- Multi-tenant architecture with team-based isolation
- Tool Registry with discovery and versioning
- Subscription management for tools per team
- Rate limiting and quota enforcement per tenant
- Request/response logging and tracing

#### Developer Portal
- React-based self-service portal
- Tool catalog with search and filtering
- Subscription management interface ("My Subscriptions")
- API key generation and management
- Export configuration for Claude Desktop (`claude_desktop_config.json`)
- Team-based access control (RBAC)

#### Authentication & Security
- Keycloak OIDC integration for SSO
- Multi-tenant RBAC (Role-Based Access Control)
- Two-Factor Authentication (2FA) with TOTP
- HashiCorp Vault integration for secrets management
- Secure API key storage with automatic rotation
- OAuth2 and mTLS support

#### Observability
- Prometheus metrics collection
- Grafana dashboards for MCP Gateway monitoring
- Loki for centralized log aggregation
- OpenSearch for audit trail and compliance
- Per-tenant metrics and cost tracking
- Real-time request tracing

#### Infrastructure
- Kubernetes-native deployment
- ArgoCD GitOps integration
- Helm charts for installation
- PostgreSQL database backend
- Kafka/Redpanda for event streaming

#### Supply Chain Security
- SBOM generation (CycloneDX format)
- Container image signing (Sigstore Cosign)
- Vulnerability scanning integration

### Security
- OWASP ZAP security audit completed
- Penetration testing performed
- Input validation on all API endpoints
- SQL injection protection
- XSS prevention in portal

### Documentation
- Landing page at https://gostoa.dev
- API documentation at https://docs.gostoa.dev
- Architecture Decision Records (ADRs)
- Deployment guides

## [0.0.1] - 2026-01-10

### Added
- Initial project scaffolding
- Basic MCP proxy implementation
- Proof of concept for multi-tenant routing

---

## Release Notes

### v0.1.0 Highlights

**STOA** (from Greek στοά, "portico") is an Agent Gateway that brings guardrails, cost control, and MCP interoperability at enterprise scale.

> "APIM-compatible when needed, AI-native where it counts."

#### Key Differentiators
- **MCP-Native**: First-class support for Model Context Protocol
- **Multi-Tenant Core**: Team isolation built-in, not bolted-on
- **Enterprise-Ready**: Auth, audit, observability from day one
- **Open Source**: Apache 2.0 license, CNCF/Kubernetes model

#### Demo Environment
- Portal: https://portal.stoa.cab-i.com
- Grafana: https://grafana.stoa.cab-i.com
- GitHub: https://github.com/stoa-platform/stoa

#### Supported MCP Tools (Demo)
| Tool | Description | Team |
|------|-------------|------|
| `crm-search` | Customer search | Team Alpha (Sales) |
| `billing-invoice` | Invoicing | Team Alpha (Finance) |
| `inventory-lookup` | Stock lookup | Team Beta (Ops) |
| `notifications-send` | Send notifications | Team Beta (Comms) |

---

[Unreleased]: https://github.com/stoa-platform/stoa/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/stoa-platform/stoa/compare/v0.0.1...v0.1.0
[0.0.1]: https://github.com/stoa-platform/stoa/releases/tag/v0.0.1
