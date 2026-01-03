# webMethods API Gateway REST API Reference

## Overview

This document provides essential REST API examples for IBM webMethods API Gateway configuration, focusing on alias management, API import, and routing configuration.

## Gateway Network Ports

The webMethods API Gateway exposes the following ports:

| Port | Protocol | Description | K8s Service Port |
|------|----------|-------------|------------------|
| **5555** | HTTP | Primary runtime port for API invocations | `runtime` |
| **5543** | HTTPS | Secure runtime port for API invocations (SSL) | `runtime-https` |
| **9072** | HTTPS | Administration UI port | `ui` |

### Port Configuration API

Retrieve port configuration via the admin API:

```bash
curl -s -u Administrator:manage \
  "http://localhost:5555/rest/apigateway/ports"
```

**Response contains:**
- `HTTPListener@5555`: Primary HTTP port (ssl: false)
- `HTTPSListener@5543`: Secure HTTPS port (ssl: true, keyStore: DEFAULT_IS_KEYSTORE)

### Kubernetes Ingress Configuration

For production, expose APIs via HTTPS using the 5543 port with backend SSL:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: apigateway-runtime
  namespace: stoa-system
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/backend-protocol: "HTTPS"
    nginx.ingress.kubernetes.io/proxy-ssl-verify: "false"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - apis.stoa.cab-i.com
    secretName: apigateway-runtime-tls
  rules:
  - host: apis.stoa.cab-i.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: apigateway
            port:
              number: 5543
```

### DNS Configuration

Create CNAME records pointing to the Load Balancer:

| DNS | Target | Purpose |
|-----|--------|---------|
| `gateway.stoa.cab-i.com` | `<elb-hostname>` | Admin UI (port 9072) |
| `apis.stoa.cab-i.com` | `<elb-hostname>` | API Runtime (port 5543) |

## Sources & Documentation

- [webMethods API Gateway GitHub](https://github.com/ibm-wm-transition/webmethods-api-gateway) - Official repository with samples
- [webMethods API Gateway DevOps](https://github.com/ibm-wm-transition/webmethods-api-gateway-devops) - CI/CD scripts and deployment
- [Alias Management API](https://developers.webmethods.io/portal/apis/df8e28c1-3ada-11ec-27c8-023039246947) - REST API reference
- [Official Documentation](https://docs.webmethods.io/apigateway/10.15.0/) - IBM webMethods docs

## Endpoint Alias Management

### Create Endpoint Alias

Creates an endpoint alias that can be referenced in API routing configuration.

```bash
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/alias" \
  -d '{
    "name": "MyBackendAlias",
    "description": "Backend endpoint for API",
    "type": "endpoint",
    "endPointURI": "http://backend-service.namespace.svc.cluster.local:8000",
    "connectionTimeout": "30",
    "readTimeout": "60",
    "optimizationTechnique": "None",
    "passSecurityHeaders": true
  }'
```

**Response:**
```json
{
  "alias": {
    "id": "2317ce04-3129-47f0-9c03-c96297bb92d1",
    "name": "MyBackendAlias",
    "description": "Backend endpoint for API",
    "type": "endpoint",
    "owner": "Administrator",
    "endPointURI": "http://backend-service.namespace.svc.cluster.local:8000",
    "connectionTimeout": 30,
    "readTimeout": 60,
    "suspendDurationOnFailure": 0,
    "optimizationTechnique": "None",
    "passSecurityHeaders": true,
    "isAssociated": false
  }
}
```

### List All Aliases

```bash
curl -s -X GET \
  -u Administrator:manage \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/alias"
```

### Get Alias by ID

```bash
curl -s -X GET \
  -u Administrator:manage \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/alias/{aliasId}"
```

### Update Alias

```bash
curl -s -X PUT \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/alias/{aliasId}" \
  -d '{
    "name": "MyBackendAlias",
    "description": "Updated description",
    "type": "endpoint",
    "endPointURI": "http://new-backend.namespace.svc.cluster.local:8000",
    "connectionTimeout": "60",
    "readTimeout": "120",
    "optimizationTechnique": "None",
    "passSecurityHeaders": true
  }'
```

### Delete Alias

```bash
curl -s -X DELETE \
  -u Administrator:manage \
  "http://localhost:5555/rest/apigateway/alias/{aliasId}"
```

## Alias Types

| Type | Description |
|------|-------------|
| `endpoint` | Backend service endpoint URL |
| `simple` | Simple key-value alias |
| `authServerAlias` | OAuth/OIDC authorization server |
| `serviceRegistryAlias` | Service discovery (Eureka, Consul) |

## Optimization Techniques

| Value | Description |
|-------|-------------|
| `None` | No optimization |
| `MTOM` | Message Transmission Optimization Mechanism |

## API Import via File Upload

### Import OpenAPI Spec

webMethods Gateway 10.15 supports OpenAPI 3.0.x (NOT 3.1.0). Convert specs before import.

```bash
# Convert OpenAPI 3.1.0 to 3.0.3
curl -s http://backend/openapi.json | \
  sed 's/"openapi":"3.1.0"/"openapi":"3.0.3"/' > /tmp/openapi30.json

# Import via multipart form
curl -s -X POST \
  -u Administrator:manage \
  -H "Accept: application/json" \
  -F "type=openapi" \
  -F "apiName=MyAPI" \
  -F "apiVersion=1.0" \
  -F "file=@/tmp/openapi30.json" \
  "http://localhost:5555/rest/apigateway/apis"
```

**Response:**
```json
{
  "apiResponse": {
    "api": {
      "id": "7ba67c90-814d-4d2f-a5da-36e9cda77afe",
      "apiName": "MyAPI",
      "apiVersion": "1.0",
      "isActive": false,
      ...
    }
  }
}
```

### Import via URL (requires internet access)

```bash
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/apis" \
  -d '{
    "apiName": "MyAPI",
    "apiVersion": "1.0",
    "type": "openapi",
    "url": "http://backend/openapi.json"
  }'
```

## API Routing Configuration

### Updating Routing via Policy Actions (Recommended Method)

The correct way to update API routing is through the Policy Actions embedded in the API object:

1. **GET the full API object:**
```bash
curl -s -u Administrator:manage \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/apis/{apiId}" > api.json
```

2. **Locate the policyAction/routing section in the response:**
The API response contains a `policyAction` object with routing configuration:
```json
{
  "apiResponse": {
    "api": {
      "id": "7ba67c90-814d-4d2f-a5da-36e9cda77afe",
      "apiName": "Control-Plane-API",
      ...
      "policyAction": {
        "routing": {
          "routeEndpoint": "${AliasName}/${sys:resource_path}"
        }
      }
    }
  }
}
```

3. **Modify the routeEndpoint value:**
Change the routing endpoint to use your alias:
```
${ControlPlaneBackend}/${sys:resource_path}
```

4. **PUT the entire API structure back:**
```bash
curl -s -X PUT \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/apis/{apiId}" \
  -d @api_updated.json
```

**Important Notes:**
- You MUST send the complete API object structure in the PUT request
- The `api` field in the PUT body should be a JSON string (escaped)
- The routing change is in `policyAction.routing.routeEndpoint`

### Routing Endpoint Format with Alias

To route API requests through an alias, use the format:
```
${AliasName}/${sys:resource_path}
```

Where:
- `${AliasName}` - References the endpoint alias by name
- `${sys:resource_path}` - Dynamic variable for the incoming request path

Example alias reference:
```
${ControlPlaneBackend}/${sys:resource_path}
```

### Direct Backend Endpoint (without alias)

For direct routing without using an alias:
```
http://backend-service.namespace.svc.cluster.local:8000/${sys:resource_path}
```

## Transport Policy - Enable HTTPS for APIs

By default, APIs are created with HTTP transport only (port 5555). To enable HTTPS access via port 5543, you must update the Transport Policy Action.

### Understanding Transport Policy

When an API is imported, it has an associated policy with transport enforcement:

```json
{
  "policyEnforcements": [
    {
      "stageKey": "transport",
      "enforcements": [{
        "enforcementObjectId": "<transport-policy-action-id>"
      }]
    }
  ]
}
```

### Step 1: Get the API's Policy

```bash
# Get the API to find its policy ID
curl -s -u Administrator:manage \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/apis/{apiId}" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d['apiResponse']['api']['policies'])"
```

### Step 2: Get the Transport Policy Action ID

```bash
# Get the policy details to find the transport policyAction ID
curl -s -u Administrator:manage \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/policies/{policyId}" | \
  python3 -c "import json,sys; d=json.load(sys.stdin);
for e in d['policy']['policyEnforcements']:
  if e['stageKey'] == 'transport':
    print(e['enforcements'][0]['enforcementObjectId'])"
```

### Step 3: Check Current Transport Configuration

```bash
curl -s -u Administrator:manage \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/policyActions/{policyActionId}"
```

**Default response (HTTP only):**
```json
{
  "policyAction": {
    "id": "d910f764-8615-462f-be11-1288413b65be",
    "names": [{"value": "Enable HTTP / HTTPS", "locale": "en"}],
    "templateKey": "entryProtocolPolicy",
    "parameters": [{
      "templateKey": "protocol",
      "values": ["http"]
    }],
    "active": false
  }
}
```

### Step 4: Enable HTTPS Transport

Update the policy action to include both HTTP and HTTPS:

```bash
curl -s -X PUT \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/policyActions/{policyActionId}" \
  -d '{
    "policyAction": {
      "id": "{policyActionId}",
      "names": [{"value": "Enable HTTP / HTTPS", "locale": "en"}],
      "templateKey": "entryProtocolPolicy",
      "parameters": [{
        "templateKey": "protocol",
        "values": ["http", "https"]
      }],
      "active": true
    }
  }'
```

**Response after update:**
```json
{
  "policyAction": {
    "parameters": [{
      "templateKey": "protocol",
      "values": ["http", "https"]
    }],
    "active": true
  }
}
```

### Step 5: Verify HTTPS Access

```bash
# Test via HTTPS port 5543
curl -sk "https://localhost:5543/gateway/MyAPI/1.0/health"
```

### Complete Mode Opératoire

Here's the complete procedure to enable HTTPS on a newly imported API:

```bash
#!/bin/bash
API_ID="7ba67c90-814d-4d2f-a5da-36e9cda77afe"
GW_URL="http://localhost:5555"
GW_USER="Administrator"
GW_PASS="manage"

# 1. Get API's policy ID
POLICY_ID=$(curl -s -u $GW_USER:$GW_PASS -H "Accept: application/json" \
  "$GW_URL/rest/apigateway/apis/$API_ID" | \
  python3 -c "import json,sys; print(json.load(sys.stdin)['apiResponse']['api']['policies'][0])")

echo "Policy ID: $POLICY_ID"

# 2. Get transport policy action ID
TRANSPORT_ACTION_ID=$(curl -s -u $GW_USER:$GW_PASS -H "Accept: application/json" \
  "$GW_URL/rest/apigateway/policies/$POLICY_ID" | \
  python3 -c "import json,sys; d=json.load(sys.stdin)
for e in d['policy']['policyEnforcements']:
  if e['stageKey'] == 'transport':
    print(e['enforcements'][0]['enforcementObjectId'])")

echo "Transport Action ID: $TRANSPORT_ACTION_ID"

# 3. Enable HTTP + HTTPS
curl -s -X PUT -u $GW_USER:$GW_PASS \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "$GW_URL/rest/apigateway/policyActions/$TRANSPORT_ACTION_ID" \
  -d "{
    \"policyAction\": {
      \"id\": \"$TRANSPORT_ACTION_ID\",
      \"names\": [{\"value\": \"Enable HTTP / HTTPS\", \"locale\": \"en\"}],
      \"templateKey\": \"entryProtocolPolicy\",
      \"parameters\": [{
        \"templateKey\": \"protocol\",
        \"values\": [\"http\", \"https\"]
      }],
      \"active\": true
    }
  }"

# 4. Verify
echo -e "\n\nTesting HTTPS access..."
curl -sk "https://localhost:5543/gateway/MyAPI/1.0/health"
```

### Transport Protocol Options

| Value | Port | Description |
|-------|------|-------------|
| `http` | 5555 | HTTP only (default) |
| `https` | 5543 | HTTPS only |
| `["http", "https"]` | Both | HTTP and HTTPS |

## API Lifecycle

### Activate API

```bash
curl -s -X PUT \
  -u Administrator:manage \
  "http://localhost:5555/rest/apigateway/apis/{apiId}/activate"
```

### Deactivate API

```bash
curl -s -X PUT \
  -u Administrator:manage \
  "http://localhost:5555/rest/apigateway/apis/{apiId}/deactivate"
```

### Delete API

```bash
# First deactivate, then delete
curl -s -X PUT \
  -u Administrator:manage \
  "http://localhost:5555/rest/apigateway/apis/{apiId}/deactivate"

curl -s -X DELETE \
  -u Administrator:manage \
  "http://localhost:5555/rest/apigateway/apis/{apiId}"
```

## Gateway Invocation

Once API is active, invoke via:
```
http://gateway:5555/gateway/{apiName}/{apiVersion}/{path}
```

Example:
```bash
curl -s "http://gateway:5555/gateway/MyAPI/1.0/health"
```

## Health Check

```bash
curl -s -u Administrator:manage \
  "http://localhost:5555/rest/apigateway/health"
```

## Common Issues

### "openapi url is not reachable"
- Gateway cannot fetch external URLs (no internet access in cluster)
- Solution: Use file upload approach instead

### "openapi file is not valid"
- OpenAPI 3.1.0 not supported
- Solution: Convert to 3.0.3 before import

### "Downtime exception: Not able to reach end point"
- nativeEndpoint configured incorrectly
- Solution: Create alias and use `${Alias}/${sys:resource_path}` format

### API PUT update returns error
- Full API object may be required for updates
- Solution: GET current API, modify, then PUT

## OIDC Security Configuration

### Architecture Overview

```
Client → apis.stoa.cab-i.com (HTTPS) → Ingress → Gateway:5543 → Backend
                                                      ↓
                                              OIDC Validation
                                                      ↓
                                              Keycloak (auth.stoa.cab-i.com)
```

### Step 1: Create External Authorization Server (Keycloak)

Create an External Authorization Server pointing to Keycloak with JWKS-based local introspection:

```bash
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/alias" \
  -d '{
    "name": "KeycloakOIDC",
    "description": "Keycloak OIDC Provider for STOA Platform",
    "type": "authServerAlias",
    "authServerType": "EXTERNAL",
    "localIntrospectionConfig": {
      "issuer": "https://auth.stoa.cab-i.com/realms/stoa",
      "jwksuri": "https://auth.stoa.cab-i.com/realms/stoa/protocol/openid-connect/certs"
    },
    "metadata": {
      "authorizeURL": "https://auth.stoa.cab-i.com/realms/stoa/protocol/openid-connect/auth",
      "accessTokenURL": "https://auth.stoa.cab-i.com/realms/stoa/protocol/openid-connect/token",
      "refreshTokenURL": "https://auth.stoa.cab-i.com/realms/stoa/protocol/openid-connect/token"
    },
    "scopes": [
      {"name": "openid", "description": "OpenID Connect scope"},
      {"name": "profile", "description": "User profile information"},
      {"name": "email", "description": "User email address"},
      {"name": "roles", "description": "User roles"},
      {"name": "offline_access", "description": "Offline access token"}
    ],
    "supportedGrantTypes": ["authorization_code", "client_credentials", "refresh_token"],
    "tokenGeneratorConfig": {
      "accessTokenExpInterval": 3600,
      "authCodeExpInterval": 600
    }
  }'
```

**Response:**
```json
{
  "alias": {
    "id": "8654d1f9-605b-4c9f-9552-172bb072cdce",
    "name": "KeycloakOIDC",
    "type": "authServerAlias",
    "authServerType": "EXTERNAL",
    "scopes": [...]
  }
}
```

### Step 2: Create OAuth2 Strategy

Create a strategy linking the application to the authorization server:

**IMPORTANT:** The request body must NOT be wrapped in a `strategy` object. Send the strategy properties directly.

```bash
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/strategies" \
  -d '{
    "name": "stoa-platform-oauth2",
    "description": "OAuth2/OIDC strategy for STOA platform APIs",
    "type": "OAUTH2",
    "authServerAlias": "KeycloakOIDC",
    "clientId": "control-plane-ui",
    "audience": "account"
  }'
```

**Response:**
```json
{
  "strategy": {
    "id": "29dce722-11d4-4238-8ae2-aec1c2f85369",
    "type": "OAUTH2",
    "authServerAlias": "KeycloakOIDC",
    "name": "stoa-platform-oauth2",
    "description": "OAuth2/OIDC strategy for STOA platform APIs",
    "clientId": "control-plane-ui",
    "audience": "account"
  }
}
```

**Notes:**
- The `audience` must match the `aud` claim in the Keycloak JWT token. By default, Keycloak sets this to `account`.
- The `type` must be uppercase: `OAUTH2` (not `oauth2`)
- Common error: `{"errorDetails":"Unrecognized Type: [null]"}` means the body was wrapped incorrectly

### Step 3: Create Application

Create an application representing the consuming client:

```bash
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/applications" \
  -d '{
    "name": "control-plane-ui",
    "description": "DevOps UI Application for Control Plane",
    "contactEmails": ["admin@cab-i.com"],
    "siteURLs": ["https://devops.stoa.cab-i.com"]
  }'
```

**Response contains:**
- `id`: Application UUID
- `accessTokens.apiAccessKey_credentials.apiAccessKey`: Generated API key

### Step 4: Associate Strategy to Application

Update the application with the authentication strategy and identifier:

```bash
APP_ID="<application-id>"
STRATEGY_ID="<strategy-id>"

curl -s -X PUT \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/applications/$APP_ID" \
  -d '{
    "name": "control-plane-ui",
    "description": "DevOps UI Application for Control Plane",
    "contactEmails": ["admin@cab-i.com"],
    "authStrategyIds": ["'"$STRATEGY_ID"'"],
    "identifiers": [
      {
        "key": "openIdClaims",
        "name": "azp",
        "value": ["control-plane-ui"]
      }
    ]
  }'
```

**Important:** The identifier `openIdClaims` with `name: azp` matches the `azp` (authorized party) claim in Keycloak JWT tokens.

### Step 5: Associate APIs to Application

**IMPORTANT:** The `consumingAPIs` field cannot be modified via PUT on the application. Use the dedicated `/apis` endpoint instead:

```bash
APP_ID="<application-id>"

# Associate multiple APIs to application (POST adds, doesn't replace)
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/applications/$APP_ID/apis" \
  -d '{
    "apiIDs": [
      "7ba67c90-814d-4d2f-a5da-36e9cda77afe",
      "8f9c7b6c-1bc6-4438-88be-a10e2352bae2"
    ]
  }'
```

**Verify association:**
```bash
curl -s -u Administrator:manage \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/applications/$APP_ID/apis" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Associated APIs:', d.get('apiIDs', []))"
```

### Step 6: Create OAuth Scope Mappings

**CRITICAL:** Create scope mappings to link OAuth scopes from the authorization server to the API. Without these mappings, JWT token validation will fail with "Audience match failed".

```bash
API_ID="<api-id>"

# Create scope mapping for openid
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/scopes" \
  -d '{
    "scopeName": "KeycloakOIDC:openid",
    "scopeDescription": "OpenID Connect scope",
    "audience": "control-plane-api",
    "apiScopes": ["'"$API_ID"'"],
    "requiredAuthScopes": [
      {
        "authServerAlias": "KeycloakOIDC",
        "scopeName": "openid"
      }
    ]
  }'

# Create scope mapping for profile
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/scopes" \
  -d '{
    "scopeName": "KeycloakOIDC:profile",
    "scopeDescription": "User profile information",
    "audience": "control-plane-api",
    "apiScopes": ["'"$API_ID"'"],
    "requiredAuthScopes": [
      {
        "authServerAlias": "KeycloakOIDC",
        "scopeName": "profile"
      }
    ]
  }'

# Create scope mapping for email
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/scopes" \
  -d '{
    "scopeName": "KeycloakOIDC:email",
    "scopeDescription": "User email address",
    "audience": "control-plane-api",
    "apiScopes": ["'"$API_ID"'"],
    "requiredAuthScopes": [
      {
        "authServerAlias": "KeycloakOIDC",
        "scopeName": "email"
      }
    ]
  }'

# Create scope mapping for roles
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/scopes" \
  -d '{
    "scopeName": "KeycloakOIDC:roles",
    "scopeDescription": "User roles",
    "audience": "control-plane-api",
    "apiScopes": ["'"$API_ID"'"],
    "requiredAuthScopes": [
      {
        "authServerAlias": "KeycloakOIDC",
        "scopeName": "roles"
      }
    ]
  }'
```

**Important Notes:**
- `scopeName` format: `{AuthServerName}:{ScopeName}`
- `audience` must match the `aud` claim in the JWT token (configure via Keycloak audience mapper)
- `apiScopes` is an array of API IDs this scope applies to
- `requiredAuthScopes` links to the authorization server scope definition

### Step 7: Create Identify & Authorize Policy Action

Create a policy action for OIDC authentication:

```bash
curl -s -X POST \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/policyActions" \
  -d '{
    "policyAction": {
        "names": [{"value": "Identify & Authorize OIDC", "locale": "en"}],
        "templateKey": "evaluatePolicy",
        "parameters": [
            {"templateKey": "logicalConnector", "values": ["OR"]},
            {"templateKey": "allowAnonymous", "values": ["false"]},
            {
                "templateKey": "IdentificationRule",
                "parameters": [
                    {"templateKey": "applicationLookup", "values": ["strict"]},
                    {"templateKey": "identificationType", "values": ["openIdClaims"]}
                ]
            }
        ],
        "active": true
    }
  }'
```

### Step 8: Add IAM Stage to API Policy

Update the API's policy to include IAM enforcement:

```bash
POLICY_ID="<api-policy-id>"
IAM_ACTION_ID="<iam-policy-action-id>"
ROUTING_ACTION_ID="<routing-policy-action-id>"
TRANSPORT_ACTION_ID="<transport-policy-action-id>"

curl -s -X PUT \
  -u Administrator:manage \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  "http://localhost:5555/rest/apigateway/policies/$POLICY_ID" \
  -d '{
    "policy": {
        "id": "'"$POLICY_ID"'",
        "names": [{"value": "API Policy with OIDC", "locale": "English"}],
        "descriptions": [{"value": "Policy with OIDC authentication", "locale": "English"}],
        "policyEnforcements": [
            {
                "enforcements": [{"enforcementObjectId": "'"$IAM_ACTION_ID"'", "order": "0"}],
                "stageKey": "IAM"
            },
            {
                "enforcements": [{"enforcementObjectId": "'"$ROUTING_ACTION_ID"'", "order": "0"}],
                "stageKey": "routing"
            },
            {
                "enforcements": [{"enforcementObjectId": "'"$TRANSPORT_ACTION_ID"'", "order": "0"}],
                "stageKey": "transport"
            }
        ],
        "policyScope": "SERVICE",
        "active": true
    }
  }'
```

### Keycloak Configuration Requirements

For the OIDC integration to work correctly, ensure these Keycloak settings:

1. **Client `control-plane-ui`:**
   - Direct Access Grants Enabled: `true` (for password grant testing)
   - Standard Flow Enabled: `true`
   - Valid Redirect URIs: `https://devops.stoa.cab-i.com/*`
   - Web Origins: `https://devops.stoa.cab-i.com`

2. **Token Audience:**
   - By default, Keycloak sets `aud: account`
   - Configure audience mapper if you need a custom audience

3. **Realm Roles:**
   - `cpi-admin`: Platform administrator
   - `tenant-admin`: Tenant administrator
   - `devops`: DevOps engineer
   - `viewer`: Read-only access

### Testing OIDC Authentication

```bash
# Get token from Keycloak
TOKEN=$(curl -s -X POST \
  "https://auth.stoa.cab-i.com/realms/stoa/protocol/openid-connect/token" \
  -d "client_id=control-plane-ui" \
  -d "username=admin@stoa.local" \
  -d "password=demo" \
  -d "grant_type=password" | jq -r '.access_token')

# Call API via Gateway
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://apis.stoa.cab-i.com/gateway/Control-Plane-API/2.0/health"
```

### Debugging OIDC Issues

1. **Enable Tracing** in Gateway UI for the API
2. **Check Token Claims:**
   ```bash
   echo $TOKEN | cut -d. -f2 | base64 -d | jq
   ```
3. **Common Errors:**
   - `Audience match failed`: Ensure `audience` in strategy matches `aud` claim
   - `Token specified is invalid`: Check issuer and JWKS URI accessibility
   - `Unauthorized application`: Verify application is associated with API

### Exposing Gateway Admin API Securely

The Gateway Admin REST API (`/rest/apigateway/*`) should NOT be exposed externally with basic auth. Instead:

1. **Create a proxy API** that exposes specific admin endpoints
2. **Secure with OIDC** requiring `cpi-admin` role
3. **Route to internal endpoint** via alias

Example Architecture:
```
External:  https://apis.stoa.cab-i.com/admin/gateway/apis
           ↓ OIDC (JWT validation)
Gateway:   /gateway/GatewayAdmin/1.0/apis
           ↓ Alias routing
Internal:  http://localhost:5555/rest/apigateway/apis
```

## Ansible Integration

See `/ansible/playbooks/register-api-gateway.yaml` for automated API registration including:
1. Download and convert OpenAPI spec
2. Create endpoint alias
3. Import API via file upload
4. Configure routing with alias
5. Activate API

## Kubernetes Service Configuration

Ensure the Gateway service exposes all required ports:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: apigateway
  namespace: stoa-system
spec:
  ports:
  - name: runtime
    port: 5555
    targetPort: 5555
  - name: runtime-https
    port: 5543
    targetPort: 5543
  - name: ui
    port: 9072
    targetPort: 9072
  selector:
    app.kubernetes.io/name: apigateway
```

To add the HTTPS port to an existing service:

```bash
kubectl patch svc apigateway -n stoa-system --type='json' \
  -p='[{"op": "add", "path": "/spec/ports/-", "value": {"name": "runtime-https", "port": 5543, "protocol": "TCP", "targetPort": 5543}}]'
```
