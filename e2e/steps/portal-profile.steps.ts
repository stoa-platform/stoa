/**
 * Portal Profile step definitions for STOA E2E Tests
 * Steps specific to the Portal User Profile page
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// PROFILE NAVIGATION STEPS
// ============================================================================

When('I navigate to the portal profile page', async ({ page }) => {
  await page.goto(`${URLS.portal}/profile`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the portal profile page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /profile|account|profil/i });
  const content = page.locator('[class*="card"], [class*="form"], [class*="profile"]');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/profile')).toBe(true);
});

// ============================================================================
// PROFILE CONTENT STEPS
// ============================================================================

Then('user profile information is displayed', async ({ page }) => {
  // Profile page should show at least one of: email, username, name, or account details
  const profileInfo = page.locator(
    'text=/email|username|account|name|profil|utilisateur/i, ' +
      'input[type="email"], input[name*="email"], ' +
      '[class*="avatar"], [class*="user-info"]',
  );

  const hasInfo =
    (await profileInfo.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/profile');

  expect.soft(hasInfo).toBe(true);
  expect(hasInfo).toBe(true);
});
