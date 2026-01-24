# STOA MCP Gateway

> Model Context Protocol Gateway for AI-Native API Management

## Overview

The STOA MCP Gateway exposes APIs as [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) tools, enabling LLMs to discover and invoke APIs through a standardized interface.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          STOA MCP Gateway                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     MCP Protocol Layer                           │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │   │
│  │  │  Tools   │  │Resources │  │ Prompts  │  │ Sampling │        │   │
│  │  │Discovery │  │  Access  │  │Templates │  │  Hooks   │        │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                  │                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Security & Policy Layer                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │   │
│  │  │ Keycloak │  │   OPA    │  │  Rate    │  │ Metering │        │   │
│  │  │   OIDC   │  │ Policies │  │ Limiting │  │  Kafka   │        │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                  │                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Kubernetes Integration                       │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐                       │   │
│  │  │ Tool CRD │  │ToolSet   │  │   RBAC   │                       │   │
│  │  │ Watcher  │  │  CRD     │  │ Control  │                       │   │
│  │  └──────────┘  └──────────┘  └──────────┘                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                  │                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Backend Adapters                             │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │   │
│  │  │ REST/OAS │  │ GraphQL  │  │   gRPC   │  │  Kafka   │        │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Features

### Core Capabilities
- **MCP Protocol**: Full implementation of tools, resources, and prompts endpoints
- **Tool Registry**: Dynamic registration of tools from APIs and CRDs
- **OpenAPI Converter**: Automatic conversion of OpenAPI specs to MCP tools

### Security & Policy (CAB-122)
- **Keycloak OIDC**: JWT-based authentication with role extraction
- **OPA Policy Engine**: Fine-grained authorization with embedded or sidecar mode
- **Tenant Isolation**: Multi-tenant support with namespace-based isolation
- **Rate Limiting**: Role-based rate limits (cpi-admin, tenant-admin, devops, viewer)

### Metering & Billing (CAB-123)
- **Kafka Producer**: Async metering events for usage tracking
- **Cost Computation**: Latency-based and tool-type pricing model
- **Consumer Tracking**: X-Consumer-ID header for client identification

### Kubernetes Integration (CAB-121)
- **Tool CRD**: Register tools via Kubernetes custom resources
- **ToolSet CRD**: Generate multiple tools from OpenAPI specs
- **Dynamic Sync**: Watch and sync tools from Kubernetes in real-time

## Quick Start

### Prerequisites

- Python 3.11+
- pip or uv

### Installation

```bash
# Clone the repository
cd mcp-gateway

# Install dependencies
pip install -e ".[dev]"

# For Kubernetes integration
pip install -e ".[k8s]"

# Or with uv
uv pip install -e ".[dev,k8s]"
```

### Run Development Server

```bash
# Set environment variables
export BASE_DOMAIN=gostoa.dev
export DEBUG=true

# Run the server
python -m src.main

# Or with uvicorn directly
uvicorn src.main:app --reload --port 8080
```

### Run with Docker Compose

```bash
# Start all services (Gateway, Keycloak, OPA, Prometheus, Grafana)
docker-compose up -d

# View logs
docker-compose logs -f mcp-gateway
```

### Build and Deploy Docker Image

```bash
# Build for amd64 (for Kubernetes deployment)
docker build --platform linux/amd64 -t mcp-gateway:latest .

# Push to ECR
aws ecr get-login-password --region eu-west-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.eu-west-1.amazonaws.com
docker tag mcp-gateway:latest <account>.dkr.ecr.eu-west-1.amazonaws.com/apim/mcp-gateway:latest
docker push <account>.dkr.ecr.eu-west-1.amazonaws.com/apim/mcp-gateway:latest
```

**Note:** The Docker image includes `kubernetes-asyncio` for K8s CRD watching. The Dockerfile installs `.[k8s]` extras.

## Endpoints

### Health Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check for load balancers |
| `GET /ready` | Readiness check for Kubernetes |
| `GET /live` | Liveness check for Kubernetes |
| `GET /metrics` | Prometheus metrics |

### MCP Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /mcp/v1/` | Server info and capabilities |
| `GET /mcp/v1/tools` | List available MCP tools |
| `GET /mcp/v1/tools/{name}` | Get tool details |
| `POST /mcp/v1/tools/{name}/invoke` | Invoke a tool (requires auth) |
| `GET /mcp/v1/resources` | List available resources |
| `GET /mcp/v1/prompts` | List available prompts |

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BASE_DOMAIN` | `gostoa.dev` | Base domain for STOA services |
| `ENVIRONMENT` | `dev` | Environment (dev/staging/prod) |
| `DEBUG` | `false` | Enable debug mode |
| `PORT` | `8080` | Server port |
| `KEYCLOAK_URL` | Derived | Keycloak URL |
| `KEYCLOAK_REALM` | `stoa` | Keycloak realm |
| `OPA_ENABLED` | `true` | Enable OPA policy engine |
| `OPA_EMBEDDED` | `true` | Use embedded Python evaluator |
| `METERING_ENABLED` | `true` | Enable Kafka metering |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka brokers |
| `K8S_WATCHER_ENABLED` | `false` | Enable K8s CRD watcher |

## Project Structure

```
mcp-gateway/
├── src/
│   ├── main.py              # FastAPI application
│   ├── config/              # Settings and configuration
│   ├── handlers/            # MCP protocol handlers
│   ├── middleware/          # Auth, metrics
│   ├── models/              # Pydantic models (MCP types)
│   ├── services/            # Tool registry, OpenAPI converter
│   ├── policy/              # OPA client and Rego policies
│   ├── metering/            # Kafka producer for billing
│   └── k8s/                 # Kubernetes CRD watcher
├── tests/                   # 196 tests, 79% coverage
├── dev/                     # Docker Compose dev resources
├── docker-compose.yml       # Local development stack
└── pyproject.toml
```

## Kubernetes CRDs

### RBAC Requirements

When running in Kubernetes with `K8S_WATCHER_ENABLED=true`, the MCP Gateway needs RBAC permissions to watch Tool and ToolSet CRDs:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: stoa-mcp-gateway
  namespace: stoa-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: stoa-mcp-gateway-tools
rules:
  - apiGroups: ["gostoa.dev"]
    resources: ["tools", "toolsets"]
    verbs: ["get", "list", "watch"]
  - apiGroups: ["gostoa.dev"]
    resources: ["tools/status", "toolsets/status"]
    verbs: ["get", "patch", "update"]
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: stoa-mcp-gateway-tools
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: stoa-mcp-gateway-tools
subjects:
  - kind: ServiceAccount
    name: stoa-mcp-gateway
    namespace: stoa-system
```

The Helm chart (`charts/stoa-platform/templates/mcp-gateway-rbac.yaml`) creates these resources automatically when `mcpGateway.k8s.enabled=true`.

### Tool CRD

```yaml
apiVersion: gostoa.dev/v1alpha1
kind: Tool
metadata:
  name: payment-search
  namespace: tenant-acme
spec:
  displayName: Search Payments
  description: Search payment records by various criteria
  endpoint: https://api.example.com/v1/payments/search
  method: GET
  tags: [payments, search]
  inputSchema:
    properties:
      query:
        type: string
    required: [query]
```

### ToolSet CRD

```yaml
apiVersion: gostoa.dev/v1alpha1
kind: ToolSet
metadata:
  name: petstore-api
  namespace: tenant-acme
spec:
  displayName: Petstore API
  openAPISpec:
    url: https://petstore.swagger.io/v2/swagger.json
  selector:
    tags: [pet, store]
  toolDefaults:
    timeout: 30s
```

## Development

### Run Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=src --cov-report=term-missing

# Specific module
pytest tests/test_k8s.py -v
```

### Code Quality

```bash
# Linting
ruff check src tests

# Type checking
mypy src
```

## Related Documentation

- [STOA Platform](../README.md)
- [Demo MCP Tools](../deploy/demo-tools/README.md) - Multi-tenant isolation demo
- [MCP Specification](https://modelcontextprotocol.io/)
- [CHANGELOG](../CHANGELOG.md)

## License

MIT - STOA Platform
