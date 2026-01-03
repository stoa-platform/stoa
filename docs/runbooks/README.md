# STOA Platform - Runbooks Operationnels

> **Linear Issue**: CAB-107 (APIM-9504)
> **Phase**: 9.5 - Production Readiness
> **Last Updated**: 2024-12-28

Ce repertoire contient les procedures operationnelles pour la gestion des incidents sur la plateforme STOA.

---

## Index des Runbooks

### Critical (Action immediate requise)

| Runbook | Description | Impact |
|---------|-------------|--------|
| [Vault Sealed](critical/vault-sealed.md) | HashiCorp Vault en etat sealed | Secrets inaccessibles, authentification KO |
| [Gateway Down](critical/gateway-down.md) | webMethods API Gateway indisponible | Toutes les APIs down |
| [Database Connection](critical/database-connection.md) | Problemes de connexion PostgreSQL/RDS | Keycloak et services down |

### High (Resolution dans l'heure)

| Runbook | Description | Impact |
|---------|-------------|--------|
| [Gateway High Latency](high/gateway-high-latency.md) | Latence elevee sur le Gateway | SLA de latence compromis |
| [Kafka Lag](high/kafka-lag.md) | Consumer lag eleve sur Redpanda | Deploiements retardes |
| [Certificate Expiration](high/certificate-expiration.md) | Certificats TLS expirant/expires | Services HTTPS inaccessibles |

### Medium (Resolution dans la journee)

| Runbook | Description | Impact |
|---------|-------------|--------|
| [Jenkins Pipeline Stuck](medium/jenkins-pipeline-stuck.md) | Pipeline CI/CD bloque | Builds et deploiements bloques |
| [AWX Unreachable](medium/awx-unreachable.md) | AWX (Ansible Tower) inaccessible | Automation des deploiements KO |
| [API Rollback](medium/api-rollback.md) | Procedure de rollback d'une API | Restaurer version precedente |

---

## Quick Reference

### Commandes de diagnostic frequentes

```bash
# Statut global des pods
kubectl get pods -A | grep -v Running

# Events recents (toutes namespaces)
kubectl get events -A --sort-by='.lastTimestamp' | tail -30

# Logs d'un service specifique
kubectl logs -n <namespace> deploy/<deployment> --tail=100

# Metriques CPU/Memory
kubectl top pods -A | sort -k3 -h -r | head -20
```

### Namespaces STOA

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
| `cert-manager` | Gestion des certificats |

### URLs Principales

| Service | URL |
|---------|-----|
| Gateway | https://gateway.stoa.cab-i.com |
| DevOps UI | https://devops.stoa.cab-i.com |
| Control Plane API | https://api.stoa.cab-i.com |
| Keycloak | https://auth.stoa.cab-i.com |
| Grafana | https://grafana.stoa.cab-i.com |
| AWX | https://awx.stoa.cab-i.com |
| ArgoCD | https://argocd.stoa.cab-i.com |
| Vault | https://vault.stoa.cab-i.com |

---

## Escalation Matrix

| Severite | Temps de reponse | Qui contacter |
|----------|------------------|---------------|
| Critical | < 15 min | On-call + Platform Lead |
| High | < 1 heure | On-call DevOps |
| Medium | < 4 heures | Platform Team |
| Low | < 24 heures | Ticket standard |

### Contacts

| Role | Contact |
|------|---------|
| On-call DevOps | Slack `#ops-alerts` |
| Platform Team | Slack `#platform-team` |
| Security Team | Slack `#security` |
| Management | @engineering-manager |

---

## Template de Runbook

Voir [_TEMPLATE.md](_TEMPLATE.md) pour creer un nouveau runbook.

Structure standard:
1. **Symptomes** - Alertes, comportement, impact
2. **Diagnostic rapide** - Checklist < 5 min
3. **Resolution** - Actions par cause
4. **Verification** - Post-resolution checks
5. **Escalation** - Qui contacter
6. **Prevention** - Monitoring recommande

---

## Contribution

Pour ajouter ou modifier un runbook:

1. Creer une branche `docs/runbook-<component>`
2. Copier le template `_TEMPLATE.md`
3. Remplir toutes les sections
4. Tester les commandes
5. Creer une PR vers `main`

---

## Historique

| Date | Modification |
|------|--------------|
| 2024-12-28 | Creation initiale - 9 runbooks |
