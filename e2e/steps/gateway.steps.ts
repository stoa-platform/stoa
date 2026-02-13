/**
 * Gateway step definitions for STOA E2E Tests
 * Steps for testing API Gateway access control and runtime behavior
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const { Given, When, Then } = createBdd(test);

// Store for test context
let currentApiKey: string | null = null;
let lastResponse: { status: number; body: any } | null = null;

// mTLS test context
let currentToken: string | null = null;
let currentFingerprint: string | null = null;

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

// ============================================================================
// mTLS STEPS (CAB-864 / CAB-872)
// ============================================================================

const CERTS_DIR = path.resolve(__dirname, '../../scripts/demo/certs');
const AUTH_URL = process.env.STOA_AUTH_URL || 'https://auth.gostoa.dev';

/**
 * Load consumer credentials from seed output or environment variables.
 */
function loadConsumerCredentials(consumerId: string): {
  clientId: string;
  clientSecret: string;
} {
  // Try credentials.json first (generated by seed-mtls-demo.py)
  const credsPath = path.join(CERTS_DIR, 'credentials.json');
  if (fs.existsSync(credsPath)) {
    const data = JSON.parse(fs.readFileSync(credsPath, 'utf-8'));
    const credentials = data.credentials || data;
    const entry = credentials.find(
      (c: { external_id?: string; client_id?: string }) =>
        c.external_id === consumerId || c.client_id === `mtls-${consumerId}`
    );
    if (entry) {
      return { clientId: entry.client_id, clientSecret: entry.client_secret };
    }
  }

  // Fallback to env vars
  const envKey = consumerId.replace(/-/g, '_').toUpperCase();
  const clientId = process.env[`MTLS_${envKey}_CLIENT_ID`] || '';
  const clientSecret = process.env[`MTLS_${envKey}_CLIENT_SECRET`] || '';
  if (!clientId || !clientSecret) {
    throw new Error(
      `No credentials for ${consumerId}. Run seed-mtls-demo.py or set MTLS_${envKey}_CLIENT_ID/SECRET`
    );
  }
  return { clientId, clientSecret };
}

/**
 * Load fingerprint from fingerprints.csv.
 */
function loadFingerprint(consumerId: string): string {
  const fpPath = path.join(CERTS_DIR, 'fingerprints.csv');
  if (!fs.existsSync(fpPath)) {
    throw new Error(`Fingerprints CSV not found at ${fpPath}. Run generate-mtls-certs.sh first.`);
  }
  const lines = fs.readFileSync(fpPath, 'utf-8').trim().split('\n');
  // CSV: external_id,fingerprint_hex,fingerprint_b64url,subject_dn,company
  for (const line of lines.slice(1)) {
    const [extId, fpHex] = line.split(',');
    if (extId === consumerId) {
      return fpHex;
    }
  }
  throw new Error(`Fingerprint not found for ${consumerId} in ${fpPath}`);
}

Given(
  'I have a cert-bound token for consumer {string}',
  async ({ request }, consumerId: string) => {
    const { clientId, clientSecret } = loadConsumerCredentials(consumerId);
    currentFingerprint = loadFingerprint(consumerId);

    // Get cert-bound token from Keycloak (client_credentials grant)
    const tokenResponse = await request.fetch(
      `${AUTH_URL}/realms/stoa/protocol/openid-connect/token`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        data: `grant_type=client_credentials&client_id=${encodeURIComponent(clientId)}&client_secret=${encodeURIComponent(clientSecret)}`,
      }
    );

    expect(tokenResponse.ok()).toBeTruthy();
    const tokenData = await tokenResponse.json();
    currentToken = tokenData.access_token;
    expect(currentToken).toBeTruthy();
  }
);

When(
  'I call {string} with mTLS headers',
  async ({ request }, endpoint: string) => {
    const [method, ...pathParts] = endpoint.split(' ');
    const urlPath = pathParts.join(' ');

    expect(currentToken).not.toBeNull();
    expect(currentFingerprint).not.toBeNull();

    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: method as 'GET' | 'POST' | 'PUT' | 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${currentToken}`,
          'X-SSL-Client-Verify': 'SUCCESS',
          'X-SSL-Client-Fingerprint': currentFingerprint!,
          'X-SSL-Client-S-DN': 'CN=api-consumer-001,OU=tenant-acme,O=Acme Corp,C=FR',
          'X-SSL-Client-I-DN': 'CN=STOA Demo CA,O=STOA Platform,C=FR',
        },
        data: JSON.stringify({ tool: 'petstore', arguments: { action: 'list-pets' } }),
      });

      lastResponse = {
        status: response.status(),
        body: await response.json().catch(() => ({})),
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) } };
    }
  }
);

When(
  'I call {string} with wrong mTLS certificate',
  async ({ request }, endpoint: string) => {
    const [method, ...pathParts] = endpoint.split(' ');
    const urlPath = pathParts.join(' ');

    expect(currentToken).not.toBeNull();

    const wrongFingerprint =
      '0000000000000000000000000000000000000000000000000000000000000000';

    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: method as 'GET' | 'POST' | 'PUT' | 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${currentToken}`,
          'X-SSL-Client-Verify': 'SUCCESS',
          'X-SSL-Client-Fingerprint': wrongFingerprint,
          'X-SSL-Client-S-DN': 'CN=attacker,OU=evil-corp,O=Evil Inc,C=XX',
          'X-SSL-Client-I-DN': 'CN=STOA Demo CA,O=STOA Platform,C=FR',
        },
        data: JSON.stringify({ tool: 'petstore', arguments: { action: 'list-pets' } }),
      });

      lastResponse = {
        status: response.status(),
        body: await response.json().catch(() => ({})),
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) } };
    }
  }
);

When(
  'I call {string} without mTLS certificate',
  async ({ request }, endpoint: string) => {
    const [method, ...pathParts] = endpoint.split(' ');
    const urlPath = pathParts.join(' ');

    expect(currentToken).not.toBeNull();

    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: method as 'GET' | 'POST' | 'PUT' | 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${currentToken}`,
        },
        data: JSON.stringify({ tool: 'petstore', arguments: { action: 'list-pets' } }),
      });

      lastResponse = {
        status: response.status(),
        body: await response.json().catch(() => ({})),
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) } };
    }
  }
);
