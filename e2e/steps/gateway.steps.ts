/**
 * Gateway step definitions for STOA E2E Tests
 * Steps for testing API Gateway access control and runtime behavior
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// Store for test context
let currentApiKey: string | null = null;
let lastResponse: { status: number; body: any } | null = null;

// ============================================================================
// API KEY SETUP STEPS
// ============================================================================

Given('I have an active subscription to {string}', async () => {
  currentApiKey = process.env.TEST_API_KEY || 'test-api-key';
});

Given('I have my valid API Key', async () => {
  expect(currentApiKey).toBeTruthy();
});

Given('I do not have a subscription to {string}', async () => {
  currentApiKey = null;
});

Given('I have an invalid API key', async () => {
  currentApiKey = 'invalid-api-key-12345';
});

Given('I am {string} with an IOI subscription', async ({}, personaName: string) => {
  currentApiKey = process.env[`${personaName.toUpperCase()}_API_KEY`] || 'ioi-test-key';
});

Given('I have an active subscription with rate limit', async () => {
  currentApiKey = process.env.TEST_API_KEY || 'test-api-key';
});

Given('I have an expired access token', async () => {
  currentApiKey = 'expired-token-12345';
});

// ============================================================================
// API CALL STEPS
// ============================================================================

When('I call {string}', async ({ request }, endpoint: string) => {
  const [method, path] = endpoint.split(' ');

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (currentApiKey) {
    headers['X-API-Key'] = currentApiKey;
    headers['Authorization'] = `Bearer ${currentApiKey}`;
  }

  try {
    const response = await request.fetch(`${URLS.gateway}${path}`, {
      method: method as 'GET' | 'POST' | 'PUT' | 'DELETE',
      headers,
    });

    lastResponse = {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  } catch (error) {
    lastResponse = {
      status: 500,
      body: { error: String(error) },
    };
  }
});

When('I call {string} without API key', async ({ request }, endpoint: string) => {
  const [method, path] = endpoint.split(' ');

  try {
    const response = await request.fetch(`${URLS.gateway}${path}`, {
      method: method as 'GET' | 'POST' | 'PUT' | 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    lastResponse = {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  } catch (error) {
    lastResponse = {
      status: 500,
      body: { error: String(error) },
    };
  }
});

When('I make many health check calls', async ({ request }) => {
  const promises = Array(20)
    .fill(null)
    .map(() =>
      request.fetch(`${URLS.gateway}/health/ready`, {
        method: 'GET',
      }),
    );

  const responses = await Promise.all(promises);
  const statuses = responses.map(r => r.status());

  lastResponse = {
    status: statuses.every(s => s < 500) ? 200 : 500,
    body: { statuses, allOk: statuses.every(s => s < 500) },
  };
});

When('I make many API calls rapidly', async ({ request }) => {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (currentApiKey) {
    headers['X-API-Key'] = currentApiKey;
  }

  const promises = Array(20)
    .fill(null)
    .map(() =>
      request.fetch(`${URLS.gateway}/health/ready`, {
        method: 'GET',
        headers,
      }),
    );

  const responses = await Promise.all(promises);
  const statuses = responses.map(r => r.status());

  lastResponse = {
    status: statuses.every(s => s < 500) ? 200 : 500,
    body: { statuses },
  };
});

// ============================================================================
// RESPONSE ASSERTION STEPS
// ============================================================================

Then('I receive a {int} response', async ({}, expectedStatus: number) => {
  expect(lastResponse).not.toBeNull();
  expect(lastResponse!.status).toBe(expectedStatus);
});

Then('I receive a {int} error', async ({}, expectedStatus: number) => {
  expect(lastResponse).not.toBeNull();
  expect(lastResponse!.status).toBe(expectedStatus);
});

Then('I receive an auth error', async () => {
  expect(lastResponse).not.toBeNull();
  // Accept 401 (Unauthorized) or 403 (Forbidden) as valid auth rejection
  expect([401, 403]).toContain(lastResponse!.status);
});

Then('the gateway remains responsive', async () => {
  expect(lastResponse).not.toBeNull();
  // No 5xx errors — gateway stayed up
  expect(lastResponse!.status).toBeLessThan(500);
});

Then('the error message contains {string}', async ({}, expectedMessage: string) => {
  expect(lastResponse).not.toBeNull();
  const bodyStr = JSON.stringify(lastResponse!.body).toLowerCase();
  expect(bodyStr).toContain(expectedMessage.toLowerCase());
});

Then('some calls receive a {int} error', async ({}, expectedStatus: number) => {
  expect(lastResponse).not.toBeNull();
  expect(lastResponse!.status).toBe(expectedStatus);
});
