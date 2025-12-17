#!/bin/bash
# Deploy Control Plane API to ECS

set -e

ENVIRONMENT=${1:-dev}
AWS_REGION=${2:-eu-west-1}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/apim-control-plane"

echo "🐳 Building Control Plane API..."
docker build -t apim-control-plane:latest .

echo "🏷️ Tagging image..."
docker tag apim-control-plane:latest ${ECR_REPO}:latest
docker tag apim-control-plane:latest ${ECR_REPO}:${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)

echo "🔐 Logging into ECR..."
aws ecr get-login-password --region ${AWS_REGION} | \
  docker login --username AWS --password-stdin ${ECR_REPO}

echo "⬆️ Pushing image to ECR..."
docker push ${ECR_REPO}:latest
docker push ${ECR_REPO}:${ENVIRONMENT}-$(date +%Y%m%d-%H%M%S)

echo "🔄 Updating ECS service..."
aws ecs update-service \
  --cluster apim-${ENVIRONMENT} \
  --service control-plane-api \
  --force-new-deployment \
  --region ${AWS_REGION}

echo "⏳ Waiting for deployment..."
aws ecs wait services-stable \
  --cluster apim-${ENVIRONMENT} \
  --services control-plane-api \
  --region ${AWS_REGION}

echo "✅ Deployment completed successfully!"
echo "🔍 Health check..."
sleep 10
curl -f https://api.apim-dev.votredomaine.com/health || echo "❌ Health check failed"
