---
slug: /
sidebar_position: 1
title: Introduction
description: What is STOA Platform — multi-tenant API management for the AI era.
---

# Introduction

STOA is a **multi-tenant API management platform** that brings together traditional API governance and AI-native access through the MCP (Model Context Protocol) Gateway.

## What STOA Does

STOA provides a complete API lifecycle management system:

- **Publish** APIs with versioning, policies, and access control
- **Consume** APIs through a self-service Developer Portal
- **Govern** APIs with tenant isolation, RBAC, and policy enforcement
- **Connect AI agents** to APIs via the MCP Gateway — no custom integration code

## Who It's For

| Role | What STOA Provides |
|------|---------------------|
| **API Providers** | Console UI to manage tenants, APIs, policies, and users |
| **API Consumers** | Developer Portal to discover, subscribe, and test APIs |
| **Platform Teams** | GitOps-driven infrastructure with Helm, ArgoCD, and Terraform |
| **AI Engineers** | MCP Gateway for tool-based API access from LLM agents |

## Key Capabilities

### Multi-Tenant Isolation

Each tenant gets its own Kubernetes namespace, RBAC scope, and API catalog. Tenants cannot see or access each other's resources.

### GitOps-Native

Git is the source of truth. Changes to API definitions, policies, and tenant configuration flow through Git → ArgoCD → Kubernetes, with AWX handling gateway reconciliation.

### Gateway-Agnostic

STOA's Gateway Adapter pattern supports multiple API gateways behind a unified interface. webMethods is production-ready; Kong, Apigee, and AWS API Gateway adapters are planned.

### AI-Native Access

The MCP Gateway exposes APIs as **tools** that AI agents can discover and invoke. OPA policies enforce fine-grained access control, and a Kafka-based metering pipeline tracks usage.

## Platform Components

```
┌──────────────────────────────────────────────────┐
│                   Clients                        │
│  Console UI · Portal · CLI · AI Agents           │
└──────────────┬───────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────┐
│              Control Plane API                   │
│  FastAPI · Keycloak OIDC · PostgreSQL            │
└──────┬───────────┬───────────┬───────────────────┘
       │           │           │
┌──────▼──┐  ┌─────▼────┐  ┌──▼──────────┐
│ MCP GW  │  │  GitLab  │  │   Kafka     │
│ (AI)    │  │  (GitOps)│  │  (Events)   │
└─────────┘  └──────────┘  └─────────────┘
```

## Next Steps

- [**Quickstart**](/getting-started/quickstart) — Get your first API running
- [**Installation**](/getting-started/installation) — Deploy STOA on Docker or Kubernetes
- [**Architecture**](/getting-started/architecture) — Understand the component design
