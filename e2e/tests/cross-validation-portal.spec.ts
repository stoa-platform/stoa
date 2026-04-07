/**
 * Portal Cross-Validation Tests (CAB-1993)
 *
 * Verifies seeded data appears in Portal UI via accessibility-first locators.
 * Requires live services (Control Plane API, Keycloak, Portal).
 */

import { test, expect } from '../fixtures/seeded-test';
import {
  assertPortalCatalogHasData,
  assertPortalSubscriptionsHasData,
} from '../fixtures/cross-validation-helpers';
import { assertNoEmptyStates, assertValidHeadingHierarchy } from '../fixtures/aria-helpers';

test.describe('Portal cross-validation', () => {
  test('API Catalog shows seeded APIs', async ({ seededData, page }) => {
    await page.goto('/apis');
    await page.waitForLoadState('networkidle');
    await assertPortalCatalogHasData(page, seededData);
  });

  test('Subscriptions page shows active subscriptions', async ({ seededData, page }) => {
    await page.goto('/subscriptions');
    await page.waitForLoadState('networkidle');
    await assertPortalSubscriptionsHasData(page, seededData);
  });

  test('Home page has no empty states after seed', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    await assertNoEmptyStates(page);
    await assertValidHeadingHierarchy(page);
  });
});
