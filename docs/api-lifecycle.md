# API Lifecycle

This document describes the canonical lifecycle path implemented in the
control-plane API. Draft, validation, gateway deployment, portal publication,
and environment promotion are all orchestrated through `ApiLifecycleService`.

## Canonical Models

- `APICatalog`: API identity, catalog metadata, catalog status, and OpenAPI
  contract cache.
- `GatewayDeployment`: runtime gateway desired/actual state per gateway.
- `Promotion`: explicit transition between environments.
- `AuditEvent`: immutable lifecycle transition trace.

`APICatalog.status` is only the catalog state. Runtime deployment, portal
publication, and promotion state are aggregated by the lifecycle endpoint from
their own canonical models.

## States

Implemented:

- `draft`: catalog entry exists, may contain an inline OpenAPI spec or a spec
  reference, and has not been validated for deployment.
- `ready`: draft validation succeeded. This is only a catalog readiness state;
  it does not mean deployed, published, or promoted.
- `deployed`: aggregate lifecycle phase when at least one `GatewayDeployment`
  is synced. The catalog status remains `ready`.
- `published`: aggregate lifecycle phase when a synced gateway deployment has
  been explicitly published to the portal.
- `promoting`: an environment promotion is pending or running.
- `promoted`: promotion has completed.
- `failed`: catalog validation, gateway sync, portal publication, or promotion
  failed with an explicit error.
- `archived`: catalog entry is no longer active.

## Endpoints

### Create Draft

`POST /v1/tenants/{tenant_id}/apis/lifecycle/drafts`

Creates an `APICatalog` row with `status=draft`, `portal_published=false`, and
an audit event `api_lifecycle.create_draft`. The request must provide either an
inline OpenAPI/Swagger document or a `spec_reference`.

Minimal body:

```json
{
  "name": "Payments API",
  "display_name": "Payments API",
  "version": "1.0.0",
  "description": "Payment operations",
  "backend_url": "https://payments.internal",
  "openapi_spec": {
    "openapi": "3.0.3",
    "info": {"title": "Payments API", "version": "1.0.0"},
    "paths": {
      "/payments": {
        "get": {"responses": {"200": {"description": "ok"}}}
      }
    }
  }
}
```

Portal publication tags such as `portal:published` are rejected on this path.
Publication must go through the lifecycle publish action.

### Get Lifecycle State

`GET /v1/tenants/{tenant_id}/apis/{api_id}/lifecycle`

Returns the aggregate lifecycle state calculated from `APICatalog`,
`GatewayDeployment`, and `Promotion`. A newly created draft has empty
`deployments` and `promotions` arrays.

### Validate Draft

`POST /v1/tenants/{tenant_id}/apis/{api_id}/lifecycle/validate`

Validates the persisted OpenAPI/Swagger contract and transitions the catalog
state from `draft` to `ready`. A `ready` API can be revalidated idempotently
when the spec has not changed. `archived` APIs and other non-draft/non-ready
catalog states are refused with a transition error.

Minimal validation rules:

- OpenAPI 3.x via `openapi` is supported.
- Swagger 2.0 via `swagger` is supported.
- The spec must be a JSON/YAML object.
- `info.title` is required.
- `info.version` is required.
- `paths` is required and cannot be empty.
- Every path key must start with `/`.
- Every HTTP operation must declare a non-empty `responses` object.

If the draft only contains `spec_reference`, validation currently returns
`spec_reference_unresolved` and keeps `APICatalog.status=draft`. No existing
control-plane service resolves arbitrary lifecycle spec references reliably yet.

Successful response shape:

```json
{
  "tenant_id": "acme",
  "api_id": "payments-api",
  "status": "ready",
  "validation": {
    "valid": true,
    "code": "validated",
    "spec_source": "inline",
    "spec_format": "openapi",
    "spec_version": "3.0.3",
    "path_count": 1,
    "operation_count": 1
  },
  "lifecycle": {
    "catalog_status": "ready",
    "lifecycle_phase": "ready",
    "deployments": [],
    "promotions": []
  }
}
```

### Request Gateway Deployment

`POST /v1/tenants/{tenant_id}/apis/{api_id}/lifecycle/deployments`

Creates or updates a `GatewayDeployment` desired state for a target gateway.
This endpoint does not call a gateway directly and does not publish to the
portal. The `SyncEngine` is responsible for reconciling `pending` deployments
against the actual gateway.

Request body:

```json
{
  "environment": "dev",
  "gateway_instance_id": "optional-uuid",
  "force": false
}
```

Gateway resolution:

- If `gateway_instance_id` is provided, it must be visible to the tenant and
  match the requested environment.
- If it is omitted, exactly one enabled gateway visible to the tenant must
  exist for the environment.
- If no gateway matches, the request returns a clear not-found error.
- If more than one gateway matches, the request is ambiguous and must include
  `gateway_instance_id`.

Idempotence:

- Same API, same environment, same gateway, same desired state returns the
  existing `GatewayDeployment`.
- Existing `pending` or `syncing` rows are not duplicated.
- Existing `synced` rows are not reset to `pending` when the desired state is
  unchanged.
- A changed desired state updates the row, increments `desired_generation`, and
  sets `sync_status=pending`.

Successful response shape:

```json
{
  "tenant_id": "acme",
  "api_id": "payments-api",
  "environment": "dev",
  "gateway_instance_id": "00000000-0000-4000-8000-000000000001",
  "deployment_id": "00000000-0000-4000-8000-000000000002",
  "deployment_status": "pending",
  "action": "created",
  "lifecycle": {
    "catalog_status": "ready",
    "deployments": [
      {
        "environment": "dev",
        "gateway_name": "stoa-dev",
        "sync_status": "pending"
      }
    ],
    "promotions": []
  }
}
```

### Publish To Portal

`POST /v1/tenants/{tenant_id}/apis/{api_id}/lifecycle/publications`

Publishes a synced `GatewayDeployment` to the STOA portal. In the current portal
architecture, the portal catalog reads `APICatalog.portal_published`, so the
lifecycle adapter updates that field and records the target publication context
under `api_metadata.lifecycle.portal_publications`. This is the only active HTTP
path that may publish an API to the portal.

Request body:

```json
{
  "environment": "dev",
  "gateway_instance_id": "optional-uuid",
  "force": false
}
```

Rules:

- The API catalog status must be `ready`.
- A matching `GatewayDeployment` must already exist.
- The matching deployment must be `synced`.
- Gateway resolution follows the same tenant/environment rules as deployment.
- Publication never creates a deployment and never mutates
  `APICatalog.status`.
- `APICatalog.openapi_spec` must be present and valid. A `spec_reference`
  without a resolved spec is refused with `spec_reference_unresolved`.
- Repeating the same publication with the same deployment and spec hash returns
  `result=unchanged`.
- `force=true` reruns the controlled publication adapter and records
  `result=republished` without creating duplicate publication records.

Successful response shape:

```json
{
  "tenant_id": "acme",
  "api_id": "payments-api",
  "environment": "dev",
  "gateway_instance_id": "00000000-0000-4000-8000-000000000001",
  "deployment_id": "00000000-0000-4000-8000-000000000002",
  "publication_status": "published",
  "portal_published": true,
  "result": "published",
  "lifecycle": {
    "catalog_status": "ready",
    "lifecycle_phase": "published",
    "portal": {
      "published": true,
      "status": "published",
      "last_environment": "dev"
    },
    "promotions": []
  }
}
```

Legacy API create/update endpoints reject `portal:published`,
`promoted:portal`, and `portal-promoted` tags with `422`. Tags are no longer a
publication mechanism; publication must use the lifecycle endpoint above.
Catalog sync, GitOps projection, and admin seed paths strip those legacy tags
from imported tags and insert new catalog rows with `portal_published=false`.
On update they preserve existing portal publication state instead of deriving
it from Git. They also preserve the lifecycle-owned
`api_metadata.lifecycle` subtree, including `portal_publications`, while
refreshing Git-projected metadata fields.

### Promote To Environment

`POST /v1/tenants/{tenant_id}/apis/{api_id}/lifecycle/promotions`

Promotes an API from a published, synced source environment to the next allowed
environment and requests the target `GatewayDeployment`. This endpoint owns the
promotion execution path. Legacy promotion approval no longer deploys directly
and no longer emits a `promotion-approved` deploy command; the legacy consumer
ignores repeated `promotion-approved` events to avoid double deployment.

Request body:

```json
{
  "source_environment": "dev",
  "target_environment": "staging",
  "source_gateway_instance_id": "optional-uuid",
  "target_gateway_instance_id": "optional-uuid",
  "force": false
}
```

Rules:

- The API catalog status must be `ready`.
- The source and target environments must be different and follow the allowed
  chain: `dev -> staging` or `staging -> production`.
- The source gateway deployment must exist and be `synced`.
- The source deployment must have been published through the lifecycle
  publication endpoint.
- The target gateway is resolved with the same tenant/environment rules as
  deployment and publication.
- Promotion creates or reuses one `Promotion` row and creates or reuses one
  target `GatewayDeployment`.
- Promotion never creates a legacy `Deployment` and never mutates
  `APICatalog.status`.
- Repeating the same promotion returns `result=unchanged` and does not create a
  second `Promotion` or target `GatewayDeployment`.
- The promotion remains `promoting` until the target deployment is synced and
  the target environment is published through the controlled publication
  endpoint. That target publication marks the promotion `promoted`.

Successful response shape:

```json
{
  "tenant_id": "acme",
  "api_id": "payments-api",
  "promotion_id": "00000000-0000-4000-8000-000000000003",
  "source_environment": "dev",
  "target_environment": "staging",
  "source_gateway_instance_id": "00000000-0000-4000-8000-000000000001",
  "target_gateway_instance_id": "00000000-0000-4000-8000-000000000004",
  "target_deployment_id": "00000000-0000-4000-8000-000000000005",
  "promotion_status": "promoting",
  "deployment_status": "pending",
  "result": "requested",
  "lifecycle": {
    "catalog_status": "ready",
    "lifecycle_phase": "promoting"
  }
}
```

## Legacy Deployment Hardening

The lifecycle path is the only write path for lifecycle-managed APIs. A catalog
row is lifecycle-managed when `api_metadata.lifecycle` is present. For those
APIs:

- legacy `POST /v1/tenants/{tenant_id}/deployments` returns `409` and points to
  `POST /v1/tenants/{tenant_id}/apis/{api_id}/lifecycle/deployments`.
- legacy deployment rollback and status writes return `409`.
- `DeploymentService` refuses to create, rollback, or update legacy
  `Deployment` rows.
- `GatewayDeploymentService.deploy_api()` refuses direct/admin deploys and does
  not reset an unchanged existing `GatewayDeployment` to `pending`.
- `GatewayDeploymentService.undeploy()` and `force_sync()` refuse lifecycle
  deployments.
- `DeploymentOrchestrationService.deploy_api_to_env()` refuses lifecycle APIs,
  and promotion auto-deploy skips lifecycle-managed APIs.

Read-only legacy deployment queries may still return historical `Deployment`
records. They are not the runtime source of truth for lifecycle APIs.
`GatewayDeployment` remains the runtime source of truth.

## DB Persistence Checks

The JSONB persistence checks are integration tests and require a real
PostgreSQL database URL. Without `DATABASE_URL`, they skip automatically.

Run them with:

```bash
cd /Users/torpedo/hlfh-repos/stoa/control-plane-api
DATABASE_URL=<postgresql+asyncpg-url> pytest \
  tests/test_api_lifecycle_publish_db.py \
  tests/services/catalog_reconciler/test_projection_db.py \
  -q
```

These tests verify that controlled portal publication survives commit/reload
and that GitOps/catalog projection updates preserve lifecycle-owned metadata.

## Console UI

The Console exposes a minimal lifecycle flow on the existing API surfaces:

- `APIs` creates new lifecycle drafts through
  `POST /v1/tenants/{tenant_id}/apis/lifecycle/drafts`.
- API detail loads `GET /v1/tenants/{tenant_id}/apis/{api_id}/lifecycle`.
- The API detail lifecycle panel can validate, deploy, publish, and promote
  through the canonical lifecycle endpoints.
- After every lifecycle action the panel refreshes aggregate state from the
  backend instead of assuming an optimistic status.
- Gateway IDs remain optional in the UI. If the backend reports no gateway or
  ambiguous gateway selection, the backend error is shown directly.
- Legacy portal publication tags are stripped from UI create/update payloads.
  The detail page no longer exposes a portal tag toggle.
- The API list links to the API detail lifecycle panel instead of opening the
  legacy deployment workflow for this flow.

The Console keeps local TypeScript lifecycle types in
`control-plane-ui/src/services/api/apiLifecycle.ts`. Shared generated API types
are not regenerated for this UI slice.

## Slice 1 Scenario

1. Create draft through `POST /lifecycle/drafts`.
2. Store the parsed inline OpenAPI/Swagger object in `APICatalog.openapi_spec`,
   or store a required spec reference in catalog metadata.
3. Read state through `GET /{api_id}/lifecycle`.
4. Confirm `catalog_status=draft`, `lifecycle_phase=draft`, and no gateway or
   portal side effect.

## Slice 2 Scenario

1. Create draft through `POST /lifecycle/drafts` with a valid inline OpenAPI 3.x
   or Swagger 2.0 document.
2. Validate through `POST /{api_id}/lifecycle/validate`.
3. Confirm `status=ready`, `validation.valid=true`, and
   `lifecycle.catalog_status=ready`.
4. Confirm `deployments` remains empty; no gateway runtime state is invented in
   this slice.

## Slice 3 Scenario

1. Create draft through `POST /lifecycle/drafts`.
2. Validate through `POST /{api_id}/lifecycle/validate`.
3. Deploy through `POST /{api_id}/lifecycle/deployments` with
   `environment=dev`.
4. Confirm `APICatalog.status` remains `ready`.
5. Confirm `GET /{api_id}/lifecycle` contains a `GatewayDeployment` entry and
   still has no portal publication or promotion state.

## Slice 4 Scenario

1. Create draft through `POST /lifecycle/drafts`.
2. Validate through `POST /{api_id}/lifecycle/validate`.
3. Deploy through `POST /{api_id}/lifecycle/deployments`.
4. Let the sync engine, or a test fake, mark the `GatewayDeployment` as
   `synced`.
5. Publish through `POST /{api_id}/lifecycle/publications`.
6. Confirm `APICatalog.status=ready`, `portal.published=true`, the deployment
   remains `synced`, and `promotions=[]`.

## Slice 5 Scenario

1. Create draft through `POST /lifecycle/drafts`.
2. Validate through `POST /{api_id}/lifecycle/validate`.
3. Deploy dev through `POST /{api_id}/lifecycle/deployments`.
4. Let the sync engine, or a test fake, mark the dev `GatewayDeployment` as
   `synced`.
5. Publish dev through `POST /{api_id}/lifecycle/publications`.
6. Promote dev to staging through `POST /{api_id}/lifecycle/promotions`.
7. Confirm the promotion is `promoting` and a staging `GatewayDeployment` was
   requested with `sync_status=pending`.
8. Let the sync engine, or a test fake, mark the staging deployment as
   `synced`.
9. Publish staging through `POST /{api_id}/lifecycle/publications`.
10. Confirm `APICatalog.status=ready`, source and target deployments are
    visible, target portal publication is visible, and the promotion is
    `promoted`.

## Slice 6 Scenario

1. Run the full lifecycle scenario from Slice 5.
2. Attempt legacy `POST /v1/tenants/{tenant_id}/deployments` for the same API.
3. Confirm the response is `409` and no legacy `Deployment` row is created.
4. Attempt direct `GatewayDeploymentService.deploy_api()` for the same API.
5. Confirm the operation is rejected before creating or mutating runtime state.
6. Repeat a lifecycle deployment with unchanged desired state.
7. Confirm an existing `synced` `GatewayDeployment` is returned unchanged and
   is not reset to `pending`.
