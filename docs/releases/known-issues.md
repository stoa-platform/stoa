# Known Issues — STOA Platform

> Living document. Updated after each release or when new issues are discovered.
> Last updated: 2026-03-01

## Active Issues

### Gateway

| Issue | Since | Severity | Workaround | Tracking |
|-------|-------|----------|------------|----------|
| `cargo test --all-features` requires cmake installed | v2.0.0 | Low | Use `cargo test` without `--all-features` for local dev | — |
| Unicode escape in admin_auth causes non-required CI failure | v2.0.0 | Low | Non-blocking (gateway-ci fmt/clippy) | — |

### Control Plane API

| Issue | Since | Severity | Workaround | Tracking |
|-------|-------|----------|------------|----------|
| mypy failures in `pii/patterns.py`, `variable_resolver.py` | v2.0.0 | Low | Non-required CI check | — |

### CI / Build

| Issue | Since | Severity | Workaround | Tracking |
|-------|-------|----------|------------|----------|
| Dependency Review fails (GitHub Advanced Security not enabled) | v1.0.0 | Low | Non-blocking check | — |
| E2E tests require running infra, fail on UI-only PRs | v1.0.0 | Medium | Tag `@wip`, skip in UI PRs | — |
| DCO Check fails on squash-merged commits | v1.0.0 | Low | Expected behavior with squash merge | — |
| Branch protection `strict: true` requires update-branch before merge | v2.0.0 | Low | `gh api repos/.../pulls/{id}/update-branch -X PUT` | — |

### Helm / Deployment

| Issue | Since | Severity | Workaround | Tracking |
|-------|-------|----------|------------|----------|
| ArgoCD `OutOfSync` + `spec.selector: immutable` | v2.0.0 | Medium | Delete deployment, let ArgoCD recreate | — |
| Kyverno blocks pods missing `privileged: false` | v2.0.0 | High | Always set explicit `securityContext.privileged: false` | — |

## Resolved Issues

| Issue | Introduced | Resolved | Version | Resolution |
|-------|-----------|----------|---------|------------|
| — | — | — | — | — |

## Reporting Issues

Found a new issue? Report it at [github.com/stoa-platform/stoa/issues](https://github.com/stoa-platform/stoa/issues).
