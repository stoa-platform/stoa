---
sidebar_position: 2
title: Quickstart
description: Get your first API published on STOA in 5 minutes.
---

# Quickstart

This guide walks you through publishing your first API on STOA — from zero to a live, discoverable endpoint.

## Prerequisites

- Docker and Docker Compose installed
- `curl` available in your terminal

## 1. Start STOA Locally

```bash
git clone https://github.com/stoa-platform/stoa.git
cd stoa
docker compose -f deploy/docker-compose.yml up -d
```

Wait for all services to become healthy:

```bash
docker compose -f deploy/docker-compose.yml ps
```

The following services will be available:

| Service | URL |
|---------|-----|
| Console UI | http://localhost:3000 |
| Developer Portal | http://localhost:5173 |
| Control Plane API | http://localhost:8000 |
| MCP Gateway | http://localhost:8001 |
| Keycloak | http://localhost:8080 |

## 2. Log In to the Console

Open **http://localhost:3000** in your browser and log in with the default admin credentials:

- **Username**: `admin@stoa.local`
- **Password**: `admin`

You'll land on the Console dashboard — the API Provider's control center.

## 3. Create a Tenant

Tenants are the isolation boundary in STOA. Create one for your organization:

```bash
curl -X POST http://localhost:8000/v1/tenants \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-org",
    "displayName": "My Organization",
    "contactEmail": "admin@my-org.com"
  }'
```

Or use the Console UI: navigate to **Tenants → Create Tenant**.

## 4. Publish an API

Register an API from an OpenAPI specification:

```bash
curl -X POST http://localhost:8000/v1/tenants/my-org/apis \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "petstore",
    "version": "1.0.0",
    "displayName": "Petstore API",
    "description": "A sample API for managing pets",
    "specUrl": "https://petstore3.swagger.io/api/v3/openapi.json"
  }'
```

## 5. Verify in the Portal

Open the **Developer Portal** at **http://localhost:5173**. Your Petstore API should appear in the API catalog, ready for consumers to discover and subscribe.

## What's Next

- [**Installation**](./installation) — Deploy to Kubernetes for production
- [**APIs**](../core-concepts/apis) — Learn about API lifecycle management
- [**Tenants**](../core-concepts/tenants) — Understand multi-tenancy
- [**MCP Gateway**](../core-concepts/mcp-gateway) — Connect AI agents to your APIs
