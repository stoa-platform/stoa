#!/usr/bin/env node
// One-shot: delete `export interface X` / `export type X` declarations whose
// names are now sourced from `@stoa/shared/api-types`. Safe because the
// codemod (migrate-types.mjs) already removed all consumer imports.
//
// Strategy: line-based deletion for predictable boundaries. We don't try to
// move adjacent comments — those become orphan cosmetic noise that a single
// follow-up pass can clean up. Better than risking off-by-one corruption.
//
// DELETION CRITERIA: same as migrate-types.mjs. Sunset both scripts together
// when CAB-2158 (UI-1-Wave2) merged AND CAB-2159 (backend BUG-1/2/4) resolved.
// Owner of deletion: whoever closes CAB-2158.

import { readFileSync, writeFileSync } from 'node:fs';
import ts from 'typescript';

const FILE = 'src/types/index.ts';

const REMOVE = new Set([
  'APIVersionEntry',
  'BulkRevokeResponse',
  'BulkActionFailure',
  'BulkActionResult',
  'BulkSubscriptionAction',
  'CompanyStats',
  'ApprovalStepDef',
  'CSRSignResponse',
  'TestConnectionResponse',
  'SyncToolsResponse',
  'WebhookTestResponse',
  'SyncResponse',
  'DeploymentStatusSummary',
  'GatewayHealthCheckResponse',
  'GatewayBindingInfo',
  'CertificateExpiryItem',
  'CertificateExpiryResponse',
  'TenantToolPermissionCreate',
  'FederationBulkRevokeResponse',
  'WebhookCreate',
  'WebhookUpdate',
  'CredentialMappingCreate',
  'CredentialMappingUpdate',
  'ContractUpdate',
  'PromotionCreate',
  'PromotionRollbackRequest',
  'PromotionDiffResponse',
  'BackendApiCreate',
  'BackendApiUpdate',
  'SaasApiKeyCreate',
  'SaasApiKeyCreatedResponse',
  'MasterAccountCreate',
  'AuthorizeResponse',
  'CallbackResponse',
  'PromoteResponse',
]);

const text = readFileSync(FILE, 'utf8');
const lines = text.split('\n');
const sf = ts.createSourceFile(FILE, text, ts.ScriptTarget.Latest, true);

// Map char offset -> line number (0-indexed).
const lineStarts = sf.getLineStarts();
function lineOf(offset) {
  // Binary search.
  let lo = 0,
    hi = lineStarts.length - 1;
  while (lo < hi) {
    const mid = (lo + hi + 1) >>> 1;
    if (lineStarts[mid] <= offset) lo = mid;
    else hi = mid - 1;
  }
  return lo;
}

const linesToDelete = new Set();
let count = 0;
for (const stmt of sf.statements) {
  let name = null;
  if (ts.isInterfaceDeclaration(stmt) && stmt.name) name = stmt.name.text;
  else if (ts.isTypeAliasDeclaration(stmt) && stmt.name) name = stmt.name.text;
  if (!name || !REMOVE.has(name)) continue;

  const startLine = lineOf(stmt.getStart(sf));
  let endLine = lineOf(stmt.getEnd() - 1);
  // Eat one trailing blank line after the declaration (if present).
  if (endLine + 1 < lines.length && lines[endLine + 1].trim() === '') {
    endLine++;
  }
  for (let i = startLine; i <= endLine; i++) linesToDelete.add(i);
  count++;
}

const kept = lines.filter((_, i) => !linesToDelete.has(i));
let updated = kept.join('\n');
// Squash 3+ blank lines.
updated = updated.replace(/\n{3,}/g, '\n\n');

writeFileSync(FILE, updated);
console.log(`Stripped ${count} declarations (${linesToDelete.size} lines) from ${FILE}.`);
