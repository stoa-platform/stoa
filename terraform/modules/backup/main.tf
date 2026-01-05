# =============================================================================
# Backup Module - Main Configuration
# =============================================================================
# STOA Platform - Phase 9.5 Production Readiness
# Creates S3 bucket, KMS key, and IAM roles for backup operations
# =============================================================================

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

locals {
  bucket_name = "${var.project_name}-${var.bucket_name_suffix}-${var.environment}-${var.aws_region}"

  common_tags = merge(
    {
      Project     = var.project_name
      Environment = var.environment
      Component   = "backup"
      ManagedBy   = "terraform"
      Phase       = "9.5-production-readiness"
    },
    var.tags
  )
}

# =============================================================================
# KMS Key for Backup Encryption
# =============================================================================

resource "aws_kms_key" "backup" {
  description             = "KMS key for STOA backup encryption - ${var.environment}"
  deletion_window_in_days = var.kms_deletion_window_days
  enable_key_rotation     = var.kms_enable_rotation

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Enable IAM User Permissions"
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"
        }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "Allow Backup Role"
        Effect = "Allow"
        Principal = {
          AWS = aws_iam_role.backup.arn
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      },
      {
        Sid    = "Allow S3 Service"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:ReEncrypt*",
          "kms:GenerateDataKey*",
          "kms:DescribeKey"
        ]
        Resource = "*"
      }
    ]
  })

  tags = local.common_tags
}

resource "aws_kms_alias" "backup" {
  name          = "alias/${var.project_name}-backup-key-${var.environment}"
  target_key_id = aws_kms_key.backup.key_id
}

# =============================================================================
# S3 Bucket for Backups
# =============================================================================

resource "aws_s3_bucket" "backup" {
  bucket = local.bucket_name

  tags = local.common_tags
}

resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id

  versioning_configuration {
    status = var.versioning_enabled ? "Enabled" : "Disabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.backup.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "backup" {
  bucket = aws_s3_bucket.backup.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "backup" {
  bucket = aws_s3_bucket.backup.id

  # AWX backups - shorter retention
  rule {
    id     = "awx-backup-lifecycle"
    status = "Enabled"

    filter {
      prefix = "awx/"
    }

    expiration {
      days = var.lifecycle_rules.awx_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }

  # Vault backups - longer retention with Glacier transition
  rule {
    id     = "vault-backup-lifecycle"
    status = "Enabled"

    filter {
      prefix = "vault/"
    }

    dynamic "transition" {
      for_each = var.lifecycle_rules.glacier_transition ? [1] : []
      content {
        days          = var.lifecycle_rules.glacier_days
        storage_class = "GLACIER"
      }
    }

    expiration {
      days = var.lifecycle_rules.vault_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 14
    }
  }

  # Cleanup incomplete multipart uploads
  rule {
    id     = "cleanup-incomplete-uploads"
    status = "Enabled"

    filter {
      prefix = ""
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

# =============================================================================
# IAM Role for Backup Jobs (IRSA)
# =============================================================================

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "backup_assume_role" {
  statement {
    effect = "Allow"

    principals {
      type        = "Federated"
      identifiers = [var.eks_oidc_provider_arn]
    }

    actions = ["sts:AssumeRoleWithWebIdentity"]

    condition {
      test     = "StringEquals"
      variable = "${replace(var.eks_oidc_provider_arn, "/^arn:aws:iam::[0-9]+:oidc-provider\\//", "")}:sub"
      values   = ["system:serviceaccount:${var.backup_namespace}:${var.backup_service_account}"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(var.eks_oidc_provider_arn, "/^arn:aws:iam::[0-9]+:oidc-provider\\//", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "backup" {
  name               = "${var.project_name}-backup-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.backup_assume_role.json

  tags = local.common_tags
}

data "aws_iam_policy_document" "backup" {
  # S3 permissions
  statement {
    sid    = "S3BackupAccess"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketLocation"
    ]

    resources = [
      aws_s3_bucket.backup.arn,
      "${aws_s3_bucket.backup.arn}/*"
    ]
  }

  # KMS permissions
  statement {
    sid    = "KMSBackupAccess"
    effect = "Allow"

    actions = [
      "kms:Encrypt",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey"
    ]

    resources = [aws_kms_key.backup.arn]
  }

  # CloudWatch Logs for backup job logs
  statement {
    sid    = "CloudWatchLogsAccess"
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/eks/${var.eks_cluster_name}/backup:*"
    ]
  }
}

resource "aws_iam_role_policy" "backup" {
  name   = "${var.project_name}-backup-policy-${var.environment}"
  role   = aws_iam_role.backup.id
  policy = data.aws_iam_policy_document.backup.json
}

# =============================================================================
# SNS Topic for Backup Notifications (Optional)
# =============================================================================

resource "aws_sns_topic" "backup_notifications" {
  count = var.enable_sns_notifications ? 1 : 0

  name              = "${var.project_name}-backup-notifications-${var.environment}"
  kms_master_key_id = aws_kms_key.backup.id

  tags = local.common_tags
}

resource "aws_sns_topic_subscription" "backup_email" {
  count = var.enable_sns_notifications && var.notification_email != "" ? 1 : 0

  topic_arn = aws_sns_topic.backup_notifications[0].arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# =============================================================================
# S3 Event Notifications
# =============================================================================

resource "aws_s3_bucket_notification" "backup" {
  count  = var.enable_sns_notifications ? 1 : 0
  bucket = aws_s3_bucket.backup.id

  topic {
    topic_arn     = aws_sns_topic.backup_notifications[0].arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "awx/"
    filter_suffix = ".gz"
  }

  topic {
    topic_arn     = aws_sns_topic.backup_notifications[0].arn
    events        = ["s3:ObjectCreated:*"]
    filter_prefix = "vault/"
    filter_suffix = ".snap"
  }
}

resource "aws_sns_topic_policy" "backup_notifications" {
  count = var.enable_sns_notifications ? 1 : 0

  arn = aws_sns_topic.backup_notifications[0].arn

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowS3Publish"
        Effect = "Allow"
        Principal = {
          Service = "s3.amazonaws.com"
        }
        Action   = "sns:Publish"
        Resource = aws_sns_topic.backup_notifications[0].arn
        Condition = {
          ArnLike = {
            "aws:SourceArn" = aws_s3_bucket.backup.arn
          }
        }
      }
    ]
  })
}
