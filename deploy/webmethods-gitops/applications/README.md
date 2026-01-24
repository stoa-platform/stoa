# webMethods Gateway Applications

This directory contains GitOps definitions for webMethods API Gateway applications.

## Overview

Applications in webMethods Gateway represent OAuth2 clients that consume APIs. Each application
is identified by the `azp` (authorized party) claim in JWT tokens issued by Keycloak.

## Application Structure

```yaml
apiVersion: gostoa.dev/v1
kind: GatewayApplication
metadata:
  name: AppName
  description: "Description"
spec:
  clientId: keycloak-client-id    # Matches JWT 'azp' claim
  identifierClaim: azp            # JWT claim used for identification
  contactEmail: admin@example.com
  consumingAPIs:
    - API-Name-1
    - API-Name-2
  authStrategy: StrategyName      # OIDC strategy reference
  scopes:                         # Documentation only - enforced by backend
    - stoa:read
```

## Applications

| Application | Client ID | Purpose |
|-------------|-----------|---------|
| ConsoleApp | `control-plane-ui` | Admin Console for API providers |
| PortalApp | `stoa-portal` | Developer Portal for API consumers |

## GitOps Sync

These definitions are synced to the Gateway by the `reconcile-webmethods` Ansible playbook:

```bash
# Sync all (APIs + Applications)
ansible-playbook reconcile-webmethods.yml -e "env=dev"

# Sync only applications
ansible-playbook reconcile-webmethods.yml -e "env=dev" --tags applications
```

## Manual Creation

To create an application manually:

```bash
curl -X POST \
  -u Administrator:$GATEWAY_PASSWORD \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "https://gateway.gostoa.dev/rest/apigateway/applications" \
  -d '{
    "name": "AppName",
    "description": "Description",
    "contactEmails": ["admin@cab-i.com"],
    "identifiers": [{
      "key": "openIdClaims",
      "name": "azp",
      "value": ["keycloak-client-id"]
    }],
    "subscription": false
  }'
```
