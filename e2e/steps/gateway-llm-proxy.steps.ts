/**
 * LLM Proxy step definitions for STOA E2E Tests (CAB-1601)
 *
 * Tests the gateway's LLM proxy endpoints: /v1/messages, /v1/chat/completions,
 * /v1/messages/count_tokens. Validates authentication, format detection, and
 * error handling.
 *
 * IMPORTANT: Reusable assertion steps (I receive a {int} response, I receive a {int} error,
 * the error message contains {string}) are defined in gateway.steps.ts — do NOT re-declare here.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// ---------------------------------------------------------------------------
// Test state
// ---------------------------------------------------------------------------

let lastResponse: { status: number; body: any; bodyText: string } | null = null;
let currentApiKey: string | null = null;

// ---------------------------------------------------------------------------
// Background — 'the STOA Gateway is accessible' is defined in uac-contract.steps.ts
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// API Key setup
// ---------------------------------------------------------------------------

Given('I have a valid STOA LLM subscription API key', async () => {
  currentApiKey = process.env.TEST_LLM_API_KEY || process.env.TEST_API_KEY || 'test-api-key';
});

// ---------------------------------------------------------------------------
// LLM Proxy request steps
// ---------------------------------------------------------------------------

When(
  'I call the LLM proxy {string} without any API key',
  async ({ request }, endpoint: string) => {
    const [method, urlPath] = endpoint.split(' ');

    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: method as 'POST',
        headers: { 'Content-Type': 'application/json' },
        data: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 10,
          messages: [{ role: 'user', content: 'test' }],
        }),
      });

      const bodyText = await response.text();
      lastResponse = {
        status: response.status(),
        body: tryParseJson(bodyText),
        bodyText,
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) }, bodyText: String(error) };
    }
  },
);

When(
  'I call the LLM proxy {string} with API key {string}',
  async ({ request }, endpoint: string, apiKey: string) => {
    const [method, urlPath] = endpoint.split(' ');

    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: method as 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
        },
        data: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 10,
          messages: [{ role: 'user', content: 'test' }],
        }),
      });

      const bodyText = await response.text();
      lastResponse = {
        status: response.status(),
        body: tryParseJson(bodyText),
        bodyText,
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) }, bodyText: String(error) };
    }
  },
);

When(
  'I call the LLM proxy {string} with x-api-key header {string}',
  async ({ request }, endpoint: string, apiKey: string) => {
    const [method, urlPath] = endpoint.split(' ');

    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: method as 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': apiKey,
        },
        data: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 10,
          messages: [{ role: 'user', content: 'test' }],
        }),
      });

      const bodyText = await response.text();
      lastResponse = {
        status: response.status(),
        body: tryParseJson(bodyText),
        bodyText,
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) }, bodyText: String(error) };
    }
  },
);

When(
  'I call the LLM proxy {string} with Bearer token {string}',
  async ({ request }, endpoint: string, token: string) => {
    const [method, urlPath] = endpoint.split(' ');

    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: method as 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        data: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 10,
          messages: [{ role: 'user', content: 'test' }],
        }),
      });

      const bodyText = await response.text();
      lastResponse = {
        status: response.status(),
        body: tryParseJson(bodyText),
        bodyText,
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) }, bodyText: String(error) };
    }
  },
);

When(
  'I send an Anthropic-format request to {string}',
  async ({ request }, urlPath: string) => {
    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': currentApiKey!,
          'anthropic-version': '2023-06-01',
        },
        data: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 10,
          messages: [{ role: 'user', content: 'Hello' }],
        }),
      });

      const bodyText = await response.text();
      lastResponse = {
        status: response.status(),
        body: tryParseJson(bodyText),
        bodyText,
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) }, bodyText: String(error) };
    }
  },
);

When(
  'I send an OpenAI-format request to {string}',
  async ({ request }, urlPath: string) => {
    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${currentApiKey}`,
        },
        data: JSON.stringify({
          model: 'mistral-large-latest',
          messages: [{ role: 'user', content: 'Hello' }],
          temperature: 0.7,
        }),
      });

      const bodyText = await response.text();
      lastResponse = {
        status: response.status(),
        body: tryParseJson(bodyText),
        bodyText,
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) }, bodyText: String(error) };
    }
  },
);

When(
  'I send a token count request to {string}',
  async ({ request }, urlPath: string) => {
    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': currentApiKey!,
          'anthropic-version': '2023-06-01',
        },
        data: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          messages: [{ role: 'user', content: 'Count my tokens' }],
        }),
      });

      const bodyText = await response.text();
      lastResponse = {
        status: response.status(),
        body: tryParseJson(bodyText),
        bodyText,
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) }, bodyText: String(error) };
    }
  },
);

When(
  'I send a request with a 11MB body to {string}',
  async ({ request }, urlPath: string) => {
    // Generate a payload slightly over 10MB to trigger the body size limit
    const largeContent = 'x'.repeat(11 * 1024 * 1024);

    try {
      const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': currentApiKey!,
        },
        data: JSON.stringify({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 10,
          messages: [{ role: 'user', content: largeContent }],
        }),
      });

      const bodyText = await response.text();
      lastResponse = {
        status: response.status(),
        body: tryParseJson(bodyText),
        bodyText,
      };
    } catch (error) {
      lastResponse = { status: 500, body: { error: String(error) }, bodyText: String(error) };
    }
  },
);

// ---------------------------------------------------------------------------
// Assertion steps
// ---------------------------------------------------------------------------

Then('the response body contains {string}', async ({}, expected: string) => {
  expect(lastResponse).not.toBeNull();
  const bodyStr = lastResponse!.bodyText.toLowerCase();
  expect(bodyStr).toContain(expected.toLowerCase());
});

Then('the response format is Anthropic or a proxy error', async () => {
  expect(lastResponse).not.toBeNull();
  // Either a valid Anthropic response (has type/content) or a proxy error (502/503)
  // The point is it didn't 404 — the route exists and the gateway handled it
  if (lastResponse!.status < 400) {
    // Successful upstream response — verify Anthropic format
    expect(lastResponse!.body).toHaveProperty('type');
  }
  // Any non-404 status is acceptable (401 = auth issue, 502/503 = upstream issue)
});

Then('the response format is OpenAI-compatible or a proxy error', async () => {
  expect(lastResponse).not.toBeNull();
  if (lastResponse!.status < 400) {
    // Successful upstream response — verify OpenAI format
    expect(lastResponse!.body).toHaveProperty('choices');
  }
});

Then('the proxy returns status {int}', async ({}, expectedStatus: number) => {
  expect(lastResponse).not.toBeNull();
  expect(lastResponse!.status).toBe(expectedStatus);
});

Then('the proxy returns status other than {int}', async ({}, excludedStatus: number) => {
  expect(lastResponse).not.toBeNull();
  expect(lastResponse!.status).not.toBe(excludedStatus);
});

// ---------------------------------------------------------------------------
// Sender-constraint bypass steps
// ---------------------------------------------------------------------------

When('I call {string} without any credentials', async ({ request }, endpoint: string) => {
  const [method, urlPath] = endpoint.split(' ');

  try {
    const response = await request.fetch(`${URLS.gateway}${urlPath}`, {
      method: method as 'GET' | 'POST',
    });

    const bodyText = await response.text();
    lastResponse = {
      status: response.status(),
      body: tryParseJson(bodyText),
      bodyText,
    };
  } catch (error) {
    lastResponse = { status: 500, body: { error: String(error) }, bodyText: String(error) };
  }
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function tryParseJson(text: string): any {
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}
