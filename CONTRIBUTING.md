# Contributing to STOA

First off, thank you for considering contributing to STOA! 🏛️

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to conduct@gostoa.dev.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When you create a bug report, include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples** (config snippets, logs, etc.)
- **Describe the behavior you observed and what you expected**
- **Include your environment** (OS, Docker version, K8s version, etc.)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion:

- **Use a clear and descriptive title**
- **Provide a detailed description of the suggested enhancement**
- **Explain why this enhancement would be useful**
- **List any alternatives you've considered**

### Pull Requests

1. Fork the repo and create your branch from `main`
2. Follow our coding standards and conventions
3. Add tests if applicable
4. Ensure the test suite passes
5. Update documentation as needed
6. Submit your pull request!

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose
- kubectl (for K8s development)

### Local Development
```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/stoa.git
cd stoa

# Install dependencies
make install

# Start local environment
make dev

# Run tests
make test
```

## Coding Standards

### Branch Naming

Use prefixes to categorize your branches:

| Prefix | Purpose |
|--------|---------|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `refactor/` | Code refactoring |
| `test/` | Adding or updating tests |
| `chore/` | Maintenance tasks |

**Example:** `feat/add-rate-limiting`

### Commit Messages

We follow [Conventional Commits](https://www.conventionalcommits.org/):
```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples:**
```
feat(gateway): add rate limiting per tenant
fix(api): handle null subscription gracefully
docs: update API reference for v0.2
```

### Code Style

- **Python:** Follow PEP 8, use `ruff` for linting and `black` for formatting
- **TypeScript:** Use ESLint + Prettier with project config
- **All:** Keep functions small and focused, write meaningful comments

## Testing
```bash
# Run all tests
make test

# Run specific test suite
make test-unit
make test-integration
make test-e2e

# Run with coverage
make test-coverage
```

## Documentation

- Update relevant docs when changing functionality
- Use clear, concise language
- Include code examples where helpful
- Keep the README up to date

## Community

- 💬 [Discord](https://discord.gg/stoa) — Chat with the community
- 🐦 [Twitter/X](https://x.com/gostoa) — Follow for updates
- 📧 [Email](mailto:hello@gostoa.dev) — Reach out directly

## Recognition

Contributors are recognized in our [CONTRIBUTORS.md](CONTRIBUTORS.md) file and release notes. We appreciate every contribution, no matter how small!

---

Thank you for contributing to STOA! 🚀