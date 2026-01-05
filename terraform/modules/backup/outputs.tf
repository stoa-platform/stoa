# =============================================================================
# Backup Module Outputs
# =============================================================================
# STOA Platform - Phase 9.5 Production Readiness
# =============================================================================

# -----------------------------------------------------------------------------
# S3 Bucket
# -----------------------------------------------------------------------------

output "bucket_name" {
  description = "Name of the S3 backup bucket"
  value       = aws_s3_bucket.backup.id
}

output "bucket_arn" {
  description = "ARN of the S3 backup bucket"
  value       = aws_s3_bucket.backup.arn
}

output "bucket_domain_name" {
  description = "Domain name of the S3 backup bucket"
  value       = aws_s3_bucket.backup.bucket_domain_name
}

output "bucket_regional_domain_name" {
  description = "Regional domain name of the S3 backup bucket"
  value       = aws_s3_bucket.backup.bucket_regional_domain_name
}

# -----------------------------------------------------------------------------
# KMS Key
# -----------------------------------------------------------------------------

output "kms_key_id" {
  description = "ID of the KMS key for backup encryption"
  value       = aws_kms_key.backup.key_id
}

output "kms_key_arn" {
  description = "ARN of the KMS key for backup encryption"
  value       = aws_kms_key.backup.arn
}

output "kms_key_alias" {
  description = "Alias of the KMS key for backup encryption"
  value       = aws_kms_alias.backup.name
}

# -----------------------------------------------------------------------------
# IAM Role
# -----------------------------------------------------------------------------

output "backup_role_arn" {
  description = "ARN of the IAM role for backup jobs"
  value       = aws_iam_role.backup.arn
}

output "backup_role_name" {
  description = "Name of the IAM role for backup jobs"
  value       = aws_iam_role.backup.name
}

# -----------------------------------------------------------------------------
# SNS Topic
# -----------------------------------------------------------------------------

output "sns_topic_arn" {
  description = "ARN of the SNS topic for backup notifications"
  value       = var.enable_sns_notifications ? aws_sns_topic.backup_notifications[0].arn : null
}

# -----------------------------------------------------------------------------
# Configuration for Kubernetes CronJobs
# -----------------------------------------------------------------------------

output "kubernetes_config" {
  description = "Configuration values for Kubernetes backup CronJobs"
  value = {
    service_account_annotations = {
      "eks.amazonaws.com/role-arn" = aws_iam_role.backup.arn
    }
    environment_variables = {
      AWS_REGION          = var.aws_region
      S3_BUCKET           = aws_s3_bucket.backup.id
      KMS_KEY_ID          = aws_kms_key.backup.key_id
      KMS_KEY_ALIAS       = aws_kms_alias.backup.name
      SNS_TOPIC_ARN       = var.enable_sns_notifications ? aws_sns_topic.backup_notifications[0].arn : ""
    }
    s3_paths = {
      awx   = "s3://${aws_s3_bucket.backup.id}/awx/"
      vault = "s3://${aws_s3_bucket.backup.id}/vault/"
    }
  }
}
