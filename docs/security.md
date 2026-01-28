---
sidebar_position: 10
title: Security
description: STOA Platform security scanning, SBOM, and compliance policies
---

# Security

[![Security Scan](https://github.com/hlfh/stoa-platform/actions/workflows/security-scan.yml/badge.svg)](https://github.com/hlfh/stoa-platform/actions/workflows/security-scan.yml)

## CI Security Checks

The STOA Platform runs 9 automated security checks on every push to `main`/`develop`, on every PR to `main`, and daily at 06:00 UTC.

| # | Job | Tool | Scope | Fail Criteria |
|---|-----|------|-------|---------------|
| 1 | `verify-signatures` | git verify-commit | All commits | Warning only |
| 2 | `sast-rust` | Clippy (strict) | stoa-gateway | Any warning or denied lint |
| 3 | `sast-python` | Bandit | control-plane-api, mcp-gateway | Medium+ severity |
| 4 | `sast-javascript` | ESLint Security | control-plane-ui, portal | Error-level findings |
| 5 | `dependency-scan` | cargo-audit, pip-audit, npm audit | All dependencies | HIGH+ vulnerabilities |
| 6 | `secret-scan` | Gitleaks | Full git history | Any secret detected |
| 7 | `license-compliance` | Trivy SPDX | All packages | Warning on copyleft |
| 8 | `sbom-generation` | Trivy CycloneDX + SPDX | Full repository | N/A (generation only) |
| 9 | `container-scan` | Trivy image | Docker images | HIGH+ vulnerabilities |

## SBOM

Software Bill of Materials (SBOM) is generated automatically on every CI run in two formats:

- **CycloneDX** — machine-readable, integrates with dependency-track and similar tools
- **SPDX** — ISO/IEC 5962:2021 compliant, suitable for license compliance reporting

SBOM artifacts are retained for 90 days and downloadable from the GitHub Actions artifacts tab.

## Policies

### Dependency Management
- All dependencies are audited for known vulnerabilities (HIGH+)
- Python dependencies: `pip-audit`
- Rust dependencies: `cargo-audit`
- JavaScript dependencies: `npm audit`

### Container Security
- Container images are scanned with Trivy before deployment
- HIGH and CRITICAL vulnerabilities with available fixes block the pipeline

### Secret Detection
- Full git history is scanned with Gitleaks on every push
- Any detected secret blocks the pipeline

### Signed Commits
- Commit signatures are verified but not enforced (warning only)
- Contributors are encouraged to sign commits with GPG or SSH keys

## AI Governance

The STOA MCP Gateway provides AI-native API access with built-in security controls:

- **OPA Policy Engine** — fine-grained RBAC for tool access
- **Metering Pipeline** — usage tracking and rate limiting via Kafka
- **Tenant Isolation** — Kubernetes namespace-based isolation via CRDs

## Supply Chain Security

SLSA provenance and Cosign image signing are tracked under [CAB-400](https://github.com/hlfh/stoa-platform/issues) and are not yet implemented.

## Contact

Report security vulnerabilities to [security@gostoa.dev](mailto:security@gostoa.dev).
