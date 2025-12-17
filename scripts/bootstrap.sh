#!/bin/bash
# Bootstrap script to initialize the APIM platform infrastructure

set -e

ENVIRONMENT=${1:-dev}
AWS_REGION=${2:-eu-west-1}

echo "🚀 Bootstrapping APIM platform for environment: ${ENVIRONMENT}"

# Create S3 bucket for Terraform state
echo "📦 Creating Terraform state S3 bucket..."
aws s3api create-bucket \
  --bucket apim-terraform-state-${ENVIRONMENT} \
  --region ${AWS_REGION} \
  --create-bucket-configuration LocationConstraint=${AWS_REGION} || echo "Bucket already exists"

aws s3api put-bucket-versioning \
  --bucket apim-terraform-state-${ENVIRONMENT} \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket apim-terraform-state-${ENVIRONMENT} \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Create DynamoDB table for Terraform locks
echo "🔒 Creating Terraform lock DynamoDB table..."
aws dynamodb create-table \
  --table-name apim-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ${AWS_REGION} || echo "Table already exists"

# Create ECR repository for Control Plane API
echo "🐳 Creating ECR repository..."
aws ecr create-repository \
  --repository-name apim-control-plane \
  --region ${AWS_REGION} || echo "Repository already exists"

echo "✅ Bootstrap completed successfully!"
echo ""
echo "Next steps:"
echo "1. cd terraform/environments/${ENVIRONMENT}"
echo "2. terraform init"
echo "3. terraform plan"
echo "4. terraform apply"
