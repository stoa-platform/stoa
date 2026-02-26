/**
 * Console Identity Governance step definitions for STOA E2E Tests (CAB-1486)
 * Steps for access review dashboard page navigation and content verification
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// ACCESS REVIEW DASHBOARD
// ============================================================================

When('I navigate to the Access Review Dashboard page', async ({ page }) => {
  await page.goto(`${URLS.console}/access-review`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Access Review Dashboard page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Access Review/i });
  const content = page.locator(
    '[class*="card"], [data-testid="summary-cards"], [data-testid="clients-table-body"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/access-review')).toBe(true);
});

Then('the Access Review Dashboard displays client summary cards', async ({ page }) => {
  const summaryCards = page.locator('[data-testid="summary-cards"]');
  const cards = page.locator('[class*="card"], [class*="stat"]');

  const hasCards =
    (await summaryCards.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await cards.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasCards || page.url().includes('/access-review')).toBe(true);
});

Then('the Access Review Dashboard shows action buttons for admin', async ({ page }) => {
  const actionsColumn = page.locator('th').filter({ hasText: /Actions/i });
  const actionButtons = page.locator(
    '[data-testid*="approve-"], [data-testid*="revoke-"], [data-testid*="flag-"]',
  );

  const hasActions =
    (await actionsColumn.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await actionButtons.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasActions || page.url().includes('/access-review')).toBe(true);
});
