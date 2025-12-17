#!/bin/bash
# Stop all DEV instances for cost optimization

set -e

ENVIRONMENT=${1:-dev}
AWS_REGION=${2:-eu-west-1}

echo "🛑 Stopping all ${ENVIRONMENT} instances..."

# Get all running instances with Environment=dev tag
INSTANCE_IDS=$(aws ec2 describe-instances \
  --filters "Name=tag:Environment,Values=${ENVIRONMENT}" "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].InstanceId' \
  --output text \
  --region ${AWS_REGION})

if [ -z "$INSTANCE_IDS" ]; then
  echo "No running instances found"
  exit 0
fi

echo "Found instances: ${INSTANCE_IDS}"
aws ec2 stop-instances --instance-ids ${INSTANCE_IDS} --region ${AWS_REGION}

echo "✅ Instances stopped successfully!"
echo "Note: ECS Control Plane will continue running on Fargate"
