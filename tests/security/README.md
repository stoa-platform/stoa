# STOA Platform Security Testing

> **Phase**: 9.5 - Production Readiness
> **Ticket**: CAB-108
> **Tools**: OWASP ZAP, Trivy, pip-audit, npm audit
> **Last Updated**: 2026-01-05

## Overview

This directory contains security testing configurations for the STOA Platform. Security scans are automated via GitHub Actions but can also be run locally.

## Quick Start

### Run a Baseline Scan

```bash
# Against dev environment
./scripts/run-security-scan.sh -t baseline -e dev --docker

# Against staging
./scripts/run-security-scan.sh -t baseline -e staging --docker
```

### Run an API Scan

```bash
# Scans OpenAPI specification
./scripts/run-security-scan.sh -t api -e dev --docker
```

### Run a Full Scan (Dev/Staging Only)

```bash
# Active scanning - attacks the application
./scripts/run-security-scan.sh -t full -e dev --docker
```

## Scan Types

| Scan Type | Duration | Production Safe? | Description |
|-----------|----------|------------------|-------------|
| `baseline` | 5 min | ✅ Yes | Passive scanning only |
| `api` | 15 min | ⚠️ Careful | API-focused using OpenAPI spec |
| `full` | 30-60 min | ❌ No | Active attacks included |

## OWASP ZAP Configuration

### Configuration Files

```
tests/security/zap/
├── zap-baseline.yaml     # Baseline scan configuration
├── zap-full.yaml         # Full scan configuration
└── api-scan-rules.conf   # Alert rules (IGNORE/WARN/FAIL)
```

### Rule Configuration

The `api-scan-rules.conf` file controls how alerts are handled:

```conf
# Format: [rule_id]  [IGNORE/WARN/FAIL]

# Critical security headers
10035    FAIL    # Missing HSTS
40018    FAIL    # SQL Injection
90020    FAIL    # Command Injection

# Informational
10054    IGNORE  # Cookie SameSite (Keycloak handles)
10202    IGNORE  # Missing CSRF tokens (Bearer auth used)
```

### Common ZAP Rules

| Rule ID | Description | Default |
|---------|-------------|---------|
| 10021 | X-Content-Type-Options | WARN |
| 10035 | Strict-Transport-Security | FAIL |
| 10038 | Content Security Policy | WARN |
| 40012 | XSS (Reflected) | FAIL |
| 40014 | XSS (Persistent) | FAIL |
| 40018 | SQL Injection | FAIL |
| 90020 | OS Command Injection | FAIL |

## Container Scanning

### Trivy

Container images are scanned for vulnerabilities using Trivy:

```bash
# Scan control-plane-api
docker build -t stoa/control-plane-api:scan ./control-plane-api/
trivy image stoa/control-plane-api:scan

# Scan with severity filter
trivy image --severity HIGH,CRITICAL stoa/control-plane-api:scan
```

## Dependency Scanning

### Python (pip-audit)

```bash
cd control-plane-api
pip-audit -r requirements.txt
```

### JavaScript (npm audit)

```bash
cd control-plane-ui
npm audit
```

## GitHub Actions

Security scans run automatically:

| Trigger | Scan Type | Environment |
|---------|-----------|-------------|
| Weekly (Sunday 4AM) | baseline | staging |
| Manual dispatch | configurable | configurable |
| PR to main | baseline | staging |

### Manual Trigger

1. Go to Actions → Security Scan
2. Click "Run workflow"
3. Select environment and scan type
4. Click "Run workflow"

## Results

### Report Locations

- **Local**: `tests/security/results/`
- **CI/CD**: GitHub Actions artifacts
- **GitHub Security Tab**: SARIF reports from Trivy

### Interpreting Results

#### ZAP Risk Levels

| Risk | Description | Action |
|------|-------------|--------|
| High | Critical vulnerability | Must fix immediately |
| Medium | Significant issue | Fix before release |
| Low | Minor concern | Fix when possible |
| Info | Informational | Review periodically |

#### Trivy Severities

| Severity | CVSS Score | Action |
|----------|------------|--------|
| CRITICAL | 9.0-10.0 | Block deployment |
| HIGH | 7.0-8.9 | Fix within 24h |
| MEDIUM | 4.0-6.9 | Fix within 1 week |
| LOW | 0.1-3.9 | Fix when convenient |

## Authentication

For authenticated scans, set environment variables:

```bash
export ZAP_USER="test-user"
export ZAP_PASSWORD="test-password"
```

Or use GitHub Secrets for CI/CD:
- `ZAP_USER`
- `ZAP_PASSWORD`

## False Positive Management

### Adding Exceptions

Edit `zap/api-scan-rules.conf`:

```conf
# Ignore specific rule entirely
10096    IGNORE    # Timestamp disclosure

# Or in ZAP YAML, add alert filter:
- type: alertFilter
  rules:
    - ruleId: 10096
      newRisk: "Info"
      context: "STOA Platform"
```

### Documenting Exceptions

When ignoring a rule, document:
1. Why it's a false positive
2. What compensating controls exist
3. Who approved the exception

## Integration with CI/CD

### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

### Pull Request Gates

- Baseline scan must pass
- No HIGH or CRITICAL Trivy findings
- No secret leaks detected

## Troubleshooting

### "Target not reachable"

1. Check VPN connection
2. Verify environment is up
3. Check firewall rules

### "Authentication failed"

1. Verify credentials are correct
2. Check Keycloak is accessible
3. Ensure user has correct roles

### "Too many false positives"

1. Review `api-scan-rules.conf`
2. Add context-specific filters
3. Update OpenAPI spec with security schemes

## Related Documentation

- [SLO/SLA Documentation](../../docs/SLO-SLA.md)
- [Load Testing](../load/README.md)
- [OWASP ZAP Documentation](https://www.zaproxy.org/docs/)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
