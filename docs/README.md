# STOA Platform Documentation

Welcome to the STOA Platform documentation. STOA is a multi-tenant API management platform with Control-Plane UI, GitOps, and Event-Driven Architecture.

## Quick Links

| Document | Description |
|----------|-------------|
| [Getting Started](./getting-started.md) | Quick start guide for new users |
| [Installation](./installation.md) | Detailed installation instructions |
| [Configuration](./configuration.md) | Configuration reference |
| [Architecture](./ARCHITECTURE-COMPLETE.md) | System architecture overview |

## Documentation Structure

### Core Documentation

- **[Architecture](./ARCHITECTURE-COMPLETE.md)** - Complete system architecture
- **[Architecture Presentation](./ARCHITECTURE-PRESENTATION.md)** - Visual architecture overview
- **[Technology Choices](./TECHNOLOGY-CHOICES.md)** - Technology stack decisions

### Features

- **[Portal](./PORTAL.md)** - Developer Portal documentation
- **[Subscriptions](./SUBSCRIPTIONS.md)** - API subscription system
- **[MCP Subscriptions](./MCP-SUBSCRIPTIONS.md)** - MCP Gateway subscriptions
- **[MCP Claude AI Integration](./MCP-CLAUDEAI-INTEGRATION.md)** - Claude AI integration

### Operations

- **[Observability](./OBSERVABILITY.md)** - Monitoring and logging
- **[GitOps Setup](./GITOPS-SETUP.md)** - GitOps configuration
- **[SLO/SLA](./SLO-SLA.md)** - Service level objectives
- **[Benchmarks](./BENCHMARKS.md)** - Performance benchmarks
- **[E2E Testing](./E2E-TESTING.md)** - End-to-end testing

### Runbooks

Operational runbooks organized by severity:

- **[Critical Runbooks](./runbooks/critical/)** - Immediate response required
- **[High Priority Runbooks](./runbooks/high/)** - Response within 1 hour
- **[Medium Priority Runbooks](./runbooks/medium/)** - Response within 4 hours

### Integrations

- **[IBM webMethods Gateway API](./ibm/webmethods-gateway-api.md)** - Gateway integration

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/PotoMitan/stoa/issues)
- **Discussions**: [GitHub Discussions](https://github.com/PotoMitan/stoa/discussions)
- **Security**: See [SECURITY.md](../SECURITY.md) for reporting vulnerabilities

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines.
