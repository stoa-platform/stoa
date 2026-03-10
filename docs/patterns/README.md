# STOA Platform — Pattern Library

Reusable architectural patterns used across the codebase.

## Patterns

### Repository Pattern
**Used in**: `control-plane-api/src/repositories/`
- Separate data access logic from business logic
- Each model gets a repository with CRUD operations
- Async SQLAlchemy sessions injected via FastAPI `Depends()`

### Adapter Pattern (ADR-035)
**Used in**: `control-plane-api/src/adapters/`
- Abstract gateway integrations behind a common interface
- Implementations: webMethods, STOA native, template
- Registry pattern to select adapter by gateway type

### Tool Registry Pattern
**Used in**: `stoa-gateway/src/tools/`
- Dynamic tool registration from multiple sources (CRDs, database, config)
- Separates tool definition from tool execution

### Event-Driven Pattern
**Used in**: Kafka/Redpanda metering pipeline
- Producers: stoa-gateway (tool calls, metering events)
- Consumers: control-plane-api (usage tracking, sync)
- Topic conventions: `stoa.metering.events`, `stoa.audit.events`
- All consumers are idempotent (safe to replay)

### OPA Policy Enforcement
**Used in**: `stoa-gateway/src/policy/`
- Fine-grained RBAC for tool access
- Policies defined per-tenant, per-tool

### Persona-Based E2E Testing
**Used in**: `e2e/`
- Pre-authenticated storage states per persona
- Gherkin BDD features as source of truth
- Ready Player One theme for tenant/user naming
