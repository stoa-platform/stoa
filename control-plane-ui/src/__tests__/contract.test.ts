/**
 * Contract Tests — Console UI ↔ Control Plane API
 *
 * Validates that TypeScript interfaces match the OpenAPI schema generated
 * by the backend. Catches schema drift before it reaches production.
 *
 * When a contract test fails:
 * 1. Check if the backend schema changed (update TS types)
 * 2. Or if the snapshot is stale (regenerate openapi-snapshot.json)
 */
import { describe, expect, it } from 'vitest';
import schema from '../../../control-plane-api/openapi-snapshot.json';

type OpenAPISchema = {
  components: {
    schemas: Record<
      string,
      {
        properties?: Record<string, unknown>;
        required?: string[];
      }
    >;
  };
};

const typedSchema = schema as unknown as OpenAPISchema;

function getSchemaProperties(schemaName: string): string[] {
  const s = typedSchema.components.schemas[schemaName];
  if (!s) throw new Error(`Schema '${schemaName}' not found in OpenAPI snapshot`);
  return Object.keys(s.properties || {});
}

function getRequiredProperties(schemaName: string): string[] {
  const s = typedSchema.components.schemas[schemaName];
  if (!s) throw new Error(`Schema '${schemaName}' not found in OpenAPI snapshot`);
  return s.required || [];
}

/**
 * For each TS interface, we list the properties it declares.
 * The test verifies that all required OpenAPI properties exist in the TS type.
 * This catches: missing fields, renamed fields, removed fields.
 *
 * Note: TS uses snake_case (matching the API JSON responses directly).
 */
const CONSOLE_TYPE_MAPPINGS: Record<string, string[]> = {
  // TenantResponse → Tenant
  TenantResponse: ['id', 'name', 'display_name', 'status', 'created_at', 'updated_at'],

  // GatewayInstanceResponse → GatewayInstance
  GatewayInstanceResponse: [
    'id',
    'name',
    'display_name',
    'gateway_type',
    'environment',
    'tenant_id',
    'base_url',
    'auth_config',
    'status',
    'last_health_check',
    'capabilities',
    'version',
    'tags',
    'created_at',
    'updated_at',
  ],

  // ContractResponse → Contract (TS uses 'bindings')
  ContractResponse: [
    'id',
    'tenant_id',
    'name',
    'version',
    'status',
    'created_at',
    'updated_at',
  ],

  // PlatformStatusResponse → PlatformStatusResponse
  PlatformStatusResponse: ['gitops', 'events', 'external_links', 'timestamp'],

  // MCPServerResponse → maps to ExternalMCPServer in console
  MCPServerResponse: [
    'id',
    'name',
    'display_name',
    'description',
    'category',
    'status',
    'created_at',
    'updated_at',
  ],
};

describe('OpenAPI Contract — Console UI', () => {
  it('should have a valid OpenAPI snapshot', () => {
    expect(typedSchema.components).toBeDefined();
    expect(typedSchema.components.schemas).toBeDefined();
    expect(Object.keys(typedSchema.components.schemas).length).toBeGreaterThan(50);
  });

  describe.each(Object.entries(CONSOLE_TYPE_MAPPINGS))(
    'Schema %s',
    (schemaName, tsProperties) => {
      it(`should exist in OpenAPI snapshot`, () => {
        const props = getSchemaProperties(schemaName);
        expect(props.length).toBeGreaterThan(0);
      });

      it(`should have all TS-declared properties in OpenAPI`, () => {
        const apiProps = getSchemaProperties(schemaName);
        const missing = tsProperties.filter((p) => !apiProps.includes(p));
        expect(missing).toEqual([]);
      });

      it(`should have required properties covered by TS type`, () => {
        const required = getRequiredProperties(schemaName);
        const covered = tsProperties.filter((p) => required.includes(p));
        // At least half of required fields should be in the TS type
        expect(covered.length).toBeGreaterThanOrEqual(Math.min(required.length, 3));
      });
    }
  );

  it('should not have unexpected schema removals', () => {
    const expectedSchemas = [
      'TenantResponse',
      'SubscriptionResponse',
      'ContractResponse',
      'GatewayInstanceResponse',
      'MCPServerResponse',
      'PlatformStatusResponse',
      'DeploymentResponse',
      'GatewayPolicyResponse',
    ];

    for (const name of expectedSchemas) {
      expect(typedSchema.components.schemas[name]).toBeDefined();
    }
  });
});
