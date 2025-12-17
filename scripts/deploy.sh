#!/bin/bash
# Deploy script for APIM infrastructure

set -e

ENVIRONMENT=${1:-dev}
COMPONENT=${2:-all}

echo "🚀 Deploying APIM ${COMPONENT} to ${ENVIRONMENT}"

case $COMPONENT in
  terraform)
    echo "📦 Deploying Terraform infrastructure..."
    cd terraform/environments/${ENVIRONMENT}
    terraform init
    terraform plan -out=tfplan
    terraform apply tfplan
    ;;

  ansible)
    echo "🔧 Running Ansible playbooks..."
    cd ansible
    ansible-playbook -i inventory/${ENVIRONMENT}.ini playbooks/site.yml
    ;;

  control-plane)
    echo "🐳 Deploying Control Plane API..."
    cd control-plane-api
    ./deploy.sh ${ENVIRONMENT}
    ;;

  all)
    echo "📦 Deploying all components..."
    $0 ${ENVIRONMENT} terraform
    $0 ${ENVIRONMENT} ansible
    $0 ${ENVIRONMENT} control-plane
    ;;

  *)
    echo "Unknown component: ${COMPONENT}"
    echo "Usage: $0 <environment> <terraform|ansible|control-plane|all>"
    exit 1
    ;;
esac

echo "✅ Deployment completed successfully!"
