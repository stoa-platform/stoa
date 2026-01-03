# Runbook: [COMPONENT] - [INCIDENT TYPE]

> **Severity**: [SEVERITY_BADGE] Critical | High | Medium
> **Last updated**: YYYY-MM-DD
> **Owner**: Platform Team
> **Linear Issue**: CAB-XXX

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `AlertName` | condition | [Dashboard Link](https://grafana.dev.stoa.cab-i.com/d/xxx) |

### Observed Behavior

- Description of abnormal behavior observed
- Typical error messages

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | |
| **APIs** | |
| **SLA** | |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check pod status
kubectl get pods -n <namespace> -l app=<component>

# 2. Check recent logs
kubectl logs -n <namespace> -l app=<component> --tail=100 --since=5m

# 3. Check events
kubectl get events -n <namespace> --sort-by='.lastTimestamp' | tail -20

# 4. Check metrics
kubectl top pods -n <namespace>
```

### Verification Points

- [ ] Pod running?
- [ ] Service accessible?
- [ ] Sufficient resources (CPU/Memory)?
- [ ] Network policies OK?
- [ ] Secrets/ConfigMaps mounted?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Cause 1 | High | Verification command |
| Cause 2 | Medium | Verification command |
| Cause 3 | Low | Verification command |

---

## 3. Resolution

### Immediate Action (mitigation)

> **Objective**: Restore service quickly

```bash
# Mitigation commands
```

### Corrective Action (fix root cause)

> **Objective**: Fix the root cause

```bash
# Correction commands
```

### Rollback if necessary

```bash
# Rollback commands
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] Service responds normally
- [ ] Metrics back to normal
- [ ] No errors in logs
- [ ] Smoke tests passed
- [ ] Alerts resolved in Grafana

### Verification Commands

```bash
# Service verification
curl -s https://<service>.dev.stoa.cab-i.com/health | jq .

# Metrics verification
kubectl exec -n monitoring prometheus-0 -- \
  promtool query instant http://localhost:9090 'up{job="<job>"}'
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team | After 15 min without resolution | Slack `#platform-team` |
| L3 | Vendor Support | If blocked or major incident | Support ticket |

### Emergency Contacts

| Role | Name | Contact |
|------|------|---------|
| Platform Lead | - | @platform-lead |
| Security | - | @security-team |
| Management | - | @engineering-manager |

---

## 6. Post-mortem

### To document after resolution

- [ ] Incident timeline
- [ ] Root cause identified
- [ ] Preventive actions defined
- [ ] Runbook updated if necessary

### Post-mortem Template

```markdown
## Incident: [TITLE]
**Date**: YYYY-MM-DD HH:MM
**Duration**: X hours Y minutes
**Severity**: Critical/High/Medium

### Timeline
- HH:MM - Detection
- HH:MM - First action
- HH:MM - Resolution

### Root Cause
[Description]

### Preventive Actions
- [ ] Action 1
- [ ] Action 2
```

---

## 7. References

### Documentation

- [STOA Architecture](../ARCHITECTURE-PRESENTATION.md)
- [Component documentation](link)

### Grafana Dashboards

- [Main dashboard](https://grafana.dev.stoa.cab-i.com/d/xxx)
- [Detailed dashboard](https://grafana.dev.stoa.cab-i.com/d/yyy)

### Previous Incidents

| Date | Issue | Resolution |
|------|-------|------------|
| YYYY-MM-DD | CAB-XXX | Description |

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| YYYY-MM-DD | @author | Initial creation |
