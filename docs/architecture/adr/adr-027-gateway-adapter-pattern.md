# ADR-027: Gateway Adapter Pattern

## Status

Accepted

## Date

2026-01-30

## Context

STOA Platform needs to orchestrate API gateway operations (API lifecycle, policy management, OIDC configuration, application provisioning) as part of its GitOps pipeline. The current implementation directly integrates with webMethods API Gateway via its REST Admin API.

**Technical lock (verrou technique)**: No existing solution provides declarative, idempotent reconciliation of a proprietary API gateway (webMethods) via REST API with:
- Desired state management (Git as source of truth)
- Observed state comparison (gateway runtime)
- Bidirectional conflict resolution (GitOps declarations + runtime provisioning from CAB-800)
- Convergence guarantees

There is no Terraform provider, Kubernetes operator, or ArgoCD plugin for webMethods API Gateway. The same gap exists for many enterprise gateways.

## Decision

Introduce the **Gateway Adapter Pattern**: an abstract Python interface (`GatewayAdapterInterface`) that defines the contract for gateway orchestration. Each supported gateway provides a concrete adapter implementation.

### Architecture

```
GatewayAdapterInterface (ABC)
├── WebMethodsGatewayAdapter     ← First implementation
├── KongGatewayAdapter           ← Planned
├── ApigeeGatewayAdapter         ← Planned
└── AWSApiGatewayAdapter         ← Planned
```

### Interface Operations

The interface covers 7 resource domains: APIs, Policies, Applications, Auth/OIDC, Aliases, Configuration, and Backup.

All operations return `AdapterResult(success, resource_id, data, error)` and must be idempotent.

### Integration Points

1. **Provisioning Service** (CAB-800): Uses the adapter for runtime application provisioning
2. **Ansible Reconciliation**: Uses gateway REST API directly (could be refactored to use adapter via CLI)
3. **Control Plane API**: Exposes gateway status through subscription provisioning state

## Consequences

### Positive

- **Gateway-agnostic**: STOA can orchestrate any gateway that implements the interface
- **Testable**: Abstract interface enables mock adapters for testing
- **Extensible**: New gateways can be added without modifying core reconciliation logic
- **CIR-eligible**: The pattern and its first implementation constitute original research (no prior art for declarative webMethods orchestration)

### Negative

- **Indirection**: One more layer between the service and the gateway API
- **Impedance mismatch**: Some gateway-specific features may not map cleanly to the abstract interface
- **Maintenance**: Each adapter must be maintained and tested independently

### Risks

- Gateway REST APIs may change between versions (mitigated by version-specific mappers)
- Complex multi-step operations (e.g., OIDC setup) may need gateway-specific sequencing

## Research Context (CIR)

This work addresses a novel technical problem: **declarative reconciliation of proprietary API gateways**. Key indicators:

1. **No prior art**: No Terraform provider, K8s operator, or declarative tool exists for webMethods API Gateway
2. **Bidirectional state management**: Reconciling Git-declared state with runtime-provisioned state (CAB-800)
3. **Reusable abstraction**: The adapter pattern is applicable to any gateway vendor
4. **Potential publication**: "Declarative Reconciliation of Proprietary API Gateways via Abstract Adapter Pattern"
