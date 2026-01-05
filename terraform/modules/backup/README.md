# STOA Backup Module

> **Phase**: 9.5 - Production Readiness
> **Component**: Backup Infrastructure

This Terraform module creates the AWS infrastructure required for automated backups of STOA platform components (AWX, Vault).

## Features

- **S3 Bucket** with versioning and lifecycle policies
- **KMS Key** for server-side encryption
- **IAM Role** with IRSA support for Kubernetes workloads
- **SNS Topic** for backup notifications (optional)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        EKS Cluster                               │
│  ┌─────────────────┐    ┌─────────────────┐                     │
│  │ AWX Backup      │    │ Vault Backup    │                     │
│  │ CronJob         │    │ CronJob         │                     │
│  │ (stoa-backup SA)│    │ (stoa-backup SA)│                     │
│  └────────┬────────┘    └────────┬────────┘                     │
│           │                      │                               │
│           └──────────┬───────────┘                               │
│                      │ IRSA                                      │
└──────────────────────┼──────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                         AWS (eu-west-3)                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    IAM Role                                 │ │
│  │                 (stoa-backup-role)                          │ │
│  └─────────────────────────┬───────────────────────────────────┘ │
│                            │                                     │
│         ┌──────────────────┼──────────────────┐                 │
│         ▼                  ▼                  ▼                 │
│  ┌────────────┐     ┌────────────┐     ┌────────────┐          │
│  │ S3 Bucket  │     │  KMS Key   │     │ SNS Topic  │          │
│  │  backups   │◄────│ encryption │     │   alerts   │          │
│  │            │     │            │     │            │          │
│  │ ├─ awx/    │     │            │     │            │          │
│  │ └─ vault/  │     │            │     │            │          │
│  └────────────┘     └────────────┘     └────────────┘          │
└──────────────────────────────────────────────────────────────────┘
```

## Usage

```hcl
module "backup" {
  source = "../modules/backup"

  environment           = "dev"
  project_name          = "stoa"
  aws_region            = "eu-west-3"
  eks_cluster_name      = "stoa-dev"
  eks_oidc_provider_arn = module.eks.oidc_provider_arn

  lifecycle_rules = {
    awx_retention_days   = 30
    vault_retention_days = 90
    glacier_transition   = true
    glacier_days         = 60
  }

  enable_sns_notifications = true
  notification_email       = "ops@example.com"

  tags = {
    Team = "Platform"
  }
}
```

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| `environment` | Environment name (dev, staging, prod) | `string` | - | yes |
| `project_name` | Project name for resource naming | `string` | `"stoa"` | no |
| `aws_region` | AWS region for backup resources | `string` | `"eu-west-3"` | no |
| `eks_cluster_name` | EKS cluster name for IRSA | `string` | - | yes |
| `eks_oidc_provider_arn` | EKS OIDC provider ARN for IRSA | `string` | - | yes |
| `backup_namespace` | Kubernetes namespace for backup jobs | `string` | `"stoa-system"` | no |
| `backup_service_account` | Kubernetes service account | `string` | `"stoa-backup"` | no |
| `lifecycle_rules` | S3 lifecycle configuration | `object` | See variables.tf | no |
| `enable_sns_notifications` | Enable SNS notifications | `bool` | `true` | no |
| `notification_email` | Email for notifications | `string` | `""` | no |

## Outputs

| Name | Description |
|------|-------------|
| `bucket_name` | Name of the S3 backup bucket |
| `bucket_arn` | ARN of the S3 backup bucket |
| `kms_key_id` | ID of the KMS encryption key |
| `kms_key_arn` | ARN of the KMS encryption key |
| `backup_role_arn` | ARN of the IAM role for IRSA |
| `kubernetes_config` | Configuration for Kubernetes CronJobs |

## S3 Bucket Structure

```
s3://stoa-backups-{env}-eu-west-3/
├── awx/
│   └── YYYY-MM-DD/
│       └── awx-backup-{timestamp}.sql.gz
└── vault/
    └── YYYY-MM-DD/
        └── vault-snapshot-{timestamp}.snap
```

## Lifecycle Policies

### AWX Backups
- Retention: 30 days (configurable)
- Previous versions: 7 days

### Vault Backups
- Retention: 90 days (configurable)
- Glacier transition: 60 days (optional)
- Previous versions: 14 days

## Security

- **Encryption**: All backups encrypted with KMS (SSE-KMS)
- **Access**: IRSA-based authentication (no long-lived credentials)
- **Public Access**: Blocked via bucket policy
- **Versioning**: Enabled for recovery from accidental deletion

## Integration with Kubernetes

The module outputs a `kubernetes_config` object that can be used to configure the backup CronJobs:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: stoa-backup
  namespace: stoa-system
  annotations:
    eks.amazonaws.com/role-arn: ${backup_role_arn}
```

## Notifications

When SNS notifications are enabled:
- Email notification on new backup upload
- Can be extended to Slack via AWS Chatbot

## Related Documentation

- [AWX Backup Runbook](../../docs/runbooks/critical/awx-restore.md)
- [Vault Backup Runbook](../../docs/runbooks/critical/vault-restore.md)
- [Backup CronJob Helm Templates](../../charts/stoa-platform/templates/backup-*.yaml)
