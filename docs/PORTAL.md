# STOA Developer Portal - User Guide

> **URL**: https://portal.gostoa.dev
> **Status**: Production
> **Last Updated**: January 2026

## Overview

The STOA Developer Portal is the API Consumer interface for browsing, subscribing to, and testing MCP Tools and APIs. It provides:

- **MCP Tools Catalog**: Browse and subscribe to AI-powered MCP Tools
- **API Catalog**: Discover and explore available APIs
- **Subscriptions**: Manage tool and API subscriptions with API keys
- **Applications**: Register consumer applications for API access
- **Profile**: View account information and settings

---

## Getting Started

### Authentication

The portal uses **Keycloak OIDC** for authentication:

1. Navigate to https://portal.gostoa.dev
2. Click **"Sign in with SSO"**
3. Enter your Keycloak credentials
4. You'll be redirected to the portal dashboard

### Navigation

The left sidebar provides access to all portal sections:

| Menu Item | Description |
|-----------|-------------|
| **Home** | Dashboard with quick actions and stats |
| **MCP Tools** | Browse and subscribe to MCP Tools |
| **API Catalog** | Browse published APIs |
| **My Apps** | Manage consumer applications |
| **My Subscriptions** | View and manage subscriptions |
| **Profile** | Account information |

---

## MCP Tools

### Browsing Tools

1. Click **"MCP Tools"** in the sidebar
2. Use the search bar to find tools by name or description
3. Filter by category using the dropdown
4. Click a tool card to view details

### Subscribing to a Tool

1. Navigate to the tool detail page
2. Click **"Subscribe"** button
3. Select a subscription plan:
   - **Free**: 100 calls/day, basic support
   - **Basic**: 10,000 calls/day, email support
   - **Premium**: 100,000 calls/day, priority support
4. Click **"Subscribe"** to confirm

### API Key (One-Time Display)

After subscribing, you'll see the **API Key Modal**:

> **IMPORTANT**: The API key is shown **only once**! Copy it immediately.

1. Copy the API key using the copy button
2. Optionally, download the `claude_desktop_config.json` configuration
3. Check the acknowledgment box
4. Click **"Done"**

### Using Your API Key

```bash
# Direct API call
curl -X POST https://mcp.gostoa.dev/mcp/v1/invoke \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tool": "tool_name", "args": {}}'
```

Or configure Claude Desktop with the downloaded config file.

---

## My Subscriptions

### Viewing Subscriptions

1. Click **"My Subscriptions"** in the sidebar
2. See stats: Active subscriptions, Total API calls, Expired
3. Filter by status: All, Active, Expired, Revoked
4. Search by tool name

### Subscription Information

Each subscription card shows:
- Tool name and status badge
- Created date
- Expiration date (if applicable)
- Last used date
- Usage count

### Revoking a Subscription

1. Find the active subscription
2. Click **"Revoke"** button
3. Confirm the revocation

> **Warning**: Revoking immediately invalidates the API key.

---

## API Catalog

### Browsing APIs

1. Click **"API Catalog"** in the sidebar
2. Search for APIs by name or description
3. Filter by category
4. Click an API card for details

### API Detail Page

- **Overview**: Description, version, tags
- **Endpoints**: Available operations
- **OpenAPI Spec**: Full specification viewer
- **Testing Sandbox**: Try API calls directly

### API Testing Sandbox

1. From API detail, click **"Test API"**
2. Select the environment (dev, staging, prod)
3. Configure request:
   - HTTP method
   - Path with parameters
   - Headers
   - Request body (JSON)
4. Click **"Send Request"**
5. View response with timing info

> **Warning**: Production environment requires confirmation.

---

## My Applications

### Creating an Application

1. Click **"My Apps"** in the sidebar
2. Click **"Create Application"**
3. Fill in:
   - Name
   - Description
   - Callback URLs (for OAuth)
4. Click **"Create"**

### Application Credentials

After creation, you'll receive:
- **Client ID**: Public identifier
- **Client Secret**: Shown once (copy immediately!)

### Application Subscriptions

Each application can subscribe to multiple APIs:
1. Go to application detail
2. Click **"Subscribe to API"**
3. Select an API and plan
4. Confirm subscription

---

## Configuration

### Environment Variables

The portal is configured via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `VITE_KEYCLOAK_URL` | Keycloak base URL | https://auth.gostoa.dev |
| `VITE_KEYCLOAK_REALM` | Keycloak realm | stoa |
| `VITE_KEYCLOAK_CLIENT_ID` | OIDC client ID | stoa-portal |
| `VITE_API_URL` | Control-Plane API URL | https://api.gostoa.dev |
| `VITE_MCP_GATEWAY_URL` | MCP Gateway URL | https://mcp.gostoa.dev |
| `VITE_CONSOLE_URL` | Console UI URL | https://console.gostoa.dev |

### Feature Flags

Features can be enabled/disabled in `portal/src/config.ts`:

```typescript
features: {
  enableMCPTools: true,      // MCP Tools catalog
  enableAPICatalog: true,    // API catalog
  enableSubscriptions: true,  // Subscriptions management
  enableAPITesting: true,    // API testing sandbox
}
```

---

## Troubleshooting

### Login Issues

- **"Failed to authenticate"**: Check Keycloak is running
- **Redirect loop**: Clear browser cookies and try again
- **Access denied**: Verify your user has portal access roles

### Subscription Issues

- **"Already subscribed"**: Check My Subscriptions for existing subscription
- **API key not showing**: Subscription may have failed - check console errors
- **Tool invocation fails**: Verify API key is correct and not expired

### API Testing Issues

- **"Network error"**: Check API is accessible from portal
- **"401 Unauthorized"**: Token may have expired - re-login
- **"403 Forbidden"**: Check you have subscription to this API

---

## Related Documentation

- [MCP Gateway Documentation](./MCP-GATEWAY.md)
- [Observability Guide](./OBSERVABILITY.md)
- [Subscriptions System](./SUBSCRIPTIONS.md)
- [E2E Testing Guide](./E2E-TESTING.md)

---

## Changelog

### 2026-01-08
- Added ApiKeyModal with one-time API key display (CAB-292)
- Fixed sidebar navigation with proper z-index and scrolling
- Connected useSubscribeToTool hook to MCP subscriptions service

### 2026-01-05
- Initial portal release (CAB-246)
- MCP Tools catalog and subscriptions
- API catalog with testing sandbox
- Applications management
