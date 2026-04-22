/**
 * Auto-generated API types from control-plane-api OpenAPI spec.
 *
 * Source of truth for backend wire formats. Re-exported here so apps
 * (control-plane-ui, portal) can `import type { components } from
 * '@stoa/shared/api-types'` and address schemas via
 * `components['schemas']['XxxResponse']`.
 *
 * For convenience the `Schemas` and `Operations` aliases are also exported.
 *
 * Regenerate: `cd shared && npm run generate:api-types`
 * Drift gate: `cd shared && npm run check:api-types` (CI: api-contract-check.yml)
 */
export type { paths, components, operations } from './generated';

import type { components, operations } from './generated';

/** Convenience alias: `Schemas['TenantResponse']` etc. */
export type Schemas = components['schemas'];

/** Convenience alias: `Operations['list_tenants']` etc. */
export type Operations = operations;
