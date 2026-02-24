# STOA Platform - Operational Runbooks

> **Last Updated**: 2026-02-15

This directory contains operational procedures for incident management on the STOA platform.

---

## Runbook Index

### Critical (Immediate action required)

| Runbook | Description | Impact |
|---------|-------------|--------|
| [ArgoCD Out of Sync](critical/argocd-out-of-sync.md) | ArgoCD application OutOfSync or Degraded | Deployment stale, new code not deployed |
| [AWX Restore](critical/awx-restore.md) | AWX restore from S3 backup | Configuration recovery |
| [Gateway Down](critical/gateway-down.md) | API Gateway unavailable | All APIs down |
| [Database Connection](critical/database-connection.md) | PostgreSQL connection issues | Keycloak and services down |
| [PostgreSQL Restore](critical/postgresql-restore.md) | PostgreSQL restore from backup | Data recovery |

### High (Resolution within the hour)

| Runbook | Description | Impact |
|---------|-------------|--------|
| [Operator Reconciliation Failed](high/operator-reconciliation-failed.md) | STOA operator drift/reconciliation errors | Gateway config stale |
| [Gateway High Latency](high/gateway-high-latency.md) | High latency on Gateway | Latency SLA compromised |
| [Gateway Registration Failed](high/gateway-registration-failed.md) | Gateway auto-registration issues | Gateway not orchestrated by CP |
| [Kafka Lag](high/kafka-lag.md) | High consumer lag on Redpanda | Deployments delayed |
| [Certificate Expiration](high/certificate-expiration.md) | TLS certificates expiring/expired | HTTPS services inaccessible |

### Medium (Resolution within the day)

| Runbook | Description | Impact |
|---------|-------------|--------|
| [Jenkins Pipeline Stuck](medium/jenkins-pipeline-stuck.md) | CI/CD pipeline stuck | Builds and deployments blocked |
| [AWX Unreachable](medium/awx-unreachable.md) | AWX (Ansible Tower) inaccessible | Deployment automation down |
| [API Rollback](medium/api-rollback.md) | API rollback procedure | Restore previous version |
| [MCP Gateway Migration](mcp-gateway-migration.md) | Python → Rust gateway migration | Gateway transition |

### Content Operations

| Runbook | Description | Trigger |
|---------|-------------|---------|
| [Post-Milestone Content Checklist](../POST-MILESTONE-CONTENT-CHECKLIST.md) | Update landing page, blog, docs, SEO after each milestone | Release, major feature, event |

### Archived (Obsolete — do not use)

| Runbook | Reason | Replacement |
|---------|--------|-------------|
| [Vault Sealed](../archive/vault-sealed.md) | Vault decommissioned Feb 2026 | Infisical (`vault.gostoa.dev`) |
| [Vault Restore](../archive/vault-restore.md) | Vault decommissioned Feb 2026 | Infisical (`vault.gostoa.dev`) |
| [Vault Emergency Unseal](../archive/vault-emergency-unseal.md) | Vault decommissioned Feb 2026 | Infisical (`vault.gostoa.dev`) |

---

## Quick Reference

### Common diagnostic commands

```bash
# Global pod status
kubectl get pods -A | grep -v Running

# Recent events (all namespaces)
kubectl get events -A --sort-by='.lastTimestamp' | tail -30

# Logs for a specific service
kubectl logs -n <namespace> deploy/<deployment> --tail=100

# CPU/Memory metrics
kubectl top pods -A | sort -k3 -h -r | head -20

# ArgoCD application status
kubectl get applications -n argocd -o custom-columns='NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'

# STOA operator metrics
kubectl port-forward -n stoa-system deploy/stoa-operator 8000:8000 &
curl -s http://localhost:8000/metrics | grep stoa_
```

### STOA Namespaces

| Namespace | Services |
|-----------|----------|
| `stoa-system` | Control-Plane API/UI, Portal, Gateway, Operator |
| `keycloak` | Keycloak IdP |
| `redpanda` | Redpanda (Kafka) |
| `argocd` | ArgoCD GitOps |
| `monitoring` | Prometheus, Grafana, Pushgateway |
| `cert-manager` | Certificate management |

### Main URLs

| Service | URL | Description |
|---------|-----|-------------|
| Console UI | https://console.gostoa.dev | API Provider interface |
| Developer Portal | https://portal.gostoa.dev | API Consumer portal |
| MCP Gateway | https://mcp.gostoa.dev | AI-Native MCP endpoint |
| Control Plane API | https://api.gostoa.dev | REST API backend |
| Keycloak | https://auth.gostoa.dev | Identity Provider |
| Grafana | https://grafana.gostoa.dev | Monitoring |
| Prometheus | https://prometheus.gostoa.dev | Metrics |
| ArgoCD | https://argocd.gostoa.dev | GitOps CD |
| Infisical | https://vault.gostoa.dev | Secrets management |

---

## Secrets Management

Secrets are managed via **Infisical** (self-hosted at `vault.gostoa.dev`). HashiCorp Vault, AWS Secrets Manager, and External Secrets Operator are decommissioned.

See `docs/SECRETS-ROTATION.md` for rotation procedures.

---

## Escalation Matrix

| Severity | Response time | Who to contact |
|----------|---------------|----------------|
| Critical | < 15 min | On-call + Platform Lead |
| High | < 1 hour | On-call DevOps |
| Medium | < 4 hours | Platform Team |
| Low | < 24 hours | Standard ticket |

### Contacts

| Role | Contact |
|------|---------|
| On-call DevOps | Slack `#ops-alerts` |
| Platform Team | Slack `#platform-team` |
| Security Team | Slack `#security` |
| Management | @engineering-manager |

---

## Runbook Template

See [_TEMPLATE.md](_TEMPLATE.md) to create a new runbook.

Standard structure:
1. **Symptoms** - Alerts, behavior, impact
2. **Quick Diagnosis** - Checklist < 5 min
3. **Resolution** - Actions by cause
4. **Verification** - Post-resolution checks
5. **Escalation** - Who to contact
6. **Prevention** - Recommended monitoring

---

## Contributing

To add or modify a runbook:

1. Create a branch `docs/runbook-<component>`
2. Copy the template `_TEMPLATE.md`
3. Fill in all sections
4. Test the commands
5. Create a PR to `main`

---

## History

| Date | Modification |
|------|--------------|
| 2024-12-28 | Initial creation - 9 runbooks |
| 2026-02-06 | Added Gateway Registration Failed runbook (ADR-028) |
| 2026-02-15 | Archived 3 Vault runbooks, added ArgoCD + Operator runbooks, updated for Infisical (CAB-1030) |
