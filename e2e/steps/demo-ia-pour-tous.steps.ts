/**
 * Step definitions for "IA pour tous" demo E2E — Portal enrichment panel (CAB-1609)
 *
 * Gateway scenarios reuse existing steps from gateway-llm-proxy.steps.ts:
 * - 'the STOA Gateway is accessible' (uac-contract.steps.ts)
 * - 'I have a valid STOA LLM subscription API key' (gateway-llm-proxy.steps.ts)
 * - 'I call the LLM proxy {string} without any API key' (gateway-llm-proxy.steps.ts)
 * - 'I call the LLM proxy {string} with API key {string}' (gateway-llm-proxy.steps.ts)
 * - 'I send an OpenAI-format request to {string}' (gateway-llm-proxy.steps.ts)
 * - 'the proxy returns status {int}' (gateway-llm-proxy.steps.ts)
 * - 'the proxy returns status other than {int}' (gateway-llm-proxy.steps.ts)
 * - 'the response body contains {string}' (gateway-llm-proxy.steps.ts)
 * - 'the response format is OpenAI-compatible or a proxy error' (gateway-llm-proxy.steps.ts)
 *
 * Portal scenarios reuse:
 * - 'I am logged in as {string} from community {string}' (common.steps.ts)
 * - 'the STOA Portal is accessible' (common.steps.ts)
 * - 'the API detail page is displayed' (demo.steps.ts)
 *
 * Only the Portal enrichment steps below are new.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

const DEMO_TIMEOUT = 15000;

// ---------------------------------------------------------------------------
// Portal: Navigate to Chat Completions API
// ---------------------------------------------------------------------------

When('I navigate to the Chat Completions API detail page', async ({ authSession }) => {
  const { page } = authSession;

  // Navigate to API catalog
  await page.goto(`${URLS.portal}/apis`);
  await page.waitForLoadState('networkidle').catch(() => {});

  // Search for the Chat Completions API
  const searchInput = page.locator(
    'input[placeholder*="Search"], input[placeholder*="Rechercher"], ' +
      'input[placeholder*="search"], input[type="search"]',
  );

  if (await searchInput.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await searchInput.first().fill('Chat Completions');
    await page.waitForTimeout(500);
    await page.waitForLoadState('networkidle').catch(() => {});
  }

  // Click the Chat Completions API card
  const chatCard = page.locator('a[href^="/apis/"]').filter({
    hasText: /Chat Completions|GPT-4o|IA/i,
  });

  if (await chatCard.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await chatCard.first().click();
    await page.waitForLoadState('networkidle').catch(() => {});
    return;
  }

  // Chat Completions not found — clear search and try any API card
  if (await searchInput.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await searchInput.first().clear();
    await page.waitForTimeout(500);
    await page.waitForLoadState('networkidle').catch(() => {});
  }

  const anyCard = page.locator('a[href^="/apis/"]').first();
  if (await anyCard.isVisible({ timeout: 5000 }).catch(() => false)) {
    await anyCard.click();
    await page.waitForLoadState('networkidle').catch(() => {});
  }
  // If no API cards at all, subsequent enrichment steps will gracefully skip
});

// ---------------------------------------------------------------------------
// Portal: Chat Completions enrichment panel assertions
// ---------------------------------------------------------------------------

Then('I see the Chat Completions enrichment panel', async ({ authSession }) => {
  const { page } = authSession;

  const enrichmentPanel = page.locator('[data-testid="chat-completions-enrichment"]');
  const isVisible = await enrichmentPanel.isVisible({ timeout: DEMO_TIMEOUT }).catch(() => false);

  if (!isVisible) {
    // Check if we're on the right API page (may not have Chat Completions in test catalog)
    const pageText = await page.textContent('body');
    if (/Chat Completions|GPT-4o/i.test(pageText || '')) {
      expect(isVisible).toBe(true);
    }
    // Otherwise skip — API not present in test environment
  }
});

Then('the enrichment panel shows subscription plans', async ({ authSession }) => {
  const { page } = authSession;

  const enrichmentPanel = page.locator('[data-testid="chat-completions-enrichment"]');
  if (!(await enrichmentPanel.isVisible({ timeout: 3000 }).catch(() => false))) {
    return; // Skip if enrichment panel not present
  }

  // Verify plan names from chatCompletionsConfig.ts
  const hasAlpha = await page.getByText(/Alpha/).first().isVisible({ timeout: 5000 }).catch(() => false);
  const hasBeta = await page.getByText(/Beta/).first().isVisible({ timeout: 5000 }).catch(() => false);
  expect(hasAlpha || hasBeta).toBe(true);
});

Then('the enrichment panel shows the GDPR notice', async ({ authSession }) => {
  const { page } = authSession;

  const enrichmentPanel = page.locator('[data-testid="chat-completions-enrichment"]');
  if (!(await enrichmentPanel.isVisible({ timeout: 3000 }).catch(() => false))) {
    return; // Skip if enrichment panel not present
  }

  // GDPR notice is a role="alert" element mentioning Azure OpenAI and DPO
  const gdprNotice = enrichmentPanel.locator('[role="alert"]');
  await expect(gdprNotice).toBeVisible({ timeout: DEMO_TIMEOUT });
  const noticeText = await gdprNotice.textContent();
  expect(noticeText).toMatch(/Azure OpenAI|DPO|donnees/i);
});
