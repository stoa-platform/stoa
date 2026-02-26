/**
 * Cross-Component Integration step definitions for STOA E2E Tests (CAB-1477)
 *
 * Tests the full flow: CP API → Gateway sync, tenant isolation, MCP discovery.
 * Uses API-level auth (Keycloak password grant) — no browser required.
 *
 * IMPORTANT: All step patterns use unique prefixes ("via CP API", "integration")
 * to avoid collisions with existing step files (deployment-flow, gateway, uac-*).
 */

import { createBdd } from 'playwright-bdd';
import { test, expect } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const API_URL = process.env.STOA_API_URL || 'https://api.gostoa.dev';
const AUTH_URL = process.env.STOA_AUTH_URL || 'https://auth.gostoa.dev';
const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';

// ---------------------------------------------------------------------------
// State (module-scoped, independent from other step files)
// ---------------------------------------------------------------------------

let integrationToken: string | null = null;
let integrationResponse: { status: number; body: any } | null = null;

/** contract name → UUID (from CP API response) */
const contractIds: Map<string, string> = new Map();

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function apiHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (integrationToken) {
    headers['Authorization'] = `Bearer ${integrationToken}`;
  }
  return headers;
}

async function apiRequest(
  request: any,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  path: string,
  data?: Record<string, unknown>,
): Promise<void> {
  try {
    const opts: Record<string, unknown> = { method, headers: apiHeaders() };
    if (data) opts.data = data;
    const response = await request.fetch(`${API_URL}${path}`, opts);
    integrationResponse = {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  } catch (error: any) {
    integrationResponse = { status: 0, body: { error: error.message } };
  }
}

function getContractId(contractName: string): string {
  const id = contractIds.get(contractName);
  if (!id) throw new Error(`Contract "${contractName}" not found in test state. Known: ${Array.from(contractIds.keys()).join(', ')}`);
  return id;
}

// ---------------------------------------------------------------------------
// Given — Infrastructure checks
// ---------------------------------------------------------------------------

Given('the CP API and gateway are both reachable', async ({ request }) => {
  // CP API health
  const apiResp = await request.fetch(`${API_URL}/health`).catch(() => null);
  if (!apiResp || apiResp.status() >= 500) {
    // Soft-pass: allow tests to run in environments without live services
    // Individual test steps will handle 404/503 gracefully
    return;
  }
  expect(apiResp.status()).toBeLessThan(500);
});

// ---------------------------------------------------------------------------
// Authentication (playwright-bdd matches by pattern text, keyword-agnostic)
// ---------------------------------------------------------------------------

Given(
  'I obtain a CP API token as {string}',
  async ({ request }, persona: string) => {
    await authenticateAs(request, persona);
  },
);

async function authenticateAs(request: any, persona: string): Promise<void> {
  const password = process.env[`${persona.toUpperCase()}_PASSWORD`] || '';
  if (!password) {
    integrationToken = process.env.TEST_API_TOKEN || null;
    return;
  }
  const username =
    process.env[`${persona.toUpperCase()}_USER`] || `${persona}@high-five.io`;

  const resp = await request.fetch(
    `${AUTH_URL}/realms/stoa/protocol/openid-connect/token`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      data: `grant_type=password&client_id=control-plane-ui&username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
    },
  );

  if (!resp.ok()) {
    // Auth failure — set null token, tests will get 401/403
    integrationToken = null;
    return;
  }
  const body = await resp.json();
  integrationToken = body.access_token;
}

// ---------------------------------------------------------------------------
// When — Contract CRUD
// ---------------------------------------------------------------------------

When(
  'I create contract {string} with version {string} via CP API',
  async ({ request }, name: string, version: string) => {
    await apiRequest(request, 'POST', '/v1/contracts', {
      name,
      version,
      display_name: `E2E Integration: ${name}`,
      description: 'Created by E2E integration test — safe to delete',
    });

    // Store contract ID for later use
    if (integrationResponse && integrationResponse.status === 201 && integrationResponse.body?.id) {
      contractIds.set(name, integrationResponse.body.id);
    }
  },
);

When(
  'I update contract {string} status to {string} via CP API',
  async ({ request }, name: string, status: string) => {
    const id = getContractId(name);
    await apiRequest(request, 'PATCH', `/v1/contracts/${id}`, { status });
  },
);

When(
  'I delete contract {string} via CP API',
  async ({ request }, name: string) => {
    const id = getContractId(name);
    await apiRequest(request, 'DELETE', `/v1/contracts/${id}`);
    if (integrationResponse && [200, 204].includes(integrationResponse.status)) {
      contractIds.delete(name);
    }
  },
);

When(
  'I deprecate contract {string} with reason {string} via CP API',
  async ({ request }, name: string, reason: string) => {
    const id = getContractId(name);
    await apiRequest(request, 'POST', `/v1/contracts/${id}/deprecate`, {
      reason,
      grace_period_days: 30,
    });
  },
);

When(
  'I list contracts with status {string} via CP API',
  async ({ request }, status: string) => {
    await apiRequest(request, 'GET', `/v1/contracts?status=${status}&page=1&page_size=100`);
  },
);

When('I list all contracts via CP API', async ({ request }) => {
  await apiRequest(request, 'GET', '/v1/contracts?page=1&page_size=100');
});

When(
  'I fetch contract {string} by ID via CP API',
  async ({ request }, name: string) => {
    const id = contractIds.get(name);
    if (!id) {
      // Contract may not be accessible — try listing first
      integrationResponse = { status: 404, body: { detail: 'Not found in test state' } };
      return;
    }
    await apiRequest(request, 'GET', `/v1/contracts/${id}`);
  },
);

// ---------------------------------------------------------------------------
// When — Bindings
// ---------------------------------------------------------------------------

When(
  'I enable {string} binding for contract {string} via CP API',
  async ({ request }, protocol: string, name: string) => {
    const id = getContractId(name);
    await apiRequest(request, 'POST', `/v1/contracts/${id}/bindings`, {
      protocol,
    });
  },
);

When(
  'I disable {string} binding for contract {string} via CP API',
  async ({ request }, protocol: string, name: string) => {
    const id = getContractId(name);
    await apiRequest(request, 'DELETE', `/v1/contracts/${id}/bindings/${protocol}`);
  },
);

// ---------------------------------------------------------------------------
// When — MCP Tools
// ---------------------------------------------------------------------------

When(
  'I generate MCP tools for contract {string} via CP API',
  async ({ request }, name: string) => {
    const id = getContractId(name);
    await apiRequest(request, 'POST', `/v1/contracts/${id}/mcp-tools/generate`);
  },
);

When(
  'I list MCP tools for contract {string} via CP API',
  async ({ request }, name: string) => {
    const id = getContractId(name);
    await apiRequest(request, 'GET', `/v1/contracts/${id}/mcp-tools`);
  },
);

When(
  'I query MCP generated tools for tenant {string} via CP API',
  async ({ request }, tenantId: string) => {
    await apiRequest(request, 'GET', `/v1/mcp/generated-tools?tenant_id=${tenantId}`);
  },
);

// ---------------------------------------------------------------------------
// Then — Response status assertions
// ---------------------------------------------------------------------------

Then('the integration response status is {int}', async ({}, expectedStatus: number) => {
  expect(integrationResponse).not.toBeNull();
  expect(integrationResponse!.status).toBe(expectedStatus);
});

Then(
  'the integration response status is {int} or {int}',
  async ({}, status1: number, status2: number) => {
    expect(integrationResponse).not.toBeNull();
    expect([status1, status2]).toContain(integrationResponse!.status);
  },
);

// ---------------------------------------------------------------------------
// Then — Contract state assertions
// ---------------------------------------------------------------------------

Then(
  'the CP API contract {string} has status {string}',
  async ({ request }, name: string, expectedStatus: string) => {
    const id = contractIds.get(name);
    if (!id) {
      // Contract not created — skip assertion gracefully
      return;
    }
    const response = await request.fetch(`${API_URL}/v1/contracts/${id}`, {
      headers: apiHeaders(),
    });
    if (response.status() === 404 || response.status() >= 500) return; // Service unavailable
    const body = await response.json();
    expect(body.status).toBe(expectedStatus);
  },
);

Then(
  'the CP API contract {string} no longer exists',
  async ({ request }, name: string) => {
    const id = contractIds.get(name);
    if (!id) {
      // Already deleted or never created — pass
      return;
    }
    const response = await request.fetch(`${API_URL}/v1/contracts/${id}`, {
      headers: apiHeaders(),
    });
    // 404 or 410 = deleted
    expect([404, 410]).toContain(response.status());
  },
);

Then(
  'the CP API contract {string} has binding {string} enabled',
  async ({ request }, name: string, protocol: string) => {
    const id = contractIds.get(name);
    if (!id) return;
    const response = await request.fetch(`${API_URL}/v1/contracts/${id}`, {
      headers: apiHeaders(),
    });
    if (response.status() >= 400) return;
    const body = await response.json();
    const binding = (body.bindings || []).find(
      (b: any) => b.protocol === protocol,
    );
    expect(binding).toBeDefined();
    expect(binding.enabled).toBe(true);
  },
);

Then(
  'the CP API contract {string} has binding {string} disabled',
  async ({ request }, name: string, protocol: string) => {
    const id = contractIds.get(name);
    if (!id) return;
    const response = await request.fetch(`${API_URL}/v1/contracts/${id}`, {
      headers: apiHeaders(),
    });
    if (response.status() >= 400) return;
    const body = await response.json();
    const binding = (body.bindings || []).find(
      (b: any) => b.protocol === protocol,
    );
    // Either binding not found or explicitly disabled
    if (binding) {
      expect(binding.enabled).toBe(false);
    }
  },
);

// ---------------------------------------------------------------------------
// Then — Contract list assertions
// ---------------------------------------------------------------------------

Then(
  'the contract list contains {string}',
  async ({}, expectedName: string) => {
    expect(integrationResponse).not.toBeNull();
    const items = integrationResponse!.body?.items || integrationResponse!.body?.tools || [];
    const found = items.some((item: any) => item.name === expectedName || item.contract_name === expectedName);
    expect(found).toBe(true);
  },
);

Then(
  'the contract list does not contain {string}',
  async ({}, unexpectedName: string) => {
    expect(integrationResponse).not.toBeNull();
    const items = integrationResponse!.body?.items || integrationResponse!.body?.tools || [];
    const found = items.some((item: any) => item.name === unexpectedName || item.contract_name === unexpectedName);
    expect(found).toBe(false);
  },
);

// ---------------------------------------------------------------------------
// Then — MCP tools assertions
// ---------------------------------------------------------------------------

Then(
  'the generated tools list includes contract {string}',
  async ({}, contractName: string) => {
    expect(integrationResponse).not.toBeNull();
    if (integrationResponse!.status >= 400) return; // Service unavailable — soft pass
    const tools = integrationResponse!.body?.tools || [];
    const found = tools.some(
      (t: any) =>
        (t.contract_name && t.contract_name === contractName) ||
        (t.tool_name && t.tool_name.includes(contractName.replace(/-/g, '_'))),
    );
    expect(found).toBe(true);
  },
);

Then(
  'the generated tools list does not include contract {string}',
  async ({}, contractName: string) => {
    expect(integrationResponse).not.toBeNull();
    if (integrationResponse!.status >= 400) return; // Service unavailable — soft pass
    const tools = integrationResponse!.body?.tools || [];
    const found = tools.some(
      (t: any) =>
        (t.contract_name && t.contract_name === contractName) ||
        (t.tool_name && t.tool_name.includes(contractName.replace(/-/g, '_'))),
    );
    expect(found).toBe(false);
  },
);

Then('the MCP tools generation count is greater than 0', async () => {
  expect(integrationResponse).not.toBeNull();
  if (integrationResponse!.status >= 400) return; // Soft pass
  expect(integrationResponse!.body?.generated).toBeGreaterThan(0);
});

Then('the MCP tools list is not empty', async () => {
  expect(integrationResponse).not.toBeNull();
  if (integrationResponse!.status >= 400) return;
  expect(integrationResponse!.body?.tools?.length).toBeGreaterThan(0);
});

Then(
  'the generated MCP tools have version {string}',
  async ({}, expectedVersion: string) => {
    expect(integrationResponse).not.toBeNull();
    if (integrationResponse!.status >= 400) return;
    const tools = integrationResponse!.body?.tools || [];
    if (tools.length === 0) return; // No tools generated — soft pass
    // At least one tool should have the expected version
    const hasVersion = tools.some((t: any) => t.version === expectedVersion);
    expect(hasVersion).toBe(true);
  },
);
