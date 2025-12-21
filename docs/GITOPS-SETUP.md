# GitOps Setup Guide

## Overview

The APIM Platform uses GitLab as the source of truth for API definitions and configurations.
This guide explains how to configure GitLab SaaS (gitlab.com) for GitOps deployments.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌─────────────┐
│   GitLab    │────▶│ Control-Plane│────▶│   Kafka     │────▶│    AWX      │
│   (SaaS)    │     │     API      │     │ (Redpanda)  │     │  (Ansible)  │
└─────────────┘     └──────────────┘     └─────────────┘     └─────────────┘
                                                                    │
                                                                    ▼
                                                             ┌─────────────┐
                                                             │  webMethods │
                                                             │   Gateway   │
                                                             └─────────────┘
```

## GitLab Repository Structure

```
apim-gitops/
├── tenants/
│   ├── tenant-a/
│   │   ├── tenant.yaml           # Tenant configuration
│   │   ├── apis/
│   │   │   ├── petstore-api/
│   │   │   │   ├── api.yaml      # API metadata
│   │   │   │   ├── openapi.yaml  # OpenAPI specification
│   │   │   │   └── policies/     # Gateway policies
│   │   │   └── payment-api/
│   │   │       └── ...
│   │   └── applications/
│   │       └── mobile-app/
│   │           └── app.yaml
│   └── tenant-b/
│       └── ...
└── README.md
```

## Setup Instructions

### 1. Create GitLab Project

1. Go to [gitlab.com](https://gitlab.com) and create a new project
2. Name it `apim-gitops` (or your preferred name)
3. Make it **private** (recommended for API definitions)

### 2. Generate Access Token

1. Go to **Settings → Access Tokens**
2. Create a new token with these scopes:
   - `api` (Full API access)
   - `read_repository`
   - `write_repository`
3. Copy the token and save it securely

### 3. Get Project ID

1. Go to your project's main page
2. Find the **Project ID** under the project name (e.g., `12345678`)

### 4. Configure Webhook

1. Go to **Settings → Webhooks**
2. Add a new webhook:
   - **URL**: `https://api.dev.apim.cab-i.com/webhooks/gitlab`
   - **Secret Token**: Generate a secure random token (e.g., `openssl rand -hex 32`)
   - **Trigger events**:
     - ✅ Push events
     - ✅ Merge request events
     - ✅ Tag push events
   - **SSL verification**: Enable

### 5. Configure Control-Plane API

Add these environment variables to the Control-Plane API deployment:

```yaml
env:
  - name: GITLAB_URL
    value: "https://gitlab.com"
  - name: GITLAB_TOKEN
    valueFrom:
      secretKeyRef:
        name: gitlab-secrets
        key: token
  - name: GITLAB_PROJECT_ID
    value: "YOUR_PROJECT_ID"
  - name: GITLAB_WEBHOOK_SECRET
    valueFrom:
      secretKeyRef:
        name: gitlab-secrets
        key: webhook-secret
```

Create the Kubernetes secret:

```bash
kubectl create secret generic gitlab-secrets -n apim-system \
  --from-literal=token=glpat-xxxxx \
  --from-literal=webhook-secret=your-webhook-secret
```

## GitOps Workflow

### Deploying an API

1. **Create API in GitLab**:
   ```yaml
   # tenants/acme/apis/petstore/api.yaml
   name: petstore
   version: "1.0.0"
   description: Pet Store API
   backend_url: https://petstore.example.com
   status: draft
   ```

2. **Add OpenAPI Spec**:
   ```yaml
   # tenants/acme/apis/petstore/openapi.yaml
   openapi: "3.0.3"
   info:
     title: Petstore API
     version: "1.0.0"
   paths:
     /pets:
       get:
         summary: List all pets
         # ...
   ```

3. **Commit and Push**:
   ```bash
   git add .
   git commit -m "Add Petstore API for tenant acme"
   git push origin main
   ```

4. **Automatic Deployment**:
   - GitLab webhook triggers Control-Plane API
   - Event published to Kafka (`deploy-requests` topic)
   - Deployment Worker consumes event
   - AWX job launched to deploy API to Gateway

### Monitoring Deployments

Check deployment status in Kafka:
```bash
kubectl exec -it redpanda-0 -n apim-system -- \
  rpk topic consume deploy-results --brokers localhost:9092
```

Check AWX job status:
```bash
# Get AWX admin password
kubectl get secret awx-admin-password -n apim-system -o jsonpath='{.data.password}' | base64 -d

# Access AWX UI
kubectl port-forward svc/awx-web -n apim-system 8052:80
# Open http://localhost:8052
```

## Troubleshooting

### Webhook not working

1. Check webhook delivery status in GitLab (Settings → Webhooks → Edit → Recent Deliveries)
2. Verify the Control-Plane API is accessible from the internet
3. Check webhook secret matches

### Deployment not triggered

1. Check Kafka topic has the event:
   ```bash
   kubectl exec -it redpanda-0 -n apim-system -- \
     rpk topic consume deploy-requests --brokers localhost:9092 --offset start
   ```

2. Check Control-Plane API logs:
   ```bash
   kubectl logs -l app=control-plane-api -n apim-system -f
   ```

3. Check AWX job logs in the AWX UI

### AWX job failing

1. Check the playbook exists in the AWX project
2. Verify Gateway credentials are correct
3. Check Gateway is accessible from the Ansible pod
