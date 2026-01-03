# Runbook: Database - Connection Issues

> **Severity**: Critical
> **Last updated**: 2024-12-28
> **Owner**: Platform Team
> **Linear Issue**: CAB-107

---

## 1. Symptoms

### Prometheus/Grafana Alerts

| Alert | Threshold | Dashboard |
|-------|-----------|-----------|
| `PostgresDown` | `pg_up == 0` | [RDS Dashboard](https://grafana.dev.stoa.cab-i.com/d/rds) |
| `PostgresConnectionsHigh` | `pg_stat_activity_count > 80% max` | [RDS Dashboard](https://grafana.dev.stoa.cab-i.com/d/rds) |
| `KeycloakDBError` | Keycloak logs "connection refused" | [Keycloak Dashboard](https://grafana.dev.stoa.cab-i.com/d/keycloak) |

### Observed Behavior

- Keycloak no longer responds (depends on PostgreSQL)
- "Connection refused" or "too many connections" errors
- Applications in CrashLoopBackOff with DB error
- Timeouts on OIDC authentications

### Business Impact

| Impact | Description |
|--------|-------------|
| **Users** | Authentication impossible |
| **APIs** | All protected APIs inaccessible |
| **SLA** | Critical SLA violation |

---

## 2. Quick Diagnosis (< 5 min)

### Initial Checklist

```bash
# 1. Check RDS status via AWS CLI
aws rds describe-db-instances \
  --db-instance-identifier stoa-dev-keycloak \
  --query 'DBInstances[0].[DBInstanceStatus,Endpoint.Address]' \
  --output table

# 2. Test connectivity from a pod
kubectl run pg-test --rm -it --restart=Never \
  --image=postgres:15 -n stoa-system -- \
  pg_isready -h <RDS_ENDPOINT> -p 5432

# 3. Check Keycloak logs
kubectl logs -n keycloak deploy/keycloak --tail=50 | grep -i "database\|connection\|postgres"

# 4. Check dependent pods
kubectl get pods -n keycloak
kubectl get pods -n stoa-system | grep -E "control-plane|awx"

# 5. Check connection secrets
kubectl get secret -n keycloak keycloak-db-secret -o jsonpath='{.data.password}' | base64 -d
```

### Verification Points

- [ ] RDS instance running?
- [ ] Security Group allows traffic?
- [ ] Credentials correct?
- [ ] Number of connections < max_connections?
- [ ] RDS disk space sufficient?
- [ ] RDS CPU/Memory OK?

### Common Causes

| Cause | Probability | Verification |
|-------|-------------|--------------|
| Max connections reached | High | `SELECT count(*) FROM pg_stat_activity;` |
| Misconfigured Security Group | Medium | AWS Console > Security Groups |
| RDS maintenance in progress | Medium | AWS Console > RDS Events |
| Expired/changed credentials | Low | Check K8s secret vs RDS |
| Full storage | Low | CloudWatch FreeStorageSpace |

---

## 3. Resolution

### Immediate Action (mitigation)

```bash
# 1. Check if it's a max connections issue
kubectl run pg-admin --rm -it --restart=Never \
  --image=postgres:15 -n stoa-system -- \
  psql "host=<RDS_ENDPOINT> dbname=keycloak user=keycloak password=<PASSWORD>" \
  -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# 2. If too many connections, kill idle connections
kubectl run pg-admin --rm -it --restart=Never \
  --image=postgres:15 -n stoa-system -- \
  psql "host=<RDS_ENDPOINT> dbname=keycloak user=keycloak password=<PASSWORD>" \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'idle' AND query_start < NOW() - INTERVAL '10 minutes';"

# 3. Restart applications to release zombie connections
kubectl rollout restart deployment -n keycloak keycloak
```

### Resolution by Cause

#### Case 1: Max connections reached

```bash
# View active connections by application
kubectl run pg-admin --rm -it --restart=Never \
  --image=postgres:15 -n stoa-system -- \
  psql "host=<RDS_ENDPOINT> dbname=keycloak user=keycloak password=<PASSWORD>" \
  -c "SELECT application_name, count(*) FROM pg_stat_activity GROUP BY application_name ORDER BY count DESC;"

# Increase max_connections on RDS (requires reboot)
aws rds modify-db-parameter-group \
  --db-parameter-group-name stoa-postgres15 \
  --parameters "ParameterName=max_connections,ParameterValue=200,ApplyMethod=pending-reboot"

# Reboot RDS instance (WARNING: downtime)
aws rds reboot-db-instance --db-instance-identifier stoa-dev-keycloak

# Alternative: Reduce connection pool on application side
# In Keycloak, modify datasource to reduce pool-size
```

#### Case 2: Blocking Security Group

```bash
# List Security Groups for RDS instance
aws rds describe-db-instances \
  --db-instance-identifier stoa-dev-keycloak \
  --query 'DBInstances[0].VpcSecurityGroups[*].VpcSecurityGroupId' \
  --output text

# Check inbound rules
aws ec2 describe-security-groups \
  --group-ids <SG_ID> \
  --query 'SecurityGroups[0].IpPermissions'

# Add rule for EKS cluster CIDR
aws ec2 authorize-security-group-ingress \
  --group-id <SG_ID> \
  --protocol tcp \
  --port 5432 \
  --cidr <EKS_VPC_CIDR>
```

#### Case 3: Incorrect credentials

```bash
# Retrieve current password from Secrets Manager
aws secretsmanager get-secret-value \
  --secret-id stoa-dev-rds-password \
  --query SecretString --output text

# Update Kubernetes secret
kubectl create secret generic keycloak-db-secret -n keycloak \
  --from-literal=username=keycloak \
  --from-literal=password='<NEW_PASSWORD>' \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart Keycloak to pick up new secret
kubectl rollout restart deployment -n keycloak keycloak
```

#### Case 4: Full RDS storage

```bash
# Check available space
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name FreeStorageSpace \
  --dimensions Name=DBInstanceIdentifier,Value=stoa-dev-keycloak \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 300 \
  --statistics Average

# Increase storage (no downtime)
aws rds modify-db-instance \
  --db-instance-identifier stoa-dev-keycloak \
  --allocated-storage 50 \
  --apply-immediately
```

---

## 4. Post-Resolution Verification

### Validation Checklist

- [ ] RDS instance status = "available"
- [ ] Keycloak pod Ready
- [ ] Keycloak login works
- [ ] No DB errors in logs
- [ ] Normal connection count

### Verification Commands

```bash
# Test DB connection
kubectl run pg-test --rm -it --restart=Never \
  --image=postgres:15 -n stoa-system -- \
  pg_isready -h <RDS_ENDPOINT> -p 5432

# Test Keycloak
curl -s https://auth.dev.stoa.cab-i.com/realms/stoa/.well-known/openid-configuration | jq .issuer

# Check connection metrics
kubectl run pg-admin --rm -it --restart=Never \
  --image=postgres:15 -n stoa-system -- \
  psql "host=<RDS_ENDPOINT> dbname=keycloak user=keycloak password=<PASSWORD>" \
  -c "SELECT count(*) as active_connections FROM pg_stat_activity;"
```

---

## 5. Escalation Path

| Level | Who | When | Contact |
|-------|-----|------|---------|
| L1 | On-call DevOps | Immediate | Slack `#ops-alerts` |
| L2 | Platform Team + DBA | If issue persists | Slack `#platform-team` |
| L3 | AWS Support | RDS infrastructure issue | AWS Support Case |

---

## 6. Prevention

### Recommended Monitoring

```yaml
# CloudWatch Alerts
- MetricName: DatabaseConnections
  Threshold: 80% of max_connections
  AlarmAction: SNS -> Slack

- MetricName: FreeStorageSpace
  Threshold: < 5GB
  AlarmAction: SNS -> Slack

- MetricName: CPUUtilization
  Threshold: > 80%
  AlarmAction: SNS -> Slack
```

### Best Practices

1. **Configure connection pooling** (PgBouncer if needed)
2. **Size max_connections** according to number of applications
3. **Enable automatic RDS backups**
4. **Monitor slow queries** via Performance Insights
5. **Configure CloudWatch alerts** before saturation

---

## 7. References

### Documentation

- [AWS RDS Troubleshooting](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Troubleshooting.html)
- [Keycloak Database Configuration](https://www.keycloak.org/server/db)

### Dashboards

- [RDS Dashboard](https://grafana.dev.stoa.cab-i.com/d/rds)
- [AWS RDS Console](https://eu-west-1.console.aws.amazon.com/rds/home?region=eu-west-1#databases:)

---

## Modification History

| Date | Author | Modification |
|------|--------|--------------|
| 2024-12-28 | Platform Team | Initial creation |
