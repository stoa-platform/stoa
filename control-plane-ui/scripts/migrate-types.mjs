#!/usr/bin/env node
// One-shot codemod: rewrite UI type imports from `../types` to
// `@stoa/shared/api-types` for types that are pure DUPLIQUÉs of an
// OpenAPI schema (no drift, no enrichment).
//
// AST-based via the TypeScript compiler API — safer than regex because we
// only touch type-reference positions, not string literals/JSX/comments.
//
// Manifest = MIGRATIONS map below. Maps the manual type name (as used in
// `from '../types'`) to the OpenAPI schema name (in `Schemas[...]`).
// When the two names are identical we still list it so the script keeps
// the rewrite explicit and reviewable.
//
// Usage:
//   node scripts/migrate-types.mjs           # apply to all src/**
//   node scripts/migrate-types.mjs --dry     # show what would change
//   node scripts/migrate-types.mjs <file>    # one file only
//
// After run: `npx tsc -p tsconfig.app.json --noEmit` then `npm test`.
//
// DELETION CRITERIA (sunset this script when ALL true):
//   1. UI-1-Wave2 ticket merged (covers ~150 cascading wrappers)
//   2. Backend BUG-1, BUG-2, BUG-4 resolved upstream (REWRITE-BUGS.md)
//   3. `grep -r "Schemas\['" src/` confirms all DUPLIQUÉs come from
//      @stoa/shared/api-types (no manual re-declarations remain)
//
// Owner of deletion: whoever closes UI-1-Wave2.

import { readFileSync, writeFileSync, statSync } from 'node:fs';
import { argv, exit } from 'node:process';
import { join, dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';
import ts from 'typescript';

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = resolve(__dirname, '..', 'src');

// ---- MIGRATION MANIFEST -----------------------------------------------------
// `manualName: 'GeneratedSchemaName'`. Identity entries (`Foo: 'Foo'`) mean
// the OpenAPI schema has the same name as the manual type. Different names
// indicate the OpenAPI suffix convention (`Response`, `Detail`, etc.).
//
// ONLY include types verified as DUPLIQUÉ — same shape, no UI enrichment.
// DRIFT and UI-only types live in src/types/index.ts permanently.
const MIGRATIONS = {
  // Pilot types (already done in mcpConnectorsApi.ts — listed here so the
  // codemod re-applies after a checkout/revert).
  AuthorizeResponse: 'AuthorizeResponse',
  CallbackResponse: 'CallbackResponse',
  PromoteResponse: 'PromoteResponse',

  // ── Pure leaves: no nested entity refs, no setState cascade risk ──
  APIVersionEntry: 'APIVersionEntry',
  BulkRevokeResponse: 'BulkRevokeResponse',
  BulkActionFailure: 'BulkActionFailure',
  BulkActionResult: 'BulkActionResult',
  BulkSubscriptionAction: 'BulkSubscriptionAction',
  CompanyStats: 'CompanyStats',
  ApprovalStepDef: 'ApprovalStepDef',
  CSRSignResponse: 'CSRSignResponse',
  TestConnectionResponse: 'TestConnectionResponse',
  SyncToolsResponse: 'SyncToolsResponse',
  WebhookTestResponse: 'WebhookTestResponse',
  SyncResponse: 'SyncResponse',
  DeploymentStatusSummary: 'DeploymentStatusSummary',
  GatewayHealthCheckResponse: 'GatewayHealthCheckResponse',
  GatewayBindingInfo: 'GatewayBindingInfo',
  CertificateExpiryItem: 'CertificateExpiryItem',
  CertificateExpiryResponse: 'CertificateExpiryResponse',
  TenantToolPermissionCreate: 'TenantToolPermissionCreate',
  FederationBulkRevokeResponse: 'FederationBulkRevokeResponse',

  // ── Request types (no return-flow cascade) ──
  WebhookCreate: 'WebhookCreate',
  WebhookUpdate: 'WebhookUpdate',
  CredentialMappingCreate: 'CredentialMappingCreate',
  CredentialMappingUpdate: 'CredentialMappingUpdate',
  ContractUpdate: 'ContractUpdate',
  PromotionCreate: 'PromotionCreate',
  PromotionRollbackRequest: 'PromotionRollbackRequest',
  PromotionDiffResponse: 'PromotionDiffResponse',
  BackendApiCreate: 'BackendApiCreate',
  BackendApiUpdate: 'BackendApiUpdate',
  SaasApiKeyCreate: 'SaasApiKeyCreate',
  SaasApiKeyCreatedResponse: 'SaasApiKeyCreatedResponse',
  MasterAccountCreate: 'MasterAccountCreate',
};

// Types we leave alone (DRIFT, UI-only, or wrong schema name in OpenAPI).
// Listed here for reference — the codemod simply doesn't touch any name not
// in MIGRATIONS. Phase 4 (DRIFT resolution) will revisit some of these.
const SKIP_REASON = {
  // ── Wrong schema names (no `components.schemas[X]` in generated.ts) ──
  IssuedCertificate: 'BUG-? — no schema, only IssuedCertificate in inline?',
  TenantCAInfo: 'BUG-? — no schema named this',
  ErrorSnapshotFilters: 'BUG-? — filters are query params, no schema',
  SnapshotFiltersResponse: 'BUG-? — no schema named this',
  AggregatedMetrics: 'BUG-? — no schema named this',
  GeneratedBinding: 'BUG-? — no schema named this',
  ExternalMCPServerCredentials: 'BUG-? — no schema named this',

  // ── Wrappers cascading into DRIFT inner entities — defer to Phase 4 ──
  IssuedCertificateListResponse: 'cascade: inner IssuedCertificate missing',
  ContractListResponse: 'cascade: Contract is DRIFT',
  BackendApiListResponse: 'cascade: BackendApi is DRIFT',
  SaasApiKeyListResponse: 'cascade: SaasApiKey is DRIFT',
  MasterAccountListResponse: 'cascade: MasterAccount is DRIFT',
  SubAccountListResponse: 'cascade: SubAccount is DRIFT',
  ExternalMCPServerListResponse: 'cascade: ExternalMCPServer is DRIFT',
  CredentialMappingListResponse: 'cascade: CredentialMapping is DRIFT',
  TenantToolPermissionListResponse: 'cascade: TenantToolPermission DRIFT',

  // ── Field mismatches found in first codemod run ──
  ContractCreate: 'DRIFT — UI has status?, generated lacks it',
  AccessRequestDetail: 'DRIFT — status: string (wire) vs AccessRequestStatus (UI narrowed enum)',
  AccessRequestListResponse: 'cascade: AccessRequestDetail status DRIFT',
  SubAccountCreate: 'DRIFT — UI sends description, generated lacks it',
  ExternalMCPServerCreate: 'DRIFT — description nullable mismatch',
  ExternalMCPServerUpdate: 'DRIFT — description nullable mismatch',
  ExternalMCPServerToolResponse: 'cascade: nested in ExternalMCPServer',
  ToolAllowListResponse: 'DRIFT — UI allowed_tools, gen tools',
  UsageSubAccountStat: 'DRIFT — UI total_requests, gen request_count',
  UsageResponse: 'cascade: UsageSubAccountStat DRIFT',
  ProtocolBindingResponse: 'cascade: nested in Contract DRIFT',
  ToolObservabilityItem: 'verify nesting in Phase 4',
  MasterAccountUpdate: 'verify cascade in Phase 4',
  OAuth2Credentials: 'leaf but only nested in ExternalMCPServerCredentials (missing schema)',

  // ── DRIFT entities (Phase 4 wire/UI separation) ──
  User: 'DRIFT — session-local, distinct from UserPermissionsResponse',
  Tenant: 'DRIFT — backend has more fields',
  TenantCreate: 'DRIFT — verify before migration',
  API: 'DRIFT — BUG-4 (missing created_at, audience, etc.)',
  APICreate: 'DRIFT — verify',
  Application: 'DRIFT — BUG-1 (no ApplicationResponse)',
  ApplicationCreate: 'DRIFT — verify',
  Consumer: 'DRIFT — backend has more fields',
  Deployment: 'DRIFT — verify',
  DeploymentCreate: 'DRIFT — verify',
  GatewayInstance: 'DRIFT — BUG-2 (missing enabled, source, visibility)',
  GatewayInstanceCreate: 'DRIFT — verify',
  GatewayInstanceUpdate: 'DRIFT — verify',
  Subscription: 'DRIFT — verify',
  Contract: 'DRIFT — verify (status union)',
  Promotion: 'DRIFT — verify',
  BackendApi: 'DRIFT — verify',
  SaasApiKey: 'DRIFT — verify',
  TenantWebhook: 'DRIFT — verify',
  WebhookDelivery: 'DRIFT — verify',
  CredentialMapping: 'DRIFT — verify',
  MasterAccount: 'DRIFT — verify',
  SubAccount: 'DRIFT — verify',
  AdminUser: 'DRIFT — verify',
  PlatformSetting: 'DRIFT — verify',
  ConnectorTemplate: 'DRIFT — has needs_setup, is_connected UI fields',
  ConnectorCatalogResponse: 'depends on ConnectorTemplate',
  WorkflowTemplate: 'DRIFT — verify',
  WorkflowInstance: 'DRIFT — verify',
  WorkflowTemplateListResponse: 'depends on WorkflowTemplate',
  WorkflowListResponse: 'depends on WorkflowInstance',
  AccessRequestStatus: 'DRIFT — UI-narrowed enum',
  ProspectSummary: 'DRIFT — verify',
  ProspectDetail: 'DRIFT — verify',
  Role: 'PUREMENT UI — RBAC enum',
  Permission: 'DRIFT — RolePermission inline (BUG-5)',
  RolePermission: 'PUREMENT UI — BUG-5 inline schema',
  RoleDefinition: 'depends on RolePermission',
  RoleListResponse: 'depends on RoleDefinition',
  Environment: 'PUREMENT UI — narrowed enum',
  EnvironmentMode: 'PUREMENT UI',
  EnvironmentEndpoints: 'PUREMENT UI — verify',
  EnvironmentConfig: 'PUREMENT UI — verify',
  CertificateStatus: 'PUREMENT UI — narrowed enum',
  TokenBindingMode: 'PUREMENT UI',
  DeployLogLevel: 'PUREMENT UI — narrowed enum',
  TraceStatus: 'PUREMENT UI — narrowed enum',
  TransactionStatus: 'PUREMENT UI — narrowed enum',
  ComponentHealth: 'PUREMENT UI — narrowed enum',
  GitOpsSyncStatus: 'PUREMENT UI — narrowed enum',
  GitOpsHealthStatus: 'PUREMENT UI — narrowed enum',
  PlatformEventSeverity: 'PUREMENT UI — narrowed enum',
  ExternalMCPTransport: 'PUREMENT UI — narrowed enum',
  ExternalMCPAuthType: 'PUREMENT UI — narrowed enum',
  ExternalMCPHealthStatus: 'PUREMENT UI — narrowed enum',
  GatewayType: 'PUREMENT UI — narrowed enum',
  GatewayMode: 'PUREMENT UI — narrowed enum',
  GatewayInstanceStatus: 'PUREMENT UI — narrowed enum',
  DeploymentStatus: 'PUREMENT UI — narrowed enum',
  DeploymentSyncStatus: 'PUREMENT UI — narrowed enum',
  PolicyType: 'PUREMENT UI — narrowed enum',
  PolicyScope: 'PUREMENT UI — narrowed enum',
  WorkflowType: 'PUREMENT UI — narrowed enum',
  WorkflowMode: 'PUREMENT UI — narrowed enum',
  WorkflowStatus: 'PUREMENT UI — narrowed enum',
  Sector: 'PUREMENT UI — narrowed enum',
  StepAction: 'PUREMENT UI — narrowed enum',
  FederationAccountStatus: 'PUREMENT UI — narrowed enum',
  AdminUserStatus: 'PUREMENT UI — narrowed enum',
  SettingCategory: 'PUREMENT UI — narrowed enum',
  ProspectStatus: 'PUREMENT UI — narrowed enum',
  NPSCategory: 'PUREMENT UI — narrowed enum',
  SnapshotTrigger: 'PUREMENT UI — narrowed enum',
  SnapshotResolutionStatus: 'PUREMENT UI — narrowed enum',
  SecurityProfile: 'DRIFT — verify (backend has SecurityProfile schema)',
  ProtocolType: 'PUREMENT UI — narrowed enum',
  ContractStatus: 'PUREMENT UI — narrowed enum',
  PromotionStatus: 'PUREMENT UI — narrowed enum',
  CredentialAuthType: 'PUREMENT UI — narrowed enum',
  WebhookEventType: 'PUREMENT UI — narrowed enum',
  WebhookDeliveryStatus: 'PUREMENT UI — narrowed enum',
  SubscriptionStatus: 'PUREMENT UI — narrowed enum',
  SaasApiKeyStatus: 'PUREMENT UI — narrowed enum',
  BackendApiAuthType: 'PUREMENT UI — narrowed enum',
  BackendApiStatus: 'PUREMENT UI — narrowed enum',
  Event: 'DRIFT — verify',
  CommitInfo: 'DRIFT — verify',
  MergeRequest: 'DRIFT — verify',
};

// ---- HELPERS ----------------------------------------------------------------

const TYPES_IMPORT_PATTERNS = ['../types', '../../types', '../../../types'];

function listSourceFiles(root) {
  const out = [];
  const walk = (dir) => {
    for (const entry of execSync(`ls -A "${dir}"`).toString().split('\n').filter(Boolean)) {
      const full = join(dir, entry);
      const st = statSync(full);
      if (st.isDirectory()) {
        if (entry === 'node_modules' || entry.startsWith('.')) continue;
        walk(full);
      } else if (full.endsWith('.ts') || full.endsWith('.tsx')) {
        out.push(full);
      }
    }
  };
  walk(root);
  return out;
}

function isFromTypesPath(node) {
  if (!ts.isImportDeclaration(node)) return false;
  if (!ts.isStringLiteral(node.moduleSpecifier)) return false;
  return TYPES_IMPORT_PATTERNS.includes(node.moduleSpecifier.text);
}

function processFile(filePath, dryRun) {
  const text = readFileSync(filePath, 'utf8');
  const sf = ts.createSourceFile(filePath, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);

  // Pass 1 — find the import from '../types' (if any) and classify names.
  let typesImport = null;
  for (const stmt of sf.statements) {
    if (isFromTypesPath(stmt)) {
      typesImport = stmt;
      break;
    }
  }
  if (!typesImport) return { changed: false, names: [] };

  const importClause = typesImport.importClause;
  if (!importClause || !importClause.namedBindings) return { changed: false, names: [] };
  if (!ts.isNamedImports(importClause.namedBindings)) return { changed: false, names: [] };

  const elements = importClause.namedBindings.elements;
  const toMigrate = [];
  const toKeep = [];
  for (const el of elements) {
    const name = el.name.text;
    if (Object.prototype.hasOwnProperty.call(MIGRATIONS, name)) {
      toMigrate.push({ manual: name, schema: MIGRATIONS[name] });
    } else {
      toKeep.push(name);
    }
  }
  if (toMigrate.length === 0) return { changed: false, names: [] };

  // Pass 2 — collect all type-reference identifiers to rewrite. Only inside
  // type positions (TypeReference, TypeQuery, TypeLiteral element types).
  const namesToRewrite = new Set(toMigrate.map((t) => t.manual));
  const replacements = []; // {start, end, text}

  function visit(node) {
    if (ts.isTypeReferenceNode(node) && ts.isIdentifier(node.typeName)) {
      const name = node.typeName.text;
      if (namesToRewrite.has(name)) {
        const schema = MIGRATIONS[name];
        const id = node.typeName;
        replacements.push({
          start: id.getStart(sf),
          end: id.getEnd(),
          text: `Schemas['${schema}']`,
        });
      }
    } else if (ts.isExpressionWithTypeArguments(node) && ts.isIdentifier(node.expression)) {
      // `extends Foo`, `implements Foo` (rare in type imports but handle anyway)
      const name = node.expression.text;
      if (namesToRewrite.has(name)) {
        replacements.push({
          start: node.expression.getStart(sf),
          end: node.expression.getEnd(),
          text: `Schemas['${MIGRATIONS[name]}']`,
        });
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sf);

  // Pass 3 — rewrite the import declaration.
  const importStart = typesImport.getStart(sf);
  const importEnd = typesImport.getEnd();
  let newImports;
  if (toKeep.length === 0) {
    // Replace whole import with the @stoa/shared one (if not already there).
    newImports = `import type { Schemas } from '@stoa/shared/api-types';`;
  } else {
    const moduleSpec = typesImport.moduleSpecifier.text;
    newImports =
      `import type { ${toKeep.join(', ')} } from '${moduleSpec}';\n` +
      `import type { Schemas } from '@stoa/shared/api-types';`;
  }
  replacements.push({
    start: importStart,
    end: importEnd,
    text: newImports,
  });

  // Check if there's already a `import type { Schemas } from '@stoa/shared/api-types'`.
  for (const stmt of sf.statements) {
    if (
      stmt !== typesImport &&
      ts.isImportDeclaration(stmt) &&
      ts.isStringLiteral(stmt.moduleSpecifier) &&
      stmt.moduleSpecifier.text === '@stoa/shared/api-types'
    ) {
      // Already imported — strip the `Schemas` we're adding.
      // For simplicity drop the suffix; the existing import will already cover it.
      newImports = newImports.replace(
        /\nimport type \{ Schemas \} from '@stoa\/shared\/api-types';/,
        ''
      );
      newImports = newImports.replace(
        /^import type \{ Schemas \} from '@stoa\/shared\/api-types';$/,
        ''
      );
      // Update the replacement
      replacements[replacements.length - 1].text = newImports;
      break;
    }
  }

  // Apply replacements in reverse order of `start`.
  replacements.sort((a, b) => b.start - a.start);
  let updated = text;
  for (const r of replacements) {
    updated = updated.slice(0, r.start) + r.text + updated.slice(r.end);
  }

  if (updated === text) return { changed: false, names: [] };

  if (!dryRun) {
    writeFileSync(filePath, updated);
  }

  return { changed: true, names: toMigrate.map((t) => t.manual) };
}

// ---- MAIN -------------------------------------------------------------------

const args = argv.slice(2);
const dryRun = args.includes('--dry');
const fileArg = args.find((a) => !a.startsWith('--'));

const files = fileArg ? [resolve(fileArg)] : listSourceFiles(SRC_ROOT);

let totalChanged = 0;
const summary = [];
for (const f of files) {
  const result = processFile(f, dryRun);
  if (result.changed) {
    totalChanged++;
    summary.push({ file: relative(SRC_ROOT, f), names: result.names });
  }
}

console.log(`${dryRun ? '[DRY] ' : ''}Migrated ${totalChanged} files of ${files.length} scanned.`);
for (const s of summary) {
  console.log(`  ${s.file}: ${s.names.join(', ')}`);
}
exit(0);
