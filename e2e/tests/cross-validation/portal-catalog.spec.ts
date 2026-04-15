/**
 * Portal API Catalog Cross-Validation (CAB-1989 P1d)
 *
 * Seeds data via `seededData` fixture, navigates to the Discover page
 * (which hosts the API Catalog since CAB-1905), and asserts UI rows
 * match seeded API count via aria-helpers + data-testid locators.
 * Requires live Control Plane API + Portal.
 */

import { test, expect } from '../../fixtures/seeded-test';
import {
  assertNoEmptyStates,
  assertValidHeadingHierarchy,
  assertListHasItems,
} from '../../fixtures/aria-helpers';

test.describe('Portal API Catalog cross-validation', () => {
  test('Discover page shows seeded APIs in catalog grid', async ({ seededData, page }) => {
    // /apis redirects to /discover (CAB-1905)
    await page.goto('/discover');
    await page.waitForLoadState('networkidle');

    const resultsCount = page.locator('[data-testid="catalog-results-count"]');
    await expect(resultsCount).toBeVisible();

    // Seeded APIs must appear in the catalog list
    await assertListHasItems(page, 'API catalog', seededData.apis.length);
  });

  test('Discover page has no empty states after seed', async ({ seededData: _seededData, page }) => {
    await page.goto('/discover');
    await page.waitForLoadState('networkidle');

    await assertNoEmptyStates(page);
  });

  test('Discover page has correct heading hierarchy', async ({ page }) => {
    await page.goto('/discover');
    await page.waitForLoadState('networkidle');

    await assertValidHeadingHierarchy(page);
  });

  test('Catalog grid contains a card for each seeded API', async ({ seededData, page }) => {
    await page.goto('/discover');
    await page.waitForLoadState('networkidle');

    const catalogGrid = page.locator('[data-testid="catalog-grid"]');
    await expect(catalogGrid).toBeVisible();

    // Each seeded API should be findable by display_name
    for (const api of seededData.apis) {
      const apiCard = catalogGrid.getByText(api.display_name, { exact: false });
      await expect(apiCard.first()).toBeVisible();
    }
  });
});
