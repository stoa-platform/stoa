# Contributing to stoactl

First off, thank you for considering contributing to stoactl! 🚀

## Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to conduct@gostoa.dev.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When you create a bug report, include as many details as possible:

- **Use a clear and descriptive title**
- **Describe the exact steps to reproduce the problem**
- **Provide specific examples** (commands run, output received, config used)
- **Describe the behavior you observed and what you expected**
- **Include your environment** (OS, Go version, stoactl version)

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. When creating an enhancement suggestion:

- **Use a clear and descriptive title**
- **Provide a detailed description of the suggested enhancement**
- **Explain why this enhancement would be useful**
- **List any alternatives you've considered**

### Creating Issues

We follow the **Marchemalo Standard** for issue quality. Every ticket should pass this test:

> *"Would an architect with 40 years of experience understand this issue in 30 seconds and know exactly what to deliver?"*

See the main [STOA Contributing Guide](https://github.com/stoa-platform/stoa/blob/main/CONTRIBUTING.md) for the full issue template and guidelines.

### Pull Requests

1. Fork the repo and create your branch from `main`
2. Follow our coding standards and conventions
3. Add tests for new functionality
4. Ensure `make test` passes
5. Update documentation as needed
6. Submit your pull request!

## Development Setup

### Prerequisites

- Go 1.22+
- Make
- Docker (for release builds)

### Local Development

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/stoactl.git
cd stoactl

# Build
make build

# Run tests
make test

# Run locally
./bin/stoactl version
```

### Project Structure

```
stoactl/
├── cmd/stoactl/       # Main entry point
├── internal/
│   ├── client/        # STOA API client
│   ├── cmd/           # Cobra commands
│   │   ├── apply/
│   │   ├── auth/
│   │   ├── config/
│   │   ├── delete/
│   │   └── get/
│   ├── config/        # Configuration handling
│   ├── output/        # Output formatting (table, json, yaml)
│   └── types/         # Shared types
├── .goreleaser.yaml   # Release configuration
└── Makefile
```

## Coding Standards

### Branch Naming

| Prefix | Purpose |
|--------|---------|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `refactor/` | Code refactoring |
| `test/` | Adding or updating tests |
| `chore/` | Maintenance tasks |

**Example:** `feat/add-apply-dry-run`

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
feat(apply): add --dry-run flag
fix(auth): handle token refresh on 401
docs: update installation instructions
```

### Go Code Style

- Follow [Effective Go](https://golang.org/doc/effective_go)
- Use `gofmt` for formatting
- Use `golangci-lint` for linting
- Keep functions small and focused
- Write meaningful comments for exported functions

### Adding a New Command

1. Create a new package under `internal/cmd/`
2. Implement the Cobra command
3. Register it in `internal/cmd/root.go`
4. Add tests
5. Update README if needed

## Testing

```bash
# Run all tests
make test

# Run with coverage
make test-coverage

# Run specific tests
go test ./internal/cmd/auth/...
```

## Releasing

Releases are automated via GoReleaser when a tag is pushed:

```bash
git tag v0.1.0
git push origin v0.1.0
```

This triggers:
- Multi-platform binary builds (Linux, macOS, Windows)
- Docker image push to ghcr.io
- Homebrew formula update
- GitHub release creation

## Community

- 💬 [Discord](https://discord.gg/stoa) — Chat with the community
- 📧 [Email](mailto:hello@gostoa.dev) — Reach out directly

## Recognition

Contributors are recognized in release notes. We appreciate every contribution!

---

Thank you for contributing to stoactl! 🏛️
