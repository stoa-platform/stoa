/**
 * Credential Mapping step definitions for STOA E2E Tests (CAB-1432, CAB-1451)
 *
 * Tests per-consumer credential injection via the gateway admin API.
 * Covers 6 scenarios: CRUD, injection per-consumer, BYOK fallback,
 * anonymous negative case, and delete.
 *
 * Steps require live infrastructure (STOA Gateway + backend).
 * Tagged @gateway and @credential-mapping for targeted execution.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// Admin API base URL (uses gateway URL which serves admin endpoints)
const ADMIN_URL = process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev';
const ADMIN_TOKEN = process.env.STOA_ADMIN_TOKEN || '';

// Store for test context
let lastCredentialResponse: { status: number; body: any } | null = null;
let lastProxyResponse: { status: number; body: any } | null = null;

function adminHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (ADMIN_TOKEN) {
    headers['Authorization'] = `Bearer ${ADMIN_TOKEN}`;
  }
  return headers;
}

// ============================================================================
// BACKGROUND / SETUP STEPS
// ============================================================================

Given(
  'a test route {string} exists with backend {string}',
  async ({ request }, routeId: string, backendUrl: string) => {
    await request.fetch(`${ADMIN_URL}/admin/apis`, {
      method: 'POST',
      headers: adminHeaders(),
      data: JSON.stringify({
        id: routeId,
        name: `E2E Test Route ${routeId}`,
        upstream_url: backendUrl,
        listen_path: `/e2e/${routeId}`,
        methods: ['GET', 'POST'],
        strip_listen_path: true,
        active: true,
      }),
    });
  },
);

// ============================================================================
// CONSUMER CREDENTIAL CRUD STEPS
// ============================================================================

When(
  'I upsert a consumer credential mapping:',
  async ({ request }, dataTable: { hashes: () => Record<string, string>[] }) => {
    const rows = dataTable.hashes();
    for (const row of rows) {
      const response = await request.fetch(`${ADMIN_URL}/admin/consumer-credentials`, {
        method: 'POST',
        headers: adminHeaders(),
        data: JSON.stringify({
          route_id: row.route_id,
          consumer_id: row.consumer_id,
          auth_type: row.auth_type,
          header_name: row.header_name,
          header_value: row.header_value,
        }),
      });
      lastCredentialResponse = {
        status: response.status(),
        body: await response.json().catch(() => ({})),
      };
    }
  },
);

Given(
  'a consumer credential mapping exists:',
  async ({ request }, dataTable: { hashes: () => Record<string, string>[] }) => {
    const rows = dataTable.hashes();
    for (const row of rows) {
      const response = await request.fetch(`${ADMIN_URL}/admin/consumer-credentials`, {
        method: 'POST',
        headers: adminHeaders(),
        data: JSON.stringify({
          route_id: row.route_id,
          consumer_id: row.consumer_id,
          auth_type: row.auth_type,
          header_name: row.header_name,
          header_value: row.header_value,
        }),
      });
      expect(response.status()).toBeLessThan(300);
    }
  },
);

Given(
  'a route-level BYOK credential exists for {string}:',
  async ({ request }, routeId: string, dataTable: { hashes: () => Record<string, string>[] }) => {
    const rows = dataTable.hashes();
    const row = rows[0];
    const response = await request.fetch(`${ADMIN_URL}/admin/backend-credentials`, {
      method: 'POST',
      headers: adminHeaders(),
      data: JSON.stringify({
        route_id: routeId,
        header_name: row.header_name,
        header_value: row.header_value,
      }),
    });
    expect(response.status()).toBeLessThan(300);
  },
);

Given(
  'no consumer credential mapping exists for {string} on {string}',
  async ({ request }, consumerId: string, routeId: string) => {
    const response = await request.fetch(
      `${ADMIN_URL}/admin/consumer-credentials/${routeId}/${consumerId}`,
      { method: 'DELETE', headers: adminHeaders() },
    );
    expect([200, 204, 404]).toContain(response.status());
  },
);

Given(
  'no route-level BYOK credential exists for {string}',
  async ({ request }, routeId: string) => {
    const response = await request.fetch(
      `${ADMIN_URL}/admin/backend-credentials/${routeId}`,
      { method: 'DELETE', headers: adminHeaders() },
    );
    expect([200, 204, 404]).toContain(response.status());
  },
);

When(
  'I delete the consumer credential for {string} on route {string}',
  async ({ request }, consumerId: string, routeId: string) => {
    const response = await request.fetch(
      `${ADMIN_URL}/admin/consumer-credentials/${routeId}/${consumerId}`,
      { method: 'DELETE', headers: adminHeaders() },
    );
    lastCredentialResponse = {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  },
);

// ============================================================================
// PROXY CALL STEPS
// ============================================================================

When(
  'consumer {string} calls the proxied route {string}',
  async ({ request }, consumerId: string, routeId: string) => {
    // In a real scenario, the consumer would have a JWT with sub=consumerId.
    // For E2E, use pre-provisioned JWTs via env vars.
    const token = process.env[`TEST_JWT_${consumerId.replace(/-/g, '_').toUpperCase()}`] || '';
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    try {
      const response = await request.fetch(`${URLS.gateway}/e2e/${routeId}`, {
        method: 'GET',
        headers,
      });
      lastProxyResponse = {
        status: response.status(),
        body: await response.json().catch(() => ({})),
      };
    } catch (error) {
      lastProxyResponse = { status: 500, body: { error: String(error) } };
    }
  },
);

When(
  'an anonymous consumer calls the proxied route {string}',
  async ({ request }, routeId: string) => {
    try {
      const response = await request.fetch(`${URLS.gateway}/e2e/${routeId}`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
      });
      lastProxyResponse = {
        status: response.status(),
        body: await response.json().catch(() => ({})),
      };
    } catch (error) {
      lastProxyResponse = { status: 500, body: { error: String(error) } };
    }
  },
);

// ============================================================================
// CREDENTIAL MAPPING ASSERTION STEPS
// ============================================================================

Then(
  'the credential mapping response status is {int}',
  async ({}, expectedStatus: number) => {
    expect(lastCredentialResponse).not.toBeNull();
    expect(lastCredentialResponse!.status).toBe(expectedStatus);
  },
);

Then(
  'the consumer credential list contains {int} entry for route {string}',
  async ({ request }, expectedCount: number, routeId: string) => {
    const response = await request.fetch(`${ADMIN_URL}/admin/consumer-credentials`, {
      method: 'GET',
      headers: adminHeaders(),
    });
    expect(response.status()).toBe(200);
    const credentials: any[] = await response.json();
    const routeCredentials = credentials.filter((c: any) => c.route_id === routeId);
    expect(routeCredentials.length).toBe(expectedCount);
  },
);

Then(
  'the consumer credential list has {int} entries for {string} on {string}',
  async ({ request }, expectedCount: number, consumerId: string, routeId: string) => {
    const response = await request.fetch(`${ADMIN_URL}/admin/consumer-credentials`, {
      method: 'GET',
      headers: adminHeaders(),
    });
    expect(response.status()).toBe(200);
    const credentials: any[] = await response.json();
    const filtered = credentials.filter(
      (c: any) => c.route_id === routeId && c.consumer_id === consumerId,
    );
    expect(filtered.length).toBe(expectedCount);
  },
);

Then(
  'the backend receives header {string} with value {string}',
  async ({}, headerName: string, expectedValue: string) => {
    // httpbin.org/get echoes request headers in the "headers" field
    expect(lastProxyResponse).not.toBeNull();
    expect(lastProxyResponse!.status).toBeLessThan(500);
    const headers = lastProxyResponse!.body?.headers || {};
    const normalizedHeaders: Record<string, string> = {};
    for (const [k, v] of Object.entries(headers)) {
      normalizedHeaders[k.toLowerCase()] = String(v);
    }
    expect(normalizedHeaders[headerName.toLowerCase()]).toBe(expectedValue);
  },
);

Then('the backend does not receive header {string}', async ({}, headerName: string) => {
  expect(lastProxyResponse).not.toBeNull();
  const headers = lastProxyResponse!.body?.headers || {};
  const normalizedHeaders: Record<string, string> = {};
  for (const [k, v] of Object.entries(headers)) {
    normalizedHeaders[k.toLowerCase()] = String(v);
  }
  expect(normalizedHeaders[headerName.toLowerCase()]).toBeUndefined();
});
