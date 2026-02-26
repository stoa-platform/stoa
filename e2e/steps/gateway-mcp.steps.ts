/**
 * MCP Resource, Prompt & Completion step definitions for STOA E2E Tests
 *
 * Tests MCP specification REST endpoints (CAB-1472):
 * - POST /mcp/resources/list, /mcp/resources/read, /mcp/resources/templates/list
 * - POST /mcp/prompts/list, /mcp/prompts/get
 * - POST /mcp/completion/complete
 * - GET /mcp/capabilities
 *
 * IMPORTANT: Uses its own response state (mcpResponse) because Then steps in
 * gateway.steps.ts reference a module-scoped lastResponse that is NOT shared
 * across files. All MCP Then steps use "the MCP ..." patterns to stay unique.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ---------------------------------------------------------------------------
// MCP response state (module-scoped, independent from gateway.steps.ts)
// ---------------------------------------------------------------------------

let mcpResponse: { status: number; body: any } | null = null;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function mcpPost(
  request: any,
  path: string,
  body: Record<string, unknown> = {},
): Promise<void> {
  try {
    const response = await request.fetch(`${URLS.gateway}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      data: JSON.stringify(body),
    });
    mcpResponse = {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  } catch (error: any) {
    mcpResponse = { status: 0, body: { error: error.message } };
  }
}

async function mcpGet(request: any, path: string): Promise<void> {
  try {
    const response = await request.fetch(`${URLS.gateway}${path}`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    mcpResponse = {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  } catch (error: any) {
    mcpResponse = { status: 0, body: { error: error.message } };
  }
}

// ---------------------------------------------------------------------------
// When steps — MCP endpoints
// ---------------------------------------------------------------------------

When('I request MCP capabilities', async ({ request }) => {
  await mcpGet(request, '/mcp/capabilities');
});

When('I list MCP resources', async ({ request }) => {
  await mcpPost(request, '/mcp/resources/list', {});
});

When('I read MCP resource {string}', async ({ request }, uri: string) => {
  await mcpPost(request, '/mcp/resources/read', { uri });
});

When('I read the first available MCP resource', async ({ request }) => {
  expect(mcpResponse).not.toBeNull();
  expect(mcpResponse!.body.resources).toBeDefined();
  expect(mcpResponse!.body.resources.length).toBeGreaterThan(0);

  const firstUri = mcpResponse!.body.resources[0].uri;
  await mcpPost(request, '/mcp/resources/read', { uri: firstUri });
});

When('I list MCP resource templates', async ({ request }) => {
  await mcpPost(request, '/mcp/resources/templates/list', {});
});

When('I list MCP prompts', async ({ request }) => {
  await mcpPost(request, '/mcp/prompts/list', {});
});

When('I get MCP prompt {string}', async ({ request }, name: string) => {
  await mcpPost(request, '/mcp/prompts/get', { name });
});

When(
  'I request MCP completion for prompt {string} argument {string} value {string}',
  async ({ request }, promptName: string, argName: string, argValue: string) => {
    await mcpPost(request, '/mcp/completion/complete', {
      ref: { type: 'ref/prompt', name: promptName },
      argument: { name: argName, value: argValue },
    });
  },
);

// ---------------------------------------------------------------------------
// Then steps — MCP-specific assertions (unique patterns, no collision)
// ---------------------------------------------------------------------------

Then('the MCP response status is {int}', async ({}, expectedStatus: number) => {
  expect(mcpResponse).not.toBeNull();
  expect(mcpResponse!.status).toBe(expectedStatus);
});

Then('the MCP response body has key {string}', async ({}, key: string) => {
  expect(mcpResponse).not.toBeNull();
  expect(mcpResponse!.body).toHaveProperty(key);
});

Then('the MCP capabilities include {string}', async ({}, capability: string) => {
  expect(mcpResponse).not.toBeNull();
  expect(mcpResponse!.body.capabilities).toBeDefined();
  expect(mcpResponse!.body.capabilities).toHaveProperty(capability);
});

Then('the MCP error contains {string}', async ({}, expectedMessage: string) => {
  expect(mcpResponse).not.toBeNull();
  const bodyStr = JSON.stringify(mcpResponse!.body).toLowerCase();
  expect(bodyStr).toContain(expectedMessage.toLowerCase());
});

Then(
  'the MCP response has {int} items in {string}',
  async ({}, count: number, key: string) => {
    expect(mcpResponse).not.toBeNull();
    expect(mcpResponse!.body).toHaveProperty(key);
    expect(mcpResponse!.body[key]).toHaveLength(count);
  },
);

Then(
  'the first resource template has uriTemplate {string}',
  async ({}, expectedTemplate: string) => {
    expect(mcpResponse).not.toBeNull();
    expect(mcpResponse!.body.resourceTemplates).toBeDefined();
    expect(mcpResponse!.body.resourceTemplates.length).toBeGreaterThan(0);
    expect(mcpResponse!.body.resourceTemplates[0].uriTemplate).toBe(expectedTemplate);
  },
);

Then('the MCP completion has empty values', async () => {
  expect(mcpResponse).not.toBeNull();
  expect(mcpResponse!.body.completion).toBeDefined();
  expect(mcpResponse!.body.completion.values).toEqual([]);
});

Then('the first content has valid JSON text', async () => {
  expect(mcpResponse).not.toBeNull();
  expect(mcpResponse!.body.contents).toBeDefined();
  expect(mcpResponse!.body.contents.length).toBeGreaterThan(0);
  const text = mcpResponse!.body.contents[0].text;
  expect(text).toBeDefined();
  expect(() => JSON.parse(text)).not.toThrow();
});
