# =============================================================================
# Backup Module Variables
# =============================================================================
# STOA Platform - Phase 9.5 Production Readiness
# Backup infrastructure for AWX and Vault
# =============================================================================

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "stoa"
}

variable "aws_region" {
  description = "AWS region for backup resources"
  type        = string
  default     = "eu-west-3" # Paris
}

# -----------------------------------------------------------------------------
# S3 Configuration
# -----------------------------------------------------------------------------

variable "bucket_name_suffix" {
  description = "Suffix for S3 bucket name"
  type        = string
  default     = "backups"
}

variable "versioning_enabled" {
  description = "Enable S3 bucket versioning"
  type        = bool
  default     = true
}

variable "lifecycle_rules" {
  description = "S3 lifecycle rules configuration"
  type = object({
    awx_retention_days   = number
    vault_retention_days = number
    glacier_transition   = bool
    glacier_days         = number
  })
  default = {
    awx_retention_days   = 30
    vault_retention_days = 90
    glacier_transition   = true
    glacier_days         = 60
  }
}

# -----------------------------------------------------------------------------
# KMS Configuration
# -----------------------------------------------------------------------------

variable "kms_deletion_window_days" {
  description = "KMS key deletion window in days"
  type        = number
  default     = 30
}

variable "kms_enable_rotation" {
  description = "Enable automatic KMS key rotation"
  type        = bool
  default     = true
}

# -----------------------------------------------------------------------------
# IRSA Configuration
# -----------------------------------------------------------------------------

variable "eks_cluster_name" {
  description = "EKS cluster name for IRSA"
  type        = string
}

variable "eks_oidc_provider_arn" {
  description = "EKS OIDC provider ARN for IRSA"
  type        = string
}

variable "backup_namespace" {
  description = "Kubernetes namespace for backup jobs"
  type        = string
  default     = "stoa-system"
}

variable "backup_service_account" {
  description = "Kubernetes service account for backup jobs"
  type        = string
  default     = "stoa-backup"
}

# -----------------------------------------------------------------------------
# Notification Configuration
# -----------------------------------------------------------------------------

variable "enable_sns_notifications" {
  description = "Enable SNS notifications for backup events"
  type        = bool
  default     = true
}

variable "notification_email" {
  description = "Email for backup failure notifications"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Tags
# -----------------------------------------------------------------------------

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default     = {}
}
