---
sidebar_position: 5
title: MCP Gateway
description: AI-native API access via the Model Context Protocol.
---

# MCP Gateway

The MCP Gateway enables **AI agents to discover and invoke APIs** using the Model Context Protocol. Instead of writing custom API integration code, agents call APIs as tools through a standardized protocol.

## What is MCP?

The [Model Context Protocol](https://modelcontextprotocol.io) (MCP) is an open standard for connecting AI models to external tools and data sources. It defines how agents:

1. **Discover** available tools and their schemas
2. **Invoke** tools with typed parameters
3. **Receive** structured results

STOA implements an MCP server that exposes your APIs as tools.

## Architecture

```
┌─────────────┐     SSE      ┌──────────────────┐     HTTP    ┌──────────┐
│  AI Agent   │◄────────────►│   MCP Gateway     │────────────►│ Backend  │
│  (Claude,   │              │                   │             │  API     │
│   GPT, ...) │              │  ┌─────────────┐  │             └──────────┘
└─────────────┘              │  │ Tool Registry│  │
                             │  │ OPA Engine   │  │
                             │  │ Metering     │  │
                             │  └─────────────┘  │
                             └──────────────────┘
```

### Components

| Component | Purpose |
|-----------|---------|
| **Tool Registry** | Dynamic registry of available tools, loaded from Kubernetes CRDs |
| **OPA Policy Engine** | Fine-grained RBAC — which agents can call which tools |
| **Metering Pipeline** | Kafka-based usage tracking, rate limiting, billing |
| **SSE Transport** | Server-Sent Events for real-time MCP communication |

## Registering Tools

Tools are registered as Kubernetes Custom Resources. When an API is published, you can create a corresponding Tool CRD:

```yaml
apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: list-pets
  namespace: tenant-acme
spec:
  displayName: List Pets
  description: Retrieve a paginated list of pets from the store
  endpoint: https://api.example.com/v1/pets
  method: GET
  inputSchema:
    type: object
    properties:
      limit:
        type: integer
        description: Maximum number of pets to return
        default: 20
      status:
        type: string
        enum: [available, pending, sold]
        description: Filter by pet status
```

Apply the CRD:

```bash
kubectl apply -f tool-list-pets.yaml
```

The MCP Gateway's CRD watcher (when `K8S_WATCHER_ENABLED=true`) picks up the new tool automatically.

### ToolSets

Group related tools into a ToolSet for logical organization:

```yaml
apiVersion: gostoa.dev/v1alpha1
kind: ToolSet
metadata:
  name: petstore-tools
  namespace: tenant-acme
spec:
  displayName: Petstore API Tools
  description: All operations for the Petstore API
  tools:
    - list-pets
    - get-pet
    - create-pet
    - update-pet
```

## Agent Interaction

### Discovery

An agent lists available tools:

```
→ tools/list
← {
    "tools": [
      {
        "name": "list-pets",
        "description": "Retrieve a paginated list of pets",
        "inputSchema": { ... }
      }
    ]
  }
```

### Invocation

The agent calls a tool:

```
→ tools/call
  { "name": "list-pets", "arguments": { "limit": 5, "status": "available" } }

← {
    "content": [
      {
        "type": "text",
        "text": "[{\"id\": 1, \"name\": \"Buddy\", \"status\": \"available\"}, ...]"
      }
    ]
  }
```

## OPA Policies

Access control is enforced by OPA (Open Policy Agent). Policies evaluate:

- **Who** is calling (agent identity, tenant)
- **What** they are calling (tool name, namespace)
- **How** they are calling (parameters, frequency)

Example policy:

```rego
package stoa.mcp

default allow = false

allow {
    input.tenant == input.tool_namespace
    input.scope == "stoa:read"
    input.tool_name == "list-pets"
}

allow {
    input.scope == "stoa:admin"
}
```

## Metering

Every tool invocation is metered via Kafka:

```json
{
  "event": "tool.call",
  "tool": "list-pets",
  "tenant": "acme",
  "agent_id": "agent-123",
  "timestamp": "2026-02-04T10:30:00Z",
  "latency_ms": 145,
  "status": "success"
}
```

Metering data feeds into:

- **Rate limiting**: Enforce per-tenant/per-agent call quotas
- **Billing**: Usage-based pricing for API access
- **Observability**: Grafana dashboards for tool usage metrics

## Gateway Modes

The MCP Gateway is the first of four planned gateway modes:

| Mode | Status | Transport | Use Case |
|------|--------|-----------|----------|
| **edge-mcp** | Production | SSE/MCP | AI agent access |
| **sidecar** | Planned (Q2) | HTTP | Behind 3rd-party gateways |
| **proxy** | Planned (Q3) | HTTP | Inline policy enforcement |
| **shadow** | Deferred | Passive | Traffic capture, UAC generation |

See the [Architecture](../getting-started/architecture) page for the unified gateway design.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPA_ENABLED` | `true` | Enable policy enforcement |
| `OPA_EMBEDDED` | `true` | Use embedded evaluator |
| `METERING_ENABLED` | `true` | Enable Kafka metering |
| `K8S_WATCHER_ENABLED` | `false` | Enable CRD watcher |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker list |
