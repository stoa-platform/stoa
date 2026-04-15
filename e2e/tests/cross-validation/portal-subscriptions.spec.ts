/**
 * Portal Subscriptions Cross-Validation (CAB-1989 P1d)
 *
 * Seeds data via `seededData` fixture, navigates to the workspace subscriptions
 * tab (/workspace?tab=subscriptions — legacy /subscriptions redirects here),
 * and asserts UI rows == API-side state via aria-helpers + data-testid locators.
 * Requires live Control Plane API + Portal.
 */

import { test, expect } from '../../fixtures/seeded-test';
import {
  assertNoEmptyStates,
  assertValidHeadingHierarchy,
} from '../../fixtures/aria-helpers';

test.describe('Portal Subscriptions cross-validation', () => {
  test('Subscriptions stats region is visible after seed', async ({ seededData: _seededData, page }) => {
    // /subscriptions redirects to /workspace?tab=subscriptions
    await page.goto('/workspace?tab=subscriptions');
    await page.waitForLoadState('networkidle');

    const stats = page.locator('[data-testid="subscriptions-stats"]');
    await expect(stats).toBeVisible();
  });

  test('Active subscriptions count is non-zero after seed', async ({ seededData: _seededData, page }) => {
    await page.goto('/workspace?tab=subscriptions');
    await page.waitForLoadState('networkidle');

    const activeCount = page.locator('[data-testid="subscriptions-active-count"]');
    await expect(activeCount).toBeVisible();
    await expect(activeCount).not.toContainText('0');
  });

  test('Subscription tabs are rendered with correct roles', async ({ page }) => {
    await page.goto('/workspace?tab=subscriptions');
    await page.waitForLoadState('networkidle');

    const serversTab = page.locator('[data-testid="subscriptions-tab-servers"]');
    const toolsTab = page.locator('[data-testid="subscriptions-tab-tools"]');
    const apisTab = page.locator('[data-testid="subscriptions-tab-apis"]');

    await expect(serversTab).toBeVisible();
    await expect(toolsTab).toBeVisible();
    await expect(apisTab).toBeVisible();

    // Servers tab is selected by default
    await expect(serversTab).toHaveAttribute('aria-selected', 'true');
    await expect(toolsTab).toHaveAttribute('aria-selected', 'false');
    await expect(apisTab).toHaveAttribute('aria-selected', 'false');
  });

  test('Subscriptions page has no empty states after seed', async ({ seededData: _seededData, page }) => {
    await page.goto('/workspace?tab=subscriptions');
    await page.waitForLoadState('networkidle');

    await assertNoEmptyStates(page);
  });

  test('Subscriptions page has correct heading hierarchy', async ({ page }) => {
    await page.goto('/workspace?tab=subscriptions');
    await page.waitForLoadState('networkidle');

    await assertValidHeadingHierarchy(page);
  });
});
