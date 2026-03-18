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

| Tool | Version | Install |
|------|---------|---------|
| Docker & Docker Compose | 24+ | [docker.com](https://docs.docker.com/get-docker/) |
| Python | 3.11+ | `brew install python@3.11` or [python.org](https://www.python.org/) |
| Node.js | 20 LTS | `brew install node@20` or [nodejs.org](https://nodejs.org/) |
| Rust | stable | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| librdkafka | latest | `brew install librdkafka` (macOS) or `apt install librdkafka-dev` (Linux) |
| cmake | latest | `brew install cmake` (macOS) — needed for gateway Kafka feature |

### Option 1: Full Platform via Docker Compose (Recommended for first run)

This starts **everything** — API, UI, Portal, Gateway, Keycloak, PostgreSQL, OpenSearch, Prometheus, Grafana — in one command:

```bash
# Clone
git clone https://github.com/stoa-platform/stoa.git
cd stoa

# Start all services
cd deploy/docker-compose
docker compose up -d

# Wait for all services to be healthy (~2-3 min)
docker compose ps

# Access the platform:
#   Console UI:   http://localhost        (via nginx)
#   Keycloak:     http://localhost:8080   (admin/admin)
#   OpenSearch:   http://keycloak:5601/logs (OIDC login)
#   Grafana:      http://localhost/grafana
#   API:          http://localhost/api/v1/health
```

**Demo users** (Keycloak):

| User | Password | Role |
|------|----------|------|
| halliday | `ReadyPlayer1!rpo` | Platform admin (cpi-admin) |
| parzival | `CopperKey2045!s` | Tenant admin (oasis-gunters) |
| art3mis | `JadeKey2045!a` | Tenant admin (oasis-gunters) |
| sorrento | `CrystalKey2045!x` | Tenant admin (ioi-sixers) |

**Troubleshooting**:

| Symptom | Fix |
|---------|-----|
| Keycloak fails with "wrong password" | `docker compose down -v keycloak && docker compose up -d keycloak` (wipe H2 DB) |
| OpenSearch 401 | `docker volume rm stoa-quickstart_opensearch-data stoa-quickstart_opensearch-security && docker compose up -d opensearch` |
| Port 8080 in use | Set `PORT_KEYCLOAK=8180` in `.env` |

### Option 2: Component Development (Faster iteration)

Start only the dependencies via Docker Compose, then run the component you're working on locally:

```bash
# Start dependencies only (DB, Keycloak, message broker)
cd deploy/docker-compose
docker compose up -d postgres keycloak redpanda

# In a new terminal — run the component you're working on:

# API (Python)
cd control-plane-api
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# Console UI (React)
cd control-plane-ui
npm install
npm start  # http://localhost:5173

# Portal (React)
cd portal
npm install
npm start  # http://localhost:5174

# Gateway (Rust)
cd stoa-gateway
cargo run
```

### Option 3: Make targets

```bash
# Install all component dependencies
make setup

# Run components (each in a separate terminal)
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

### License Headers

All source files must include an Apache 2.0 license header with SPDX identifier. A script is provided to check and add headers automatically:

```bash
# Check for missing headers (CI mode — exits 1 if any missing)
python scripts/add-license-headers.py --check .

# Preview what would change
python scripts/add-license-headers.py --dry-run .

# Add headers to all files missing them
python scripts/add-license-headers.py .
```

The script supports Python, Rust, TypeScript, JavaScript, Go, Java, Shell, YAML, CSS, SQL, and more. It uses the appropriate comment style for each file type.

Expected header format (Python example):

```python
# Copyright 2026 STOA Platform Authors
# SPDX-License-Identifier: Apache-2.0
```

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

## Linting

```bash
# Run all linters
make lint

# Run by component
make lint-api        # ruff + black
make lint-ui         # eslint + prettier + tsc
make lint-portal     # eslint + prettier + tsc
make lint-gateway    # clippy + fmt

# List all available make targets
make help
```

## Documentation

- Update relevant docs when changing functionality
- Use clear, concise language
- Include code examples where helpful
- Keep the README up to date

## Community

- [Discord](https://discord.gg/j8tHSSes) — Chat with the community
- [Twitter/X](https://x.com/gostoa) — Follow for updates
- [Email](mailto:hello@gostoa.dev) — Reach out directly

## Recognition

Contributors are recognized in our [CONTRIBUTORS.md](CONTRIBUTORS.md) file and release notes. We appreciate every contribution, no matter how small!

---

Thank you for contributing to STOA! 🚀
