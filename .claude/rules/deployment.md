---
description: Deployment, Helm, Terraform, and migration rules
globs: "charts/**,deploy/**,terraform/**,**/alembic/**"
---

# Deployment & Infrastructure

## Helm
```bash
helm lint charts/stoa-platform
helm upgrade --install stoa-platform ./charts/stoa-platform -n stoa-system --create-namespace
kubectl apply -f charts/stoa-platform/crds/
```

## Terraform
```bash
cd terraform/environments/dev
terraform init && terraform plan && terraform apply
```
Always `terraform plan` before `terraform apply`.

## Database Migrations (Alembic)
- Location: `control-plane-api/alembic/`
- Create: `alembic revision --autogenerate -m "description"`
- Apply: `alembic upgrade head`

## MCP Gateway CRDs
```bash
kubectl apply -f - <<EOF
apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: my-api-tool
  namespace: tenant-acme
spec:
  displayName: My API Tool
  description: A sample tool
  endpoint: https://api.example.com/v1/action
  method: POST
EOF
```

## Configuration
- `BASE_DOMAIN` is single source of truth for all URLs
- Environment configs: `deploy/config/{dev,staging,prod}.env`

## MCP Gateway Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `OPA_ENABLED` | `true` | OPA policy engine |
| `OPA_EMBEDDED` | `true` | Embedded evaluator |
| `METERING_ENABLED` | `true` | Kafka metering |
| `K8S_WATCHER_ENABLED` | `false` | CRD watcher |
