---
sidebar_position: 1
title: Developer Portal
description: Consumer workflow — discover, subscribe, and test APIs.
---

# Developer Portal

The Developer Portal is the API consumer's interface. Developers use it to discover APIs, manage subscriptions, and test endpoints.

**URL**: [portal.gostoa.dev](https://portal.gostoa.dev)

## Getting Started

1. Navigate to the Portal URL
2. Click **Sign In** — authenticates via Keycloak (OIDC client: `stoa-portal`)
3. You'll see the API catalog on the home page

## API Catalog

The catalog displays all APIs published to the Portal by tenant admins.

### Browsing

- **Search**: Full-text search across API names, descriptions, and tags
- **Filter**: Filter by category, version, or tenant
- **Sort**: Sort by name, date published, or popularity

### API Detail Page

Click on an API to view:

- **Description**: Overview and purpose
- **Documentation**: Interactive OpenAPI/Swagger viewer
- **Versions**: Available versions with changelog
- **Subscribe button**: Request access to the API

## Subscriptions

### Creating a Subscription

1. Navigate to the API you want to use
2. Click **Subscribe**
3. Select an existing application or create a new one
4. Choose a plan (if multiple plans are available)
5. Submit the request

### Subscription Status

Track your subscriptions in **My Subscriptions**:

| Status | Meaning |
|--------|---------|
| Pending | Awaiting tenant admin approval |
| Active | Access granted — credentials available |
| Suspended | Temporarily paused by admin |
| Rejected | Request denied |

### Viewing Credentials

Once a subscription is approved:

1. Go to **My Subscriptions**
2. Click on the active subscription
3. View the API key or OAuth credentials
4. Copy credentials for use in your application

## Applications

Applications represent your client software that consumes APIs.

### Creating an Application

1. Navigate to **My Applications**
2. Click **Create Application**
3. Enter a name and description
4. The application is created and ready for subscriptions

### Application Dashboard

View all subscriptions, credentials, and usage metrics for each application.

## Testing APIs

The Portal includes an interactive API tester:

1. Open an API with an active subscription
2. Navigate to the **Try It** section
3. Select an endpoint
4. Fill in parameters
5. Click **Send** to execute the request
6. View the response with headers and body

## Authentication

The Portal uses Keycloak for authentication:

- **OIDC Client**: `stoa-portal`
- **Login**: Keycloak login page with username/password or SSO
- **Session**: JWT tokens stored in `sessionStorage`
- **Token refresh**: Handled automatically by `react-oidc-context`

See [Authentication](./authentication) for Keycloak configuration.
