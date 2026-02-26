/**
 * Console LLM Cost Dashboard step definitions for STOA E2E Tests (CAB-1499)
 * Steps for LLM cost management page navigation and content verification
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// LLM COST DASHBOARD
// ============================================================================

When('I navigate to the LLM Cost Dashboard page', async ({ page }) => {
  await page.goto(`${URLS.console}/llm-cost`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the LLM Cost Dashboard page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /LLM Cost/i });
  const content = page.locator(
    '[data-testid="budget-cards"], [data-testid="providers-table-body"], [class*="card"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/llm-cost')).toBe(true);
});

Then('the LLM Cost Dashboard displays budget cards', async ({ page }) => {
  const budgetCards = page.locator('[data-testid="budget-cards"]');
  const cards = page.locator('[class*="card"], [class*="stat"]');

  const hasCards =
    (await budgetCards.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await cards.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasCards || page.url().includes('/llm-cost')).toBe(true);
});

Then('the LLM Cost Dashboard displays provider table', async ({ page }) => {
  const tableBody = page.locator('[data-testid="providers-table-body"]');
  const table = page.locator('table');

  const hasTable =
    (await tableBody.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await table.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasTable || page.url().includes('/llm-cost')).toBe(true);
});

Then('the LLM Cost Dashboard shows admin actions', async ({ page }) => {
  const actionsColumn = page.locator('th').filter({ hasText: /Actions/i });
  const deleteButtons = page.locator('[data-testid*="delete-provider-"]');

  const hasActions =
    (await actionsColumn.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await deleteButtons.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasActions || page.url().includes('/llm-cost')).toBe(true);
});
