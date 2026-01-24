# STOA Platform Installation Guide

This guide covers production deployment of STOA Platform on Kubernetes.

## Prerequisites

### Infrastructure Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Kubernetes | 1.25+ | 1.28+ |
| Nodes | 3 | 5+ |
| CPU per node | 4 cores | 8 cores |
| Memory per node | 8 GB | 16 GB |
| Storage | 100 GB | 500 GB SSD |

### Required Tools

- `kubectl` v1.25+
- `helm` v3.12+
- `terraform` v1.5+ (for infrastructure provisioning)

### External Dependencies

- **Keycloak** - Identity Provider (OIDC)
- **PostgreSQL** - Database (RDS or self-hosted)
- **Kafka/Redpanda** - Event streaming
- **GitLab** - GitOps source of truth
- **Vault** (optional) - Secrets management

## Installation Steps

### 1. Provision Infrastructure (Optional)

If using AWS EKS:

```bash
cd terraform/environments/dev
terraform init
terraform plan
terraform apply
```

### 2. Configure Kubernetes Access

```bash
# For EKS
aws eks update-kubeconfig --name stoa-cluster --region us-west-2

# Verify access
kubectl get nodes
```

### 3. Create Namespace

```bash
kubectl create namespace stoa-system
```

### 4. Apply Custom Resource Definitions

```bash
kubectl apply -f charts/stoa-platform/crds/
```

### 5. Configure Values

Create a `values.yaml` file with your configuration:

```yaml
global:
  baseDomain: gostoa.dev

controlPlaneApi:
  replicas: 2
  database:
    host: control-plane-db.stoa-system.svc.cluster.local
    port: 5432
    name: stoa

keycloak:
  url: https://auth.gostoa.dev
  realm: stoa

kafka:
  bootstrapServers: redpanda.stoa-system.svc.cluster.local:9092
```

### 6. Deploy with Helm

```bash
helm upgrade --install stoa-platform ./charts/stoa-platform \
  -n stoa-system \
  -f values.yaml
```

### 7. Verify Deployment

```bash
# Check pods
kubectl get pods -n stoa-system

# Check services
kubectl get svc -n stoa-system

# Check ingress
kubectl get ingress -n stoa-system
```

## Post-Installation

### Configure DNS

Point your domain records to the load balancer:

| Record | Type | Value |
|--------|------|-------|
| console.gostoa.dev | CNAME | <alb-hostname> |
| portal.gostoa.dev | CNAME | <alb-hostname> |
| api.gostoa.dev | CNAME | <alb-hostname> |
| mcp.gostoa.dev | CNAME | <alb-hostname> |

### Configure Keycloak

1. Create the `stoa` realm
2. Configure client applications
3. Set up role mappings
4. Configure identity federation (optional)

### Initialize Demo Data (Optional)

```bash
kubectl apply -f deploy/demo-tenants/
kubectl apply -f deploy/demo-tools/
```

## Upgrading

```bash
# Pull latest charts
git pull origin main

# Upgrade deployment
helm upgrade stoa-platform ./charts/stoa-platform \
  -n stoa-system \
  -f values.yaml
```

## Uninstalling

```bash
# Remove Helm release
helm uninstall stoa-platform -n stoa-system

# Remove CRDs (optional - will delete all custom resources)
kubectl delete -f charts/stoa-platform/crds/

# Remove namespace
kubectl delete namespace stoa-system
```

## Troubleshooting

### Common Issues

1. **Pods not starting**: Check resource limits and node capacity
2. **Database connection failed**: Verify PostgreSQL connectivity and credentials
3. **Authentication errors**: Check Keycloak configuration and realm settings

### Useful Commands

```bash
# Check pod logs
kubectl logs -n stoa-system <pod-name>

# Describe pod for events
kubectl describe pod -n stoa-system <pod-name>

# Check secrets
kubectl get secrets -n stoa-system
```

See [Runbooks](./runbooks/) for detailed troubleshooting procedures.
