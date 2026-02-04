---
sidebar_position: 4
title: Troubleshooting
description: Common issues and solutions.
---

# Troubleshooting

Common issues encountered when running STOA, with diagnosis steps and solutions.

## Installation & Deployment

### Pods Not Starting

**Symptom**: Pods stuck in `CrashLoopBackOff` or `Pending`.

**Diagnosis**:

```bash
kubectl describe pod <pod-name> -n stoa-system
kubectl logs <pod-name> -n stoa-system --previous
```

**Common causes**:

| Cause | Fix |
|-------|-----|
| Missing secrets | Create required secrets: `kubectl create secret generic stoa-db-credentials ...` |
| Insufficient resources | Increase node resources or reduce replica count |
| Image pull failure | Verify image exists and pull secret is configured |
| CRDs not applied | Run `kubectl apply -f charts/stoa-platform/crds/` |

### Helm Install Fails

**Symptom**: `helm upgrade --install` returns an error.

```bash
# Check Helm release status
helm status stoa-platform -n stoa-system

# View rendered templates
helm template stoa-platform ./charts/stoa-platform -f values.yaml

# Lint the chart
helm lint charts/stoa-platform
```

## Database

### Connection Refused

**Symptom**: `connection refused` or `could not connect to server` in API logs.

**Checklist**:

1. Verify database is running: `kubectl get pods -l app=postgresql`
2. Check connection string: `DATABASE_URL` must include correct host, port, credentials
3. Check network policies: ensure `stoa-system` namespace can reach the database
4. Check security groups (AWS): RDS must allow inbound from EKS nodes

### Migration Failures

**Symptom**: API starts but returns 500 errors on data operations.

```bash
cd control-plane-api
alembic upgrade head
alembic current  # Verify migration state
```

If migrations are stuck:

```bash
alembic stamp head  # Reset to current state (use cautiously)
```

## Authentication

### 401 Unauthorized on All Requests

**Checklist**:

1. Token expired? Re-authenticate: `stoa login --server ...`
2. Keycloak reachable? `curl https://auth.gostoa.dev/health`
3. Realm correct? Must be `stoa`
4. Client ID correct? `control-plane-ui` for Console, `stoa-portal` for Portal
5. Clock skew? Ensure server and client clocks are synchronized

### CORS Errors During Login

**Symptom**: Browser console shows CORS errors when redirecting to/from Keycloak.

**Fix**: In Keycloak admin:

1. Open the client configuration (`control-plane-ui` or `stoa-portal`)
2. Add the application URL to **Web Origins** (e.g., `https://console.gostoa.dev`)
3. Add to **Valid Redirect URIs** (e.g., `https://console.gostoa.dev/*`)

### Token Missing Scopes

**Symptom**: 403 Forbidden despite being authenticated.

**Fix**: Ensure the user belongs to the correct Keycloak group:

| Role | Group | Scopes |
|------|-------|--------|
| Platform admin | `cpi-admin` | `stoa:admin`, `stoa:write`, `stoa:read` |
| Tenant admin | `tenant-admin` | `stoa:write`, `stoa:read` |
| DevOps | `devops` | `stoa:write`, `stoa:read` |
| Viewer | `viewer` | `stoa:read` |

## MCP Gateway

### Tools Not Appearing

**Symptom**: `tools/list` returns empty array.

**Checklist**:

1. CRDs applied? `kubectl get crds | grep gostoa.dev`
2. Tools created? `kubectl get tools -A`
3. Watcher enabled? Set `K8S_WATCHER_ENABLED=true`
4. Correct namespace? Tools must be in `tenant-{name}` namespaces
5. Gateway restarted after CRD changes? (if watcher is disabled)

### OPA Policy Denying All Requests

**Symptom**: All `tools/call` requests return 403.

```bash
# Check OPA is enabled and configured
kubectl logs -l app=mcp-gateway -n stoa-system | grep opa

# Verify policy files are mounted
kubectl exec -it <mcp-gateway-pod> -n stoa-system -- ls /policies/
```

Verify your Rego policy has a path to `allow = true` for your use case.

### Kafka Metering Errors

**Symptom**: MCP Gateway logs show Kafka connection errors.

**Checklist**:

1. Kafka/Redpanda running? `kubectl get pods -l app=redpanda`
2. Bootstrap servers correct? Check `KAFKA_BOOTSTRAP_SERVERS`
3. Topic exists? `kubectl exec redpanda-0 -- rpk topic list`
4. Network policies allow traffic? Check cross-namespace rules

## Portal

### APIs Not Showing in Catalog

**Symptom**: Portal loads but catalog is empty.

**Checklist**:

1. APIs published? Check in Console UI or via API
2. Portal visibility enabled? API must have `portal.visible: true`
3. API endpoint returns data? `curl https://api.gostoa.dev/v1/portal/apis`
4. Auth working? Portal needs valid token to fetch catalog

### Search Returns 500

**Symptom**: Searching in Portal returns HTTP 500.

This was a known issue (CAB-1044) caused by unescaped LIKE wildcards. Ensure you're running a version with the fix (commit `2c5672d8` or later).

## Gateway Sync

### API Not Synced to Gateway

**Symptom**: API shows as "Published" in Console but not reachable on the gateway.

**Checklist**:

1. GitLab sync working? Check ArgoCD for sync status
2. AWX job ran? Check AWX job history
3. Gateway adapter connected? Check adapter health in AWX logs
4. Gateway credentials valid? Verify `WM_GATEWAY_URL`, `WM_ADMIN_USER`, `WM_ADMIN_PASSWORD`

### Drift Detected

**Symptom**: Console shows "Drift" status for an API.

Drift means the gateway state differs from the desired state in Git. Trigger a reconciliation:

```bash
# Via AWX
awx job_templates launch --id <reconciliation-template-id>

# Or via Ansible directly
ansible-playbook playbooks/reconcile.yml -e "tenant=acme"
```

## Vault

### Vault Sealed

**Symptom**: Application returns errors related to Vault, logs show `VaultSealedException`.

**Fix**: Unseal Vault using the unseal keys:

```bash
vault operator unseal <key1>
vault operator unseal <key2>
vault operator unseal <key3>
```

This was addressed in CAB-1042 with automatic sealed detection (`_ensure_unsealed()`).

## Performance

### High API Latency

1. Check database query times: Grafana → Control Plane API dashboard
2. Check Kafka consumer lag: `kubectl exec redpanda-0 -- rpk group describe stoa-events`
3. Check pod resource usage: `kubectl top pods -n stoa-system`
4. Review slow query logs: Loki → `{app="control-plane-api"} | json | duration > 1s`

### High Memory Usage

1. Check for connection pool leaks: Monitor `DB_POOL_SIZE` usage in Prometheus
2. Review Kafka consumer configuration: Reduce batch sizes if needed
3. Check for large API specifications being loaded into memory
