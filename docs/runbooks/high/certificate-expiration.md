# Runbook: Certificate Expiration

> **Severity**: High
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Linear Issue**: CAB-107

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `CertificateExpiringSoon` | `cert_expiry_days < 30` | [Certificates](https://grafana.gostoa.dev/d/certs) |
| `CertificateExpired` | `cert_expiry_days <= 0` | [Certificates](https://grafana.gostoa.dev/d/certs) |
| `TLSHandshakeFailing` | `tls_handshake_errors > 0` | [Ingress](https://grafana.gostoa.dev/d/ingress) |

### Observed Behavior

- SSL/TLS errors in browsers
- `NET::ERR_CERT_DATE_INVALID`
- APIs return handshake errors
- Connections refused between internal services

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | Cannot access HTTPS services |
| **APIs** | API calls fail |
| **SLA** | Service completely unavailable |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check public endpoint certificates
echo | openssl s_client -servername gateway.gostoa.dev \
  -connect gateway.gostoa.dev:443 2>/dev/null | \
  openssl x509 -noout -dates

# 2. List all certificates in the cluster
kubectl get certificates -A

# 3. Check TLS secrets
kubectl get secrets -A -o json | jq -r '
  .items[] |
  select(.type == "kubernetes.io/tls") |
  "\(.metadata.namespace)/\(.metadata.name)"'

# 4. Check cert-manager
kubectl get pods -n cert-manager
kubectl logs -n cert-manager deploy/cert-manager --tail=50

# 5. Check Issuers
kubectl get clusterissuers
kubectl get issuers -A
```

### Verification Points

- [ ] cert-manager running?
- [ ] ClusterIssuer configured?
- [ ] Let's Encrypt accessible?
- [ ] DNS challenge OK (if wildcard)?
- [ ] HTTP challenge OK (if standard)?

### STOA Certificates to Monitor

| Service | Secret | Namespace | Issuer |
|---------|--------|-----------|--------|
| Gateway | `gateway-tls` | stoa | letsencrypt-prod |
| Keycloak | `keycloak-tls` | keycloak | letsencrypt-prod |
| DevOps UI | `devops-tls` | stoa-system | letsencrypt-prod |
| API | `api-tls` | stoa-system | letsencrypt-prod |
| Vault | `vault-tls` | vault | letsencrypt-prod |
| AWX | `awx-tls` | awx | letsencrypt-prod |

---

## 3. Resolution

### Case 1: Force certificate renewal

```bash
# Identify expired certificate
kubectl get certificate -A -o wide

# Force renewal by deleting the secret
kubectl delete secret gateway-tls -n stoa

# The Certificate resource will recreate the secret
kubectl get certificate gateway-cert -n stoa -w

# Check the new certificate
kubectl get secret gateway-tls -n stoa -o jsonpath='{.data.tls\.crt}' | \
  base64 -d | openssl x509 -noout -dates
```

### Case 2: cert-manager not working

```bash
# Check logs
kubectl logs -n cert-manager deploy/cert-manager --tail=100

# Check events
kubectl get events -n cert-manager --sort-by='.lastTimestamp'

# Restart cert-manager
kubectl rollout restart deployment -n cert-manager cert-manager
kubectl rollout restart deployment -n cert-manager cert-manager-webhook
kubectl rollout restart deployment -n cert-manager cert-manager-cainjector

# Check status
kubectl get pods -n cert-manager
```

### Case 3: HTTP challenge failing

```bash
# Check challenges in progress
kubectl get challenges -A

# View challenge details
kubectl describe challenge <challenge-name> -n <namespace>

# Check that Ingress allows challenge
kubectl get ingress -A | grep acme

# Manually test challenge
curl -v http://gateway.gostoa.dev/.well-known/acme-challenge/test
```

### Case 4: DNS challenge failing (wildcard)

```bash
# Check DNS configuration
kubectl get secret route53-credentials -n cert-manager

# Check DNS solver logs
kubectl logs -n cert-manager deploy/cert-manager | grep dns

# Test DNS resolution
dig _acme-challenge.gostoa.dev TXT

# Check Route53 permissions
aws route53 list-hosted-zones
```

### Case 5: Install certificate manually (emergency)

```bash
# Only in emergency if cert-manager is broken

# Generate CSR
openssl req -new -newkey rsa:2048 -nodes \
  -keyout gateway.key \
  -out gateway.csr \
  -subj "/CN=gateway.gostoa.dev"

# After obtaining signed certificate
kubectl create secret tls gateway-tls \
  --cert=gateway.crt \
  --key=gateway.key \
  -n stoa \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart pods to pick up new cert
kubectl rollout restart deployment -n stoa apigateway
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] New certificate valid
- [ ] Expiration date > 30 days
- [ ] No TLS errors
- [ ] Services accessible via HTTPS
- [ ] cert-manager healthy

### Verification Commands

```bash
# Check new certificate expiration
echo | openssl s_client -servername gateway.gostoa.dev \
  -connect gateway.gostoa.dev:443 2>/dev/null | \
  openssl x509 -noout -dates -subject

# Check all endpoints
for host in gateway api auth devops portal vault awx; do
  echo "=== ${host}.gostoa.dev ==="
  echo | openssl s_client -servername ${host}.gostoa.dev \
    -connect ${host}.gostoa.dev:443 2>/dev/null | \
    openssl x509 -noout -enddate
done

# Check K8s Certificates
kubectl get certificates -A -o wide
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate if expired | Slack `#ops-alerts` |
| L2 | Platform Team | If renewal fails | Slack `#platform-team` |
| L3 | Security Team | Potential compromise | @security-team |

---

## 6. Prevention

### Daily Check Script

```bash
#!/bin/bash
# check-certificates.sh

DOMAINS=(
  "gateway.gostoa.dev"
  "api.gostoa.dev"
  "auth.gostoa.dev"
  "console.gostoa.dev"
  "portal.gostoa.dev"
  "vault.gostoa.dev"
  "awx.gostoa.dev"
)

WARNING_DAYS=30
CRITICAL_DAYS=7

for domain in "${DOMAINS[@]}"; do
  expiry=$(echo | openssl s_client -servername $domain \
    -connect $domain:443 2>/dev/null | \
    openssl x509 -noout -enddate | cut -d= -f2)

  expiry_epoch=$(date -d "$expiry" +%s)
  now_epoch=$(date +%s)
  days_left=$(( (expiry_epoch - now_epoch) / 86400 ))

  if [ $days_left -le $CRITICAL_DAYS ]; then
    echo "CRITICAL: $domain expires in $days_left days"
  elif [ $days_left -le $WARNING_DAYS ]; then
    echo "WARNING: $domain expires in $days_left days"
  else
    echo "OK: $domain expires in $days_left days"
  fi
done
```

### Prometheus Monitoring

```yaml
groups:
  - name: certificates
    rules:
      - alert: CertificateExpiringSoon
        expr: certmanager_certificate_expiration_timestamp_seconds - time() < 30*24*60*60
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "Certificate {{ $labels.name }} expires in less than 30 days"

      - alert: CertificateExpiryCritical
        expr: certmanager_certificate_expiration_timestamp_seconds - time() < 7*24*60*60
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "Certificate {{ $labels.name }} expires in less than 7 days"

      - alert: CertManagerNotReady
        expr: certmanager_controller_sync_call_count == 0
        for: 10m
        labels:
          severity: warning
```

### Best Practices

1. **Configure cert-manager** with auto-renewal
2. **Alert at 30 days** before expiration
3. **Test renewal** in pre-prod
4. **Document manual certificates** if any exist
5. **Regular rotation** of internal certificates

---

## 7. References

- [cert-manager Documentation](https://cert-manager.io/docs/)
- [Let's Encrypt Rate Limits](https://letsencrypt.org/docs/rate-limits/)
- [Troubleshooting cert-manager](https://cert-manager.io/docs/faq/troubleshooting/)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2024-12-28 | Platform Team | Initial creation |
