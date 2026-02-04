---
sidebar_position: 3
title: Subscriptions
description: Consumer access model — subscribe, approve, consume.
---

# Subscriptions

Subscriptions connect API consumers to APIs. A subscription grants an application access to call a specific API with defined rate limits and policies.

## Subscription Flow

```
Consumer                    Provider
   │                           │
   ├── Subscribe to API ──────►│
   │                           ├── Review request
   │◄── Approval/Rejection ───┤
   │                           │
   ├── Receive credentials ───►│
   │                           │
   ├── Call API ──────────────►│
```

### 1. Request

A consumer browses the Developer Portal, finds an API, and requests a subscription. The request includes:

- **Application**: The consumer's registered application
- **API + Version**: The specific API and version to subscribe to
- **Plan** (optional): Rate limit tier (free, standard, premium)

### 2. Approval

Depending on the API configuration, subscriptions are either:

- **Auto-approved**: Consumer gets immediate access
- **Manual approval**: Tenant admin reviews and approves/rejects

### 3. Provisioning

On approval, STOA:

1. Creates OAuth credentials for the application-API pair
2. Configures rate limits on the gateway
3. Publishes a Kafka event (`subscription.approved`)
4. The Gateway Adapter provisions access on the target gateway

### 4. Consumption

The consumer uses the provided credentials to call the API through the gateway. All traffic is subject to the subscription's rate limits and policies.

## Subscription States

| State | Description |
|-------|-------------|
| `pending` | Request submitted, awaiting approval |
| `active` | Approved and provisioned — API is callable |
| `suspended` | Temporarily disabled by admin |
| `rejected` | Request denied by tenant admin |
| `revoked` | Previously active, now terminated |

## Managing Subscriptions

### As a Consumer (Portal)

1. Navigate to an API in the catalog
2. Click **Subscribe**
3. Select your application (or create one)
4. Submit the subscription request
5. Once approved, view credentials in **My Subscriptions**

### As a Provider (Console)

1. Navigate to **Subscriptions** in the Console
2. Review pending requests
3. Approve or reject with an optional message
4. Monitor active subscriptions and usage

### Via API

```bash
# List subscriptions for an API
curl https://api.gostoa.dev/v1/tenants/acme/apis/petstore/subscriptions \
  -H "Authorization: Bearer $TOKEN"

# Approve a subscription
curl -X PATCH https://api.gostoa.dev/v1/subscriptions/{id}/approve \
  -H "Authorization: Bearer $TOKEN"
```

## Applications

Applications are the consumer-side entity that holds subscriptions. A single application can subscribe to multiple APIs.

```
Application: "Mobile App"
├── Subscription: Petstore API v1.0 (active)
├── Subscription: Payments API v2.0 (active)
└── Subscription: Analytics API v1.0 (pending)
```

### Creating an Application

```bash
curl -X POST https://api.gostoa.dev/v1/applications \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-mobile-app",
    "displayName": "My Mobile App",
    "description": "Production mobile application"
  }'
```

## Rate Limiting

Subscriptions enforce rate limits at the gateway level:

| Plan | Requests/min | Burst |
|------|-------------|-------|
| Free | 60 | 10 |
| Standard | 600 | 100 |
| Premium | 6000 | 1000 |

Rate limits are configured per API and applied per subscription.
