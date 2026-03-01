## Summary

<!-- 1-3 bullets: what changed and why -->

## Linear Ticket

<!-- Link the Linear ticket, e.g. CAB-1234 -->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that causes existing functionality to change)
- [ ] Documentation update
- [ ] Refactoring (no functional changes)
- [ ] Tests (adding or updating tests)
- [ ] CI/CD (workflow, pipeline, or config changes)

## Breaking Changes

<!-- Does this PR introduce breaking changes? If yes, describe what breaks and how to migrate. -->

- [ ] No breaking changes
- [ ] Breaking change (describe below)

<!-- If breaking: what changed, who is affected, migration steps -->

## How Has This Been Tested?

<!-- Describe how you tested your changes -->

- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual testing

## Quality Gate Checklist

### All Components

- [ ] Code compiles with zero errors
- [ ] All tests pass locally
- [ ] No new lint warnings introduced
- [ ] No secrets or credentials in code
- [ ] Commit messages follow `type(scope): description` format

### Python (control-plane-api / landing-api)

- [ ] `ruff check .` clean
- [ ] `black --check .` clean
- [ ] `pytest tests/ --cov=src --cov-fail-under=70 -q` passes

### TypeScript (control-plane-ui / portal)

- [ ] `npm run lint` clean (max-warnings: 105 for console, 0 for portal)
- [ ] `npm run format:check` clean
- [ ] `npx tsc -p tsconfig.app.json --noEmit` clean

### Rust (stoa-gateway)

- [ ] `cargo fmt --check` clean
- [ ] `RUSTFLAGS=-Dwarnings cargo clippy --all-targets --all-features -- -D warnings` clean
- [ ] `cargo test` passes

## CI Required Checks

These 3 checks must pass before merge (branch protection):

1. **License Compliance** — Trivy SPDX scan
2. **SBOM Generation** — CycloneDX + SPDX
3. **Verify Signed Commits** — signature check

## Screenshots (if applicable)

<!-- Add screenshots to help explain UI changes -->
