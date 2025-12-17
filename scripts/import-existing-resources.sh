#!/bin/bash
# Script to import existing AWS resources into Terraform state

set -e

cd terraform/environments/dev

echo "🔄 Importing existing AWS resources into Terraform state..."

# Import S3 buckets
echo "📦 Importing S3 buckets..."
terraform import aws_s3_bucket.artifacts apim-artifacts-dev || true
terraform import aws_s3_bucket.backups apim-backups-dev || true
terraform import aws_s3_bucket.vault_storage apim-vault-storage-dev || true

# Import S3 bucket versioning
terraform import aws_s3_bucket_versioning.artifacts apim-artifacts-dev || true
terraform import aws_s3_bucket_versioning.backups apim-backups-dev || true
terraform import aws_s3_bucket_versioning.vault_storage apim-vault-storage-dev || true

# Import S3 lifecycle configuration
terraform import aws_s3_bucket_lifecycle_configuration.backups apim-backups-dev || true

# Import IAM roles
echo "👤 Importing IAM roles..."
terraform import module.iam.aws_iam_role.webmethods apim-webmethods-role-dev || true
terraform import module.iam.aws_iam_role.portal apim-portal-role-dev || true
terraform import module.iam.aws_iam_role.jenkins apim-jenkins-role-dev || true
terraform import module.iam.aws_iam_role.vault apim-vault-role-dev || true

# Get IAM policy ARNs
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Import IAM policies
echo "📋 Importing IAM policies..."
terraform import module.iam.aws_iam_policy.ssm_access arn:aws:iam::${ACCOUNT_ID}:policy/apim-ssm-access-dev || true
terraform import module.iam.aws_iam_policy.cloudwatch_logs arn:aws:iam::${ACCOUNT_ID}:policy/apim-cloudwatch-logs-dev || true
terraform import module.iam.aws_iam_policy.s3_access arn:aws:iam::${ACCOUNT_ID}:policy/apim-s3-access-dev || true
terraform import module.iam.aws_iam_policy.vault_s3_kms arn:aws:iam::${ACCOUNT_ID}:policy/apim-vault-s3-kms-dev || true
terraform import module.iam.aws_iam_policy.jenkins_admin arn:aws:iam::${ACCOUNT_ID}:policy/apim-jenkins-admin-dev || true

# Import IAM instance profiles
echo "🔐 Importing IAM instance profiles..."
terraform import module.iam.aws_iam_instance_profile.webmethods apim-webmethods-role-dev || true
terraform import module.iam.aws_iam_instance_profile.portal apim-portal-role-dev || true
terraform import module.iam.aws_iam_instance_profile.jenkins apim-jenkins-role-dev || true
terraform import module.iam.aws_iam_instance_profile.vault apim-vault-role-dev || true

echo "✅ Import completed!"
echo ""
echo "Now run: terraform apply"
