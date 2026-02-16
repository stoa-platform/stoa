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

### Creating Issues

We follow the **Marchemalo Standard** for issue quality. Every ticket should pass this test:

> *"Would an architect with 40 years of experience understand this issue in 30 seconds and know exactly what to deliver?"*

#### Required Elements

Each issue MUST include:

| Element | Description |
|---------|-------------|
| **🎯 Objective** | One clear sentence stating what will be delivered |
| **💡 Why Now** | Context, urgency, and impact if not done |
| **📋 Deliverables** | Explicit list of what will be produced |
| **✅ Definition of Done** | Objective, verifiable criteria |
| **⏱️ Estimation** | Story points or time estimate |

#### Issue Template

```markdown
## 🎯 Objective
[One clear sentence]

## 💡 Why Now
[Context and urgency]

## 📋 Deliverables
- [ ] Deliverable 1
- [ ] Deliverable 2

## ✅ Definition of Done
- [ ] Verifiable criterion 1
- [ ] Verifiable criterion 2
- [ ] Tests pass
- [ ] Documentation updated (if applicable)

## ⏱️ Estimation
[X points] or [~Xh]

## 🔗 References
- Link 1
- Link 2
```

#### Anti-patterns to Avoid

| ❌ Bad | ✅ Good |
|--------|---------|
| "Improve the site" | "Add 3 concrete use cases to /use-cases with diagrams" |
| "Fix the bug" | "Endpoint /v1/users returns 500 when email=null → return 400 with message" |
| "Documentation" | "Create ADR-005 for multi-tenant isolation decision" |
| No DoD | "Done when: tests pass + docs updated + review approved" |

#### Splitting Large Issues

If an issue is estimated at **> 5 story points**, it MUST be split into smaller issues.

#### Non-Conforming Issues

Issues that don't meet the Marchemalo Standard will be labeled `needs-triage` and require revision before being worked on.

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
- Rust stable toolchain
- Docker & Docker Compose
- kubectl (for K8s development)

See [DEVELOPMENT.md](DEVELOPMENT.md) for detailed setup instructions per component.

### Local Development

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/stoa.git
cd stoa

# Install dependencies for all components
make setup

# Start the API, UI, and Gateway (each in a separate terminal)
make run-api
make run-ui
make run-gateway

# Run all tests
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

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`

**Scopes (optional):** `api`, `ui`, `portal`, `mcp`, `gateway`, `helm`, `ci`, `docs`, `deps`, `security`, `demo`

**Examples:**
```
feat(gateway): add rate limiting per tenant
fix(api): handle null subscription gracefully
docs: update API reference for v0.2
```

> Commits are validated automatically by [commitlint](https://commitlint.js.org/) via a Husky git hook. Invalid commit messages will be rejected locally.

### Developer Certificate of Origin (DCO)

All contributions must be signed off to certify you have the right to submit the code under the project's open source license.

**Sign your commits:**
```bash
git commit -s -m "feat(api): add new endpoint"
```

This adds a `Signed-off-by: Your Name <email>` line to your commit. See [CLA.md](CLA.md) for detailed instructions on signing commits, configuring automatic sign-off, and fixing unsigned commits.

### Code Style

- **Python:** Follow PEP 8, use `ruff` for linting and `black` for formatting
- **TypeScript:** Use ESLint + Prettier with project config
- **All:** Keep functions small and focused, write meaningful comments

## Testing

```bash
# Run all tests
make test

# Run by component
make test-api        # pytest (control-plane-api)
make test-ui         # vitest (console UI)
make test-portal     # vitest (portal)
make test-gateway    # cargo test (gateway)
make test-cli        # pytest (CLI)
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
