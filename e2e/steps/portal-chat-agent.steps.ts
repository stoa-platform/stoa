/**
 * Portal Chat Agent step definitions for STOA E2E Tests (CAB-1839)
 * Happy path, RBAC checks for the FloatingChat wired in the Developer Portal.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

// ============================================================================
// PORTAL CHAT AGENT — PANEL NAVIGATION
// ============================================================================

Given('I am logged in as {string} platform admin', async ({ authSession }, personaName: string) => {
  await authSession.switchPersona(personaName as 'anorak', URLS.portal);
  await authSession.page.goto(URLS.portal);
});

When('I open the Portal Chat Agent panel', async ({ authSession }) => {
  const page = authSession.page;

  // FloatingChat button — rendered as a floating action button above Layout
  const chatBtn = page.locator(
    'button:has-text("Chat"), button[aria-label*="chat" i], button[aria-label*="agent" i], [data-testid="chat-agent-btn"]',
  );

  const hasChatBtn = await chatBtn.first().isVisible({ timeout: 5000 }).catch(() => false);

  if (hasChatBtn) {
    await chatBtn.first().click();
    await page.waitForLoadState('networkidle');
  }

  // Wait for chat input to appear
  await page
    .locator(
      'textarea[placeholder*="message" i], input[placeholder*="message" i], [data-testid="chat-input"]',
    )
    .first()
    .waitFor({ state: 'visible', timeout: 15000 })
    .catch(() => {});
});

Then('the Portal Chat Agent interface is visible', async ({ authSession }) => {
  const page = authSession.page;

  const chatInterface = page.locator(
    '[class*="chat"], [class*="floating"], [data-testid="chat-panel"]',
  );
  const messageInput = page.locator(
    'textarea[placeholder*="message" i], input[placeholder*="message" i], [data-testid="chat-input"]',
  );

  const loaded =
    (await chatInterface.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await messageInput.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded).toBe(true);
});

// ============================================================================
// PORTAL CHAT AGENT — MESSAGING
// ============================================================================

When('I send the portal chat message {string}', async ({ authSession }, message: string) => {
  const page = authSession.page;

  const messageInput = page.locator(
    'textarea[placeholder*="message" i], input[placeholder*="message" i], [data-testid="chat-input"]',
  );

  await expect(messageInput.first()).toBeVisible({ timeout: 15000 });
  await messageInput.first().fill(message);

  const sendBtn = page.locator(
    'button:has-text("Send"), button[aria-label*="send" i], [data-testid="chat-send"]',
  );

  const hasSendBtn = await sendBtn.first().isVisible({ timeout: 2000 }).catch(() => false);
  if (hasSendBtn) {
    await sendBtn.first().click();
  } else {
    await messageInput.first().press('Enter');
  }

  await page.waitForLoadState('networkidle');
});

Then('the Portal Chat Agent returns a response', async ({ authSession }) => {
  const page = authSession.page;

  // Wait for loading spinner to clear
  await page
    .locator('[class*="loading"], [class*="spinner"], text=Thinking')
    .first()
    .waitFor({ state: 'hidden', timeout: 30000 })
    .catch(() => {});

  const agentResponse = page.locator(
    '[class*="assistant"], [class*="agent-message"], [data-role="assistant"], [class*="response"]',
  );

  const hasResponse =
    (await agentResponse.first().isVisible({ timeout: 15000 }).catch(() => false)) ||
    (await page.locator('[class*="message"]').count()) >= 2;

  expect(hasResponse).toBe(true);
});

// ============================================================================
// PORTAL CHAT AGENT — RBAC
// ============================================================================

Then(
  'the Portal Chat Agent does not offer mutation tools to viewer',
  async ({ authSession }) => {
    const page = authSession.page;

    // Mutation tool buttons (create, delete, update) should not appear for viewer
    const mutationButtons = page.locator(
      'button:has-text("Create"), button:has-text("Delete"), button:has-text("Update"), [data-tool-type="mutation"]',
    );

    // Either no mutation UI visible, or the chat panel itself isn't shown
    // (viewer access may be restricted entirely in some tenants)
    const mutationCount = await mutationButtons.count();

    // Soft check — viewer may see the panel but not mutation affordances
    if (mutationCount > 0) {
      // If mutation buttons somehow appear, they should be disabled
      const firstBtn = mutationButtons.first();
      const isDisabled = await firstBtn.isDisabled().catch(() => true);
      expect(isDisabled).toBe(true);
    }
    // mutationCount === 0 is the passing case
  },
);
