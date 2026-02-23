/** Deployment Flow Integration — API-driven CRUD, logs, rollback, status */
import { createBdd } from 'playwright-bdd';
import { test, expect } from '../fixtures/test-base';
import { DEPLOY_PAYLOADS, DEPLOY_STATUSES } from '../fixtures/deploy-data';

const { Given, When, Then } = createBdd(test);
const API_URL = process.env.STOA_API_URL || 'https://api.gostoa.dev';
const TENANT_ID = process.env.TEST_TENANT_ID || 'high-five';

let authToken: string | null = null;
let currentDeployment: { id: string; status: string; [key: string]: unknown } | null = null;
let lastApiResponse: { status: number; body: Record<string, unknown> } | null = null;

const authHeaders = (): { [key: string]: string } =>
  authToken ? { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };

const deploymentsUrl = (suffix = '') =>
  `${API_URL}/v1/tenants/${TENANT_ID}/deployments${suffix}`;

// --- Setup ---

Given('the Control Plane API is accessible', async ({ request }) => {
  expect((await request.fetch(`${API_URL}/health`)).status()).toBeLessThan(400);
});

Given('I am authenticated as {string} via API', async ({ request }, persona: string) => {
  const authUrl = process.env.STOA_AUTH_URL || 'https://auth.gostoa.dev';
  const password = process.env[`${persona.toUpperCase()}_PASSWORD`] || '';
  if (!password) { authToken = process.env.TEST_API_TOKEN || null; return; }
  const username = process.env[`${persona.toUpperCase()}_USER`] || `${persona}@high-five.io`;
  const resp = await request.fetch(`${authUrl}/realms/stoa/protocol/openid-connect/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: `grant_type=password&client_id=control-plane-ui&username=${encodeURIComponent(username)}&password=${encodeURIComponent(password)}`,
  });
  expect(resp.ok()).toBeTruthy();
  authToken = (await resp.json()).access_token;
});

// --- Create ---

When('I create a deployment for API {string} to environment {string}',
  async ({ request }, apiName: string, env: string) => {
    const resp = await request.fetch(deploymentsUrl(), {
      method: 'POST', headers: authHeaders(),
      data: JSON.stringify({ ...DEPLOY_PAYLOADS.default, api_name: apiName, environment: env }),
    });
    lastApiResponse = { status: resp.status(), body: await resp.json().catch(() => ({})) };
    if (resp.ok()) currentDeployment = lastApiResponse.body as typeof currentDeployment;
  });

Then('the deployment is created with status {string}', async ({}, status: string) => {
  expect(lastApiResponse!.status).toBe(201);
  expect(currentDeployment!.status).toBe(status);
});

Then('the deployment appears in the deployment list', async ({ request }) => {
  const resp = await request.fetch(deploymentsUrl(), { headers: authHeaders() });
  const items = ((await resp.json()) as { items?: { id: string }[] }).items || [];
  expect(items.some((d) => d.id === currentDeployment?.id)).toBe(true);
});

// --- Logs ---

Given('a deployment exists for API {string} in environment {string}',
  async ({ request }, apiName: string, env: string) => {
    const resp = await request.fetch(deploymentsUrl(), {
      method: 'POST', headers: authHeaders(),
      data: JSON.stringify({ ...DEPLOY_PAYLOADS.default, api_name: apiName, environment: env }),
    });
    if (resp.ok()) currentDeployment = await resp.json();
  });

When('I fetch the deployment logs', async ({ request }) => {
  const resp = await request.fetch(deploymentsUrl(`/${currentDeployment!.id}/logs`), {
    headers: authHeaders(),
  });
  lastApiResponse = { status: resp.status(), body: await resp.json().catch(() => ({})) };
});

Then('the response contains a logs array', async () => {
  expect(lastApiResponse!.status).toBeLessThan(400);
  expect(Array.isArray((lastApiResponse!.body as { logs?: unknown[] }).logs)).toBe(true);
});

Then('each log entry has a level and message', async () => {
  for (const e of ((lastApiResponse!.body as { logs?: Record<string, unknown>[] }).logs || []))
    { expect(e).toHaveProperty('level'); expect(e).toHaveProperty('message'); }
});

// --- Rollback ---

Given('a successful deployment exists for API {string} in environment {string}',
  async ({ request }, apiName: string, env: string) => {
    const resp = await request.fetch(deploymentsUrl(), {
      method: 'POST', headers: authHeaders(),
      data: JSON.stringify({ ...DEPLOY_PAYLOADS.default, api_name: apiName, environment: env }),
    });
    if (resp.ok()) {
      currentDeployment = await resp.json();
      await request.fetch(deploymentsUrl(`/${currentDeployment!.id}/status`), {
        method: 'PATCH', headers: authHeaders(),
        data: JSON.stringify({ status: DEPLOY_STATUSES.SUCCESS }),
      });
    }
  });

When('I trigger a rollback on the deployment', async ({ request }) => {
  const resp = await request.fetch(deploymentsUrl(`/${currentDeployment!.id}/rollback`), {
    method: 'POST', headers: authHeaders(), data: JSON.stringify({}),
  });
  lastApiResponse = { status: resp.status(), body: await resp.json().catch(() => ({})) };
});

Then('a new deployment is created with status {string}', async ({}, status: string) => {
  expect(lastApiResponse!.status).toBe(201);
  expect((lastApiResponse!.body as { status?: string }).status).toBe(status);
});

Then('the new deployment references the original deployment', async () => {
  expect((lastApiResponse!.body as { rollback_of?: string }).rollback_of).toBe(currentDeployment!.id);
});

// --- Status Updates ---

When('I update the deployment status to {string} with error {string}',
  async ({ request }, status: string, errorMsg: string) => {
    const resp = await request.fetch(deploymentsUrl(`/${currentDeployment!.id}/status`), {
      method: 'PATCH', headers: authHeaders(),
      data: JSON.stringify({ status, error_message: errorMsg }),
    });
    lastApiResponse = { status: resp.status(), body: await resp.json().catch(() => ({})) };
    if (resp.ok()) currentDeployment = lastApiResponse.body as typeof currentDeployment;
  });

Then('the deployment status is {string}', async ({}, status: string) => {
  expect(currentDeployment!.status).toBe(status);
});

Then('the deployment error message contains {string}', async ({}, msg: string) => {
  expect(String(currentDeployment!.error_message || '').toLowerCase()).toContain(msg.toLowerCase());
});
