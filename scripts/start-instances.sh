#!/bin/bash
# Start all DEV instances

set -e

ENVIRONMENT=${1:-dev}
AWS_REGION=${2:-eu-west-1}

echo "▶️ Starting all ${ENVIRONMENT} instances..."

# Get all stopped instances with Environment=dev tag
INSTANCE_IDS=$(aws ec2 describe-instances \
  --filters "Name=tag:Environment,Values=${ENVIRONMENT}" "Name=instance-state-name,Values=stopped" \
  --query 'Reservations[].Instances[].InstanceId' \
  --output text \
  --region ${AWS_REGION})

if [ -z "$INSTANCE_IDS" ]; then
  echo "No stopped instances found"
  exit 0
fi

echo "Found instances: ${INSTANCE_IDS}"
aws ec2 start-instances --instance-ids ${INSTANCE_IDS} --region ${AWS_REGION}

echo "✅ Instances started successfully!"
echo "Waiting for instances to be ready..."
aws ec2 wait instance-running --instance-ids ${INSTANCE_IDS} --region ${AWS_REGION}
echo "✅ All instances are now running!"
