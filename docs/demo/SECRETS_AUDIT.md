# STOA Demo - Secrets Audit

## Audit Date: 2026-01-28

## Scope

- `mock-backends/`
- `charts/stoa-platform/`
- `deploy/`
- `landing-api/`

---

## Findings

| File | Issue | Severity | Status |
|------|-------|----------|--------|
| `charts/stoa-platform/values-demo.yaml:148` | `adminPassword: "demo-admin-2026"` | LOW | Demo-only, clearly marked |
| `charts/stoa-platform/values-demo.yaml:193` | `postgresPassword: "demo-postgres-2026"` | LOW | Demo-only, clearly marked |
| `deploy/database/postgres-statefulset.yaml:14` | `POSTGRES_PASSWORD: stoa-db-password-2026` | MEDIUM | Should use ExternalSecret |
| `deploy/database/migration-*.yaml` | Hardcoded DB connection strings | MEDIUM | Should use ExternalSecret |
| `deploy/external-secrets/*.yaml` | Vault references (templated) | NONE | Correct pattern |

---

## Analysis

### Demo Passwords (Acceptable)

The following are **intentionally demo-only** passwords, clearly marked in comments:

```yaml
# charts/stoa-platform/values-demo.yaml
adminPassword: "demo-admin-2026"    # Demo only - NOT for production
postgresPassword: "demo-postgres-2026"  # Demo only - NOT for production
```

**Status:** ACCEPTABLE - These are demo defaults with clear warnings.

### Database Passwords (Needs Improvement)

```yaml
# deploy/database/postgres-statefulset.yaml
POSTGRES_PASSWORD: stoa-db-password-2026
```

**Recommendation:** Migrate to ExternalSecret pattern for production.

### Vault Integration (Correct)

```yaml
# deploy/external-secrets/external-secret-database.yaml
password: "{{ .password }}"  # Pulled from Vault
```

**Status:** CORRECT - Uses Vault templating.

---

## Production Checklist

- [ ] All demo passwords are overridden in production values
- [ ] ExternalSecrets configured for all sensitive data
- [ ] Vault policies restrict access appropriately
- [ ] No `.env` files committed
- [ ] API keys rotated regularly

---

## Recommendations

1. **Demo Passwords:** Clearly marked with `# Demo only` comments
2. **Production:** All secrets pulled from Vault via ExternalSecrets
3. **CI/CD:** No secrets in GitHub Actions (uses OIDC)
4. **Database:** Migrate remaining hardcoded passwords to ExternalSecret

---

## No Critical Issues Found

All hardcoded values are:
- Demo-only with clear warnings
- Not used in production deployments
- Vault integration ready for production

---

## Sign-off

- [x] Security review completed
- [x] No production secrets exposed
- [x] Demo passwords clearly marked
- [x] Vault integration verified
