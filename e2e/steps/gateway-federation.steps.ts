/**
 * Gateway step definitions for Federation Routing (CAB-1373)
 * Steps for testing federation sub-account API access and metering headers.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

const GATEWAY_URL = process.env.STOA_GATEWAY_URL || 'https://mcp.gostoa.dev';

// Federation test context
let federationApiKey: string | null = null;
let allowedTools: Set<string> = new Set();
let lastFederationResponse: {
  status: number;
  body: Record<string, unknown>;
  headers: Record<string, string>;
} | null = null;

// ============================================================================
// FEDERATION — API KEY SETUP
// ============================================================================

Given('I have a federation sub-account API key', async () => {
  federationApiKey = process.env.FEDERATION_SUB_ACCOUNT_KEY || 'fed-sub-test-key';
  allowedTools = new Set(['echo-tool']); // Default allowed tools
});

Given('I have a revoked federation sub-account API key', async () => {
  federationApiKey = process.env.FEDERATION_REVOKED_KEY || 'fed-revoked-test-key';
});

// ============================================================================
// FEDERATION — TOOL ALLOW/DENY
// ============================================================================

Given(
  'the sub-account is allowed to call {string}',
  async ({}, toolName: string) => {
    allowedTools.add(toolName);
  },
);

Given(
  'the sub-account is not allowed to call {string}',
  async ({}, toolName: string) => {
    allowedTools.delete(toolName);
  },
);

// ============================================================================
// FEDERATION — TOOL CALL
// ============================================================================

When(
  'I call the tool {string} via the gateway',
  async ({ request }, toolName: string) => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (federationApiKey) {
      headers['X-API-Key'] = federationApiKey;
      headers['Authorization'] = `Bearer ${federationApiKey}`;
    }

    try {
      const response = await request.fetch(`${GATEWAY_URL}/mcp/tools/call`, {
        method: 'POST',
        headers,
        data: JSON.stringify({
          name: toolName,
          arguments: { input: 'e2e-test' },
        }),
      });

      const responseHeaders: Record<string, string> = {};
      const headersList = response.headers();
      for (const [key, value] of Object.entries(headersList)) {
        responseHeaders[key.toLowerCase()] = value;
      }

      lastFederationResponse = {
        status: response.status(),
        body: (await response.json().catch(() => ({}))) as Record<string, unknown>,
        headers: responseHeaders,
      };
    } catch (error) {
      lastFederationResponse = {
        status: 500,
        body: { error: String(error) },
        headers: {},
      };
    }
  },
);

// ============================================================================
// FEDERATION — RESPONSE ASSERTIONS
// ============================================================================

Then('the response status is {int}', async ({}, expectedStatus: number) => {
  expect(lastFederationResponse).not.toBeNull();
  expect(lastFederationResponse!.status).toBe(expectedStatus);
});

Then('the response includes the tool result', async () => {
  expect(lastFederationResponse).not.toBeNull();
  const body = lastFederationResponse!.body;
  // Tool result should have content or result field
  const hasResult =
    'content' in body || 'result' in body || 'output' in body || 'data' in body;
  expect(hasResult).toBe(true);
});

Then('the response includes {string}', async ({}, expectedText: string) => {
  expect(lastFederationResponse).not.toBeNull();
  const bodyStr = JSON.stringify(lastFederationResponse!.body).toLowerCase();
  expect(bodyStr).toContain(expectedText.toLowerCase());
});

Then(
  'the response header includes {string}',
  async ({}, headerName: string) => {
    expect(lastFederationResponse).not.toBeNull();
    const lowerHeader = headerName.toLowerCase();
    const hasHeader = lowerHeader in lastFederationResponse!.headers;
    expect(hasHeader).toBe(true);
  },
);
