# STOA Platform — Pattern Library

Reusable architectural patterns used across the codebase.

## Patterns

### Repository Pattern
**Used in**: `control-plane-api/src/repositories/`
- Separate data access logic from business logic
- Each model gets a repository with CRUD operations
- Async SQLAlchemy sessions injected via FastAPI `Depends()`

### Adapter Pattern (ADR-027)
**Used in**: `control-plane-api/src/adapters/`
- Abstract gateway integrations behind a common interface
- Implementations: webMethods, STOA native, template
- Registry pattern to select adapter by gateway type

### Tool Registry Pattern
**Used in**: `mcp-gateway/src/services/tool_registry/`
- Dynamic tool registration from multiple sources (CRDs, database, config)
- 7 submodules: registration, invocation, lookup, core_routing, external, proxied, action_handlers
- Separates tool definition from tool execution

### Event-Driven Pattern
**Used in**: Kafka/Redpanda metering pipeline
- Producers: mcp-gateway (tool calls, metering events)
- Consumers: control-plane-api (usage tracking, sync)
- Topic conventions: `stoa.metering.events`, `stoa.audit.events`
- All consumers are idempotent (safe to replay)

### OPA Policy Enforcement
**Used in**: `mcp-gateway/src/policy/`
- Embedded OPA evaluator for fine-grained RBAC
- Policies defined per-tenant, per-tool
- Argument-level filtering via `argument_engine.py`

### Persona-Based E2E Testing
**Used in**: `e2e/`
- Pre-authenticated storage states per persona
- Gherkin BDD features as source of truth
- Ready Player One theme for tenant/user naming
