# STOA Platform - Operational Runbooks

> **Linear Issue**: CAB-107 (APIM-9504)
> **Phase**: 9.5 - Production Readiness
> **Last Updated**: 2024-12-28

This directory contains operational procedures for incident management on the STOA platform.

---

## Runbook Index

### Critical (Immediate action required)

| Runbook | Description | Impact |
|---------|-------------|--------|
| [Vault Sealed](critical/vault-sealed.md) | HashiCorp Vault in sealed state | Secrets inaccessible, authentication down |
| [Vault Restore](critical/vault-restore.md) | Vault restore from S3 snapshot | Secrets recovery |
| [AWX Restore](critical/awx-restore.md) | AWX restore from S3 backup | Configuration recovery |
| [Gateway Down](critical/gateway-down.md) | webMethods API Gateway unavailable | All APIs down |
| [Database Connection](critical/database-connection.md) | PostgreSQL/RDS connection issues | Keycloak and services down |

### High (Resolution within the hour)

| Runbook | Description | Impact |
|---------|-------------|--------|
| [Gateway High Latency](high/gateway-high-latency.md) | High latency on Gateway | Latency SLA compromised |
| [Kafka Lag](high/kafka-lag.md) | High consumer lag on Redpanda | Deployments delayed |
| [Certificate Expiration](high/certificate-expiration.md) | TLS certificates expiring/expired | HTTPS services inaccessible |

### Medium (Resolution within the day)

| Runbook | Description | Impact |
|---------|-------------|--------|
| [Jenkins Pipeline Stuck](medium/jenkins-pipeline-stuck.md) | CI/CD pipeline stuck | Builds and deployments blocked |
| [AWX Unreachable](medium/awx-unreachable.md) | AWX (Ansible Tower) inaccessible | Deployment automation down |
| [API Rollback](medium/api-rollback.md) | API rollback procedure | Restore previous version |

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
```

### STOA Namespaces

| Namespace | Services |
|-----------|----------|
| `stoa` | API Gateway, Developer Portal |
| `stoa-system` | Control-Plane API/UI |
| `keycloak` | Keycloak IdP |
| `vault` | HashiCorp Vault |
| `kafka` / `redpanda` | Redpanda (Kafka) |
| `awx` | AWX (Ansible Tower) |
| `jenkins` | Jenkins CI/CD |
| `monitoring` | Prometheus, Grafana |
| `argocd` | ArgoCD GitOps |
| `cert-manager` | Certificate management |

### Main URLs

| Service | URL | Description |
|---------|-----|-------------|
| Console UI | https://console.stoa.cab-i.com | API Provider interface |
| **Developer Portal** | https://portal.stoa.cab-i.com | API Consumer portal |
| API Gateway Runtime | https://apis.stoa.cab-i.com | APIs via Gateway |
| Gateway Admin | https://gateway.stoa.cab-i.com | Gateway console |
| MCP Gateway | https://mcp.stoa.cab-i.com | AI-Native MCP endpoint |
| Control Plane API | https://api.stoa.cab-i.com | REST API backend |
| Keycloak | https://auth.stoa.cab-i.com | Identity Provider |
| Grafana | https://grafana.stoa.cab-i.com | Monitoring |
| AWX | https://awx.stoa.cab-i.com | Automation |
| ArgoCD | https://argocd.stoa.cab-i.com | GitOps CD |
| Vault | https://vault.stoa.cab-i.com | Secrets management |

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
