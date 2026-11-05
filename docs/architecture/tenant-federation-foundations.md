# Tenant and federation foundations

This Phase 0 index is for contributors assessing multi-tenant and federation
readiness. It links decisions to existing repository evidence; it is not a
runtime readiness certification or a new product contract.

Baseline: `stoa` main at `1c99a76d0345356ce16d0b20aade2c61e1fc8c21`,
reviewed on 2026-11-05. ADR and glossary references were checked against
`stoa-docs` main at `b5493383689596d50da29e076791115358e8010b`.

## Read decisions before implementation

- [ADR-074: Tenant Model](https://docs.gostoa.dev/docs/architecture/adr/adr-074-tenant-model)
  is **Accepted** and supersedes ADR-026. The delivered identity model uses one
  application realm (default `stoa`), one group per tenant and a `tenant_id`
  claim. Group membership alone does not assign the claim; the user attribute
  supplies it. Roles do not identify tenants.
- [ADR-026: Multi-IAM Federation](https://docs.gostoa.dev/docs/architecture/adr/adr-026-multi-iam-federation)
  is **Superseded**. Its realm-per-organization model, `stoa_realm` claim and
  zero-user-storage goal must not be treated as delivered platform behavior.
  [Demo scripts](../../scripts/demo-federation/) and the
  [demo stack](../../deploy/demo-federation/) preserve that historical experiment.
- [ADR-046: MCP Federation](https://docs.gostoa.dev/docs/architecture/adr/adr-046-mcp-federation-architecture)
  is **Draft**. Use it as design context for master/sub-accounts, not as an
  accepted authorization to implement partner or cross-IdP federation.

## Vocabulary and reading cautions

| Term | Reference and interpretation for this baseline |
|------|-----------------------------------------------|
| Tenant | [Glossary: T](https://docs.gostoa.dev/docs/reference/glossary#t). Use ADR-074 for identity boundaries: the glossary still says each tenant has its own realm. |
| Multi-tenancy and isolation | [Glossary: M](https://docs.gostoa.dev/docs/reference/glossary#m) and [I](https://docs.gostoa.dev/docs/reference/glossary#i). The [concept guide](https://docs.gostoa.dev/docs/concepts/multi-tenant) describes isolation layers; their presence in a guide is not deployment evidence. |
| Tenant identifier | [Tenant model](../../control-plane-api/src/models/tenant.py): `id` is the slug-style primary key; `uuid` is a separate stable identity. Do not infer a change to token or route identifiers from that column. |
| MCP federation | [Federation model](../../control-plane-api/src/models/federation.py): master accounts own developer/agent sub-accounts within a tenant. This is distinct from identity provider brokering. |
| Identity federation | ADR-026's historical pattern. ADR-074 explicitly leaves organizational identity brokering unverified. |

## Existing control plane entry points

These are source navigation pointers to registered routes, not instructions to
call them. Review the routers and their tests for current access checks,
responses and failure cases. This index does not broaden their permissions.

| Area | Existing routes | Source and checks |
|------|-----------------|-------------------|
| Tenant lifecycle | `GET/POST /v1/tenants`; `GET/PUT/DELETE /v1/tenants/{tenant_id}` | [Tenant router](../../control-plane-api/src/routers/tenants.py), [router tests](../../control-plane-api/tests/test_tenants_router.py), [administration guards](../../control-plane-api/tests/test_tenant_administration_guards.py) |
| Tenant operations | `GET /v1/tenants/{tenant_id}/usage`, `/provisioning-status`, `/export`; `POST /v1/tenants/{tenant_id}/import` | [Tenant router](../../control-plane-api/src/routers/tenants.py), [provisioning service](../../control-plane-api/src/services/tenant_provisioning_service.py), [disaster recovery tests](../../control-plane-api/tests/test_tenant_dr.py) |
| MCP federation accounts | `/v1/tenants/{tenant_id}/federation/accounts` and nested sub-account routes | [Federation router](../../control-plane-api/src/routers/federation.py), [router tests](../../control-plane-api/tests/test_federation_router.py), [tenant guard tests](../../control-plane-api/tests/test_federation_tenant_guards.py) |

Both routers are registered in [the API application](../../control-plane-api/src/main.py).
The [CLI endpoint map](../../.claude/context/cli-reference.md)
also points to the existing tenant operations. The
[tenant claim mapper runbook](../runbooks/tenant-id-mapper.md) records operational
checks and reconciliation limits; this index does not authorize applying them.

## Phase 0 non-goals

This documentation slice does not:

- add or change tenant APIs, provisioning, permissions, claims or token exchange;
- introduce realm-per-tenant support, partner trust, identity brokering or a
  cross-tenant access model;
- implement ADR-046's draft design, gateway routing, federation synchronization,
  caches, quotas or metering;
- enable a Helm value, deploy infrastructure, run the federation demo or change
  a realm, client, user, group or secret;
- certify live tenant isolation or claim that every deployment implements the
  isolation layers described in the concept guide.

Future implementation work needs its own bounded scope and evidence. An
existing route, a demo or a draft ADR is not proof of end-to-end federation
readiness.
