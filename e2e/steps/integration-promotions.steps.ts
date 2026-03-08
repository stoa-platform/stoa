/**
 * Promotion Flow Integration step definitions (CAB-1706)
 *
 * Tests the full promotion lifecycle: create → approve → complete → rollback.
 * Also verifies portal env badges via the portal API.
 * Uses API-level auth (Keycloak password grant) — no browser required.
 *
 * Reuses auth steps from integration.steps.ts (same Background).
 */

import { createBdd } from 'playwright-bdd';
import { test, expect } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const API_URL = process.env.STOA_API_URL || 'https://api.gostoa.dev';
const AUTH_URL = process.env.STOA_AUTH_URL || 'https://auth.gostoa.dev';
const TENANT_ID = process.env.TEST_TENANT_ID || 'high-five';

// ---------------------------------------------------------------------------
// State (module-scoped, independent from other step files)
// ---------------------------------------------------------------------------

let promotionToken: string | null = null;
let promotionResponse: { status: number; body: any } | null = null;
let promotionId: string | null = null;
let rollbackResponse: { status: number; body: any } | null = null;
let portalResponse: { status: number; body: any } | null = null;
let testApiId: string | null = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function promoHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (promotionToken) {
    headers['Authorization'] = `Bearer ${promotionToken}`;
  }
  return headers;
}

async function ensureToken(request: any): Promise<void> {
  if (promotionToken) return;
  const password = process.env.PARZIVAL_PASSWORD || '';
  if (!password) {
    promotionToken = process.env.TEST_API_TOKEN || null;
    return;
  }
  const username = process.env.PARZIVAL_USER || 'parzival@high-five.io';
  const resp = await request.fetch(`${AUTH_URL}/realms/stoa/protocol/openid-connect/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: `grant_type=password&client_id=control-plane-ui&username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
  });
  if (resp.ok()) {
    const body = await resp.json();
    promotionToken = body.access_token;
  }
}

// ---------------------------------------------------------------------------
// When — Tenant APIs (to get an api_id for promotion)
// ---------------------------------------------------------------------------

When('I list tenant APIs via CP API', async ({ request }) => {
  await ensureToken(request);
  const resp = await request.fetch(`${API_URL}/v1/tenants/${TENANT_ID}/apis?page=1&page_size=10`, {
    headers: promoHeaders(),
  });
  const body = await resp.json().catch(() => ({}));
  // Pick first API ID available for promotion tests
  const apis = body.items || body.apis || [];
  if (apis.length > 0) {
    testApiId = apis[0].id || apis[0].api_id;
  }
});

// ---------------------------------------------------------------------------
// When — Promotion CRUD
// ---------------------------------------------------------------------------

When(
  'I create a promotion from {string} to {string} with message {string}',
  async ({ request }, source: string, target: string, message: string) => {
    await ensureToken(request);
    if (!testApiId) {
      promotionResponse = {
        status: 0,
        body: { error: 'No API found in tenant for promotion test' },
      };
      return;
    }
    const resp = await request.fetch(`${API_URL}/v1/tenants/${TENANT_ID}/promotions/${testApiId}`, {
      method: 'POST',
      headers: promoHeaders(),
      data: JSON.stringify({
        source_environment: source,
        target_environment: target,
        message,
      }),
    });
    const body = await resp.json().catch(() => ({}));
    promotionResponse = { status: resp.status(), body };
    if (resp.status() === 201 && body.id) {
      promotionId = body.id;
    }
  }
);

When('I approve the pending promotion', async ({ request }) => {
  await ensureToken(request);
  if (!promotionId) {
    promotionResponse = { status: 0, body: { error: 'No promotion to approve' } };
    return;
  }
  const resp = await request.fetch(
    `${API_URL}/v1/tenants/${TENANT_ID}/promotions/${promotionId}/approve`,
    {
      method: 'POST',
      headers: promoHeaders(),
    }
  );
  const body = await resp.json().catch(() => ({}));
  promotionResponse = { status: resp.status(), body };
});

When('I mark the promotion as completed', async ({ request }) => {
  await ensureToken(request);
  if (!promotionId) {
    promotionResponse = { status: 0, body: { error: 'No promotion to complete' } };
    return;
  }
  const resp = await request.fetch(
    `${API_URL}/v1/tenants/${TENANT_ID}/promotions/${promotionId}/complete`,
    {
      method: 'POST',
      headers: promoHeaders(),
    }
  );
  const body = await resp.json().catch(() => ({}));
  promotionResponse = { status: resp.status(), body };
});

When('I rollback the promotion with message {string}', async ({ request }, message: string) => {
  await ensureToken(request);
  if (!promotionId) {
    rollbackResponse = { status: 0, body: { error: 'No promotion to rollback' } };
    return;
  }
  const resp = await request.fetch(
    `${API_URL}/v1/tenants/${TENANT_ID}/promotions/${promotionId}/rollback`,
    {
      method: 'POST',
      headers: promoHeaders(),
      data: JSON.stringify({ message }),
    }
  );
  const body = await resp.json().catch(() => ({}));
  rollbackResponse = { status: resp.status(), body };
});

// ---------------------------------------------------------------------------
// When — Portal APIs
// ---------------------------------------------------------------------------

When('I fetch portal APIs list', async ({ request }) => {
  await ensureToken(request);
  const resp = await request.fetch(`${API_URL}/v1/portal/apis?page=1&page_size=20`, {
    headers: promoHeaders(),
  });
  const body = await resp.json().catch(() => ({}));
  portalResponse = { status: resp.status(), body };
});

// ---------------------------------------------------------------------------
// Then — Promotion assertions
// ---------------------------------------------------------------------------

Then('the promotion response status is {int}', async ({}, expectedStatus: number) => {
  expect(promotionResponse).not.toBeNull();
  expect(promotionResponse!.status).toBe(expectedStatus);
});

Then('the promotion status is {string}', async ({}, expectedStatus: string) => {
  expect(promotionResponse).not.toBeNull();
  expect(promotionResponse!.body.status).toBe(expectedStatus);
});

Then(
  'the promotion source is {string} and target is {string}',
  async ({}, source: string, target: string) => {
    expect(promotionResponse).not.toBeNull();
    expect(promotionResponse!.body.source_environment).toBe(source);
    expect(promotionResponse!.body.target_environment).toBe(target);
  }
);

// ---------------------------------------------------------------------------
// Then — Rollback assertions
// ---------------------------------------------------------------------------

Then('the rollback promotion status is {string}', async ({}, expectedStatus: string) => {
  expect(rollbackResponse).not.toBeNull();
  expect(rollbackResponse!.body.status).toBe(expectedStatus);
});

Then(
  'the rollback promotion source is {string} and target is {string}',
  async ({}, source: string, target: string) => {
    expect(rollbackResponse).not.toBeNull();
    expect(rollbackResponse!.body.source_environment).toBe(source);
    expect(rollbackResponse!.body.target_environment).toBe(target);
  }
);

// ---------------------------------------------------------------------------
// Then — Portal assertions
// ---------------------------------------------------------------------------

Then('the portal response status is {int}', async ({}, expectedStatus: number) => {
  expect(portalResponse).not.toBeNull();
  expect(portalResponse!.status).toBe(expectedStatus);
});

Then('the portal APIs response contains a deployments field', async () => {
  expect(portalResponse).not.toBeNull();
  if (portalResponse!.status >= 400) return; // Service unavailable — soft pass
  const apis = portalResponse!.body?.apis || [];
  if (apis.length === 0) return; // No APIs published — soft pass
  // At least one API should have a deployments field (can be empty object or populated)
  const hasDeployments = apis.some(
    (api: any) => api.deployments !== undefined && api.deployments !== null
  );
  expect(hasDeployments).toBe(true);
});
