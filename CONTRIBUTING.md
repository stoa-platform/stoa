# Contributing to STOA Platform

Thank you for your interest in contributing to STOA Platform! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Project Structure](#project-structure)
- [Branching Strategy](#branching-strategy)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Testing](#testing)
- [Documentation](#documentation)
- [Issue Reporting](#issue-reporting)

---

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment. We expect all contributors to:

- Be respectful and considerate in communications
- Accept constructive criticism gracefully
- Focus on what is best for the community
- Show empathy towards other community members

---

## Getting Started

### Prerequisites

Before you begin, ensure you have the following installed:

| Tool | Version | Purpose |
|------|---------|---------|
| Node.js | 18+ | UI development |
| Python | 3.11+ | API development |
| Docker | 24+ | Containerization |
| kubectl | 1.28+ | Kubernetes management |
| Helm | 3.13+ | Chart management |
| Terraform | 1.6+ | Infrastructure as Code |
| AWS CLI | 2.x | AWS operations |

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/stoa.git
   cd stoa
   ```
3. Add the upstream remote:
   ```bash
   git remote add upstream https://github.com/PotoMitan/stoa.git
   ```

---

## Development Environment

### Control-Plane UI (React)

```bash
cd control-plane-ui
npm install
npm start
```

The UI will be available at `http://localhost:3000`.

**Environment variables:**
```bash
cp .env.example .env.local
# Edit .env.local with your Keycloak configuration
```

### Control-Plane API (FastAPI)

```bash
cd control-plane-api
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```

The API will be available at `http://localhost:8000`.

### MCP Gateway

```bash
cd mcp-gateway
python -m venv venv
source venv/bin/activate
pip install -e ".[dev,k8s]"
python -m src.main
```

The MCP Gateway will be available at `http://localhost:8080`.

### Local Kubernetes (Optional)

For testing Helm charts and Kubernetes manifests:

```bash
# Using kind (Kubernetes in Docker)
kind create cluster --name stoa-dev

# Deploy local stack
helm upgrade --install stoa-platform ./charts/stoa-platform \
  -n stoa-system --create-namespace \
  -f charts/stoa-platform/values-dev.yaml
```

---

## Project Structure

```
stoa/
├── control-plane-api/      # FastAPI backend
├── control-plane-ui/       # React frontend
├── mcp-gateway/            # MCP Gateway service
├── charts/                 # Helm charts
│   └── stoa-platform/      # Main platform chart
├── terraform/              # AWS infrastructure
│   ├── modules/            # Reusable modules
│   └── environments/       # Environment configs
├── ansible/                # AWX playbooks
├── gitops-templates/       # GitOps templates
├── scripts/                # Utility scripts
├── tests/                  # Integration tests
│   ├── load/               # K6 load tests
│   └── security/           # OWASP ZAP configs
└── docs/                   # Documentation
    └── runbooks/           # Operational runbooks
```

---

## Branching Strategy

We use a GitFlow-inspired branching model:

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready code |
| `develop` | Integration branch |
| `feature/*` | New features |
| `fix/*` | Bug fixes |
| `docs/*` | Documentation changes |
| `refactor/*` | Code refactoring |
| `chore/*` | Maintenance tasks |

### Creating a Branch

```bash
# Sync with upstream
git fetch upstream
git checkout develop
git merge upstream/develop

# Create feature branch
git checkout -b feature/CAB-123-my-feature
```

---

## Commit Guidelines

We follow [Conventional Commits](https://www.conventionalcommits.org/) specification.

### Format

```
<type>(<scope>): <subject>

[optional body]

[optional footer(s)]
```

### Types

| Type | Description |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `style` | Code style (formatting, semicolons) |
| `refactor` | Code refactoring |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks |
| `perf` | Performance improvements |
| `ci` | CI/CD changes |

### Scope Examples

- `api` - Control-Plane API
- `ui` - Control-Plane UI
- `mcp` - MCP Gateway
- `helm` - Helm charts
- `terraform` - Infrastructure
- `docs` - Documentation

### Examples

```bash
feat(api): add tenant quota management endpoint

fix(ui): resolve login redirect loop with Keycloak

docs(runbooks): add Vault restore procedure

chore(helm): update ingress annotations for ALB
```

### Linear Ticket Reference

Include the Linear ticket ID when applicable:

```bash
feat(mcp): implement OPA policy evaluation (CAB-122)
```

---

## Pull Request Process

### Before Submitting

1. **Sync with upstream:**
   ```bash
   git fetch upstream
   git rebase upstream/develop
   ```

2. **Run tests:**
   ```bash
   # API tests
   cd control-plane-api && pytest

   # UI tests
   cd control-plane-ui && npm test

   # MCP Gateway tests
   cd mcp-gateway && pytest --cov=src
   ```

3. **Lint your code:**
   ```bash
   # Python (ruff)
   ruff check . --fix
   ruff format .

   # TypeScript (eslint)
   npm run lint
   ```

4. **Update documentation** if needed

### PR Template

When creating a PR, include:

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Feature
- [ ] Bug fix
- [ ] Documentation
- [ ] Refactoring

## Linear Ticket
CAB-XXX

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed

## Checklist
- [ ] Code follows project style guidelines
- [ ] Self-review completed
- [ ] Documentation updated
- [ ] No sensitive data exposed
```

### Review Process

1. At least 1 approval required
2. All CI checks must pass
3. Squash merge to `develop`
4. Delete branch after merge

---

## Code Style

### Python (Control-Plane API, MCP Gateway)

We use **Ruff** for linting and formatting:

```toml
# pyproject.toml
[tool.ruff]
target-version = "py311"
line-length = 100
select = ["E", "W", "F", "I", "B", "C4", "UP"]
```

**Key conventions:**
- Type hints required for all functions
- Docstrings for public functions and classes
- Async functions preferred for I/O operations
- Use `structlog` for logging

### TypeScript (Control-Plane UI)

**Key conventions:**
- Functional components with hooks
- TypeScript strict mode
- Props interfaces defined for all components
- Use React Query for data fetching

### Terraform

**Key conventions:**
- Module-based organization
- Variables documented with descriptions
- Use `terraform fmt` before committing
- State stored in S3 with DynamoDB locking

### Helm Charts

**Key conventions:**
- Values documented in `values.yaml`
- Use `helm lint` before committing
- Templates should be idempotent
- Include NOTES.txt for post-install instructions

---

## Testing

### Unit Tests

| Component | Framework | Command |
|-----------|-----------|---------|
| Control-Plane API | pytest | `pytest tests/` |
| Control-Plane UI | Vitest | `npm test` |
| MCP Gateway | pytest + pytest-asyncio | `pytest --cov=src` |

### Integration Tests

```bash
# Run with local stack
docker-compose -f docker-compose.test.yml up -d
pytest tests/integration/
```

### Load Tests (K6)

```bash
cd tests/load
./scripts/run-load-tests.sh -e dev -s smoke
```

### Security Scans

```bash
cd tests/security
./scripts/run-security-scan.sh -t baseline -e dev
```

---

## Documentation

### Where to Document

| Type | Location |
|------|----------|
| API Reference | OpenAPI spec in code |
| Architecture | `docs/architecture/` |
| Runbooks | `docs/runbooks/` |
| User Guides | `docs/guides/` |
| Changelog | `CHANGELOG.md` |

### Documentation Standards

- Write in English
- Use Markdown format
- Include code examples where applicable
- Keep runbooks actionable with clear steps
- Update `Last Updated` dates

---

## Issue Reporting

### Bug Reports

Include:
- Clear title and description
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, browser, versions)
- Screenshots/logs if applicable

### Feature Requests

Include:
- Use case description
- Proposed solution
- Alternative approaches considered
- Impact assessment

### Security Issues

**Do not open public issues for security vulnerabilities.**

Email security concerns to: security@cab-i.com

---

## Getting Help

- **Slack:** `#stoa-dev` channel
- **Documentation:** https://docs.gostoa.dev
- **Issues:** GitHub Issues

---

## Recognition

Contributors are recognized in:
- `CHANGELOG.md` for significant contributions
- Release notes
- Annual contributor acknowledgments

Thank you for contributing to STOA Platform!
