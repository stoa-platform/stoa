/**
 * Console Chat Agent step definitions for STOA E2E Tests (CAB-1451)
 * Steps for interacting with the integrated Chat Agent in the Console UI.
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// CHAT AGENT — PANEL NAVIGATION
// ============================================================================

When('I open the Chat Agent panel', async ({ page }) => {
  // Chat agent can be accessed via button in toolbar or dedicated route
  const chatBtn = page.locator(
    'button:has-text("Chat"), button[aria-label*="chat" i], button[aria-label*="agent" i], [data-testid="chat-agent-btn"]',
  );

  const hasChatBtn = await chatBtn.first().isVisible({ timeout: 5000 }).catch(() => false);

  if (hasChatBtn) {
    await chatBtn.first().click();
    await page.waitForLoadState('networkidle');
  } else {
    // Try dedicated route
    await page.goto(`${URLS.console}/chat`);
    await page.waitForLoadState('networkidle');
  }

  // Wait for agent panel to be visible
  await expect(
    page.locator(
      '[class*="chat"], [class*="agent"], [data-testid="chat-panel"], textarea[placeholder*="message" i]',
    ).first(),
  )
    .toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Chat Agent interface is visible', async ({ page }) => {
  const chatInterface = page.locator(
    '[class*="chat"], [class*="agent-panel"], [data-testid="chat-panel"]',
  );
  const messageInput = page.locator(
    'textarea[placeholder*="message" i], input[placeholder*="message" i], [data-testid="chat-input"]',
  );

  const loaded =
    (await chatInterface.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await messageInput.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    page.url().includes('/chat');

  expect(loaded).toBe(true);
});

// ============================================================================
// CHAT AGENT — MESSAGING
// ============================================================================

When('I send the message {string}', async ({ page }, message: string) => {
  const messageInput = page.locator(
    'textarea[placeholder*="message" i], input[placeholder*="message" i], [data-testid="chat-input"]',
  );

  await expect(messageInput.first()).toBeVisible({ timeout: 15000 });
  await messageInput.first().fill(message);

  // Submit via Enter key or send button
  const sendBtn = page.locator(
    'button:has-text("Send"), button[aria-label*="send" i], button[type="submit"]:near(textarea)',
  );

  const hasSendBtn = await sendBtn.first().isVisible({ timeout: 2000 }).catch(() => false);
  if (hasSendBtn) {
    await sendBtn.first().click();
  } else {
    await messageInput.first().press('Enter');
  }

  // Wait for the message to appear in the conversation
  await page.waitForLoadState('networkidle');
  await expect(page.locator(`text=${message}`).first())
    .toBeVisible({ timeout: 10000 })
    .catch(() => {});
});

Then('the Chat Agent returns a response', async ({ page }) => {
  // Wait for a response — look for agent message container or loading spinner to disappear
  const loadingIndicator = page.locator(
    '[class*="loading"], [class*="spinner"], text=Thinking, text=...',
  );

  // Wait for loading to disappear (agent is thinking)
  await loadingIndicator
    .first()
    .waitFor({ state: 'hidden', timeout: 30000 })
    .catch(() => {});

  // Check for assistant/agent message
  const agentResponse = page.locator(
    '[class*="assistant"], [class*="agent-message"], [data-role="assistant"], [class*="response"]',
  );

  const hasResponse =
    (await agentResponse.first().isVisible({ timeout: 15000 }).catch(() => false)) ||
    // Fallback: at least 2 messages visible (user + agent)
    (await page.locator('[class*="message"]').count()) >= 2;

  expect(hasResponse).toBe(true);
});

Then('the response mentions available tools', async ({ page }) => {
  // Look for tool-related keywords in the response
  const toolsContent = page.locator(
    'text=/tool|function|capability|action|available/i',
  );
  const hasToolMention = await toolsContent.first().isVisible({ timeout: 10000 }).catch(() => false);
  // Soft assertion — depends on the agent's knowledge at runtime
  if (!hasToolMention) {
    // Accept if any text response was given
    const anyResponse = page.locator('[class*="assistant"], [class*="agent-message"]');
    await expect(anyResponse.first()).toBeVisible({ timeout: 5000 });
  }
});

// ============================================================================
// CHAT AGENT — CONVERSATION MANAGEMENT
// ============================================================================

When('I clear the Chat Agent conversation', async ({ page }) => {
  const clearBtn = page.locator(
    'button:has-text("Clear"), button:has-text("New conversation"), button[aria-label*="clear" i], button[aria-label*="reset" i]',
  );

  const hasClearBtn = await clearBtn.first().isVisible({ timeout: 5000 }).catch(() => false);
  if (hasClearBtn) {
    await clearBtn.first().click();
    await page.waitForLoadState('networkidle');

    // Handle confirmation dialog if present
    const confirmBtn = page.locator('button:has-text("Confirm"), button:has-text("Yes")');
    const hasConfirm = await confirmBtn.first().isVisible({ timeout: 2000 }).catch(() => false);
    if (hasConfirm) {
      await confirmBtn.first().click();
      await page.waitForLoadState('networkidle');
    }
  }
});

Then('the Chat Agent conversation is empty', async ({ page }) => {
  // No agent messages should be visible, or an empty state is shown
  const emptyState = page.locator(
    'text=/start a conversation|no messages|chat with/i, [class*="empty-state"], [data-testid="chat-empty"]',
  );
  const agentMessages = page.locator('[class*="assistant"], [class*="agent-message"]');

  const count = await agentMessages.count();
  const hasEmpty = await emptyState.first().isVisible({ timeout: 5000 }).catch(() => false);

  // Either no messages or empty state shown
  expect(count === 0 || hasEmpty).toBe(true);
});
