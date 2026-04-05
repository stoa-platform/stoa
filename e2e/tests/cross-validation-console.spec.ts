/**
 * Console Cross-Validation Tests (CAB-1993)
 *
 * Verifies seeded data appears in Console UI via accessibility-first locators.
 * Requires live services (Control Plane API, Keycloak, Console).
 */

import { test, expect } from '../fixtures/seeded-test';
import {
  assertConsoleDashboardHasData,
  assertConsoleTenantsHasData,
  assertConsoleGatewaysHasData,
} from '../fixtures/cross-validation-helpers';

test.describe('Console cross-validation', () => {
  test('Operations Dashboard displays seeded data', async ({ seededData, page }) => {
    await page.goto('/operations');
    await page.waitForLoadState('networkidle');
    await assertConsoleDashboardHasData(page, seededData);
  });

  test('Tenants page shows high-five tenant', async ({ page }) => {
    await page.goto('/tenants');
    await page.waitForLoadState('networkidle');
    await assertConsoleTenantsHasData(page);

    // Verify the default test tenant is visible
    const tenantName = page.locator('[data-testid="tenant-name"]').first();
    await expect(tenantName).toContainText('high-five');
  });

  test('Gateways page has no empty states after seed', async ({ seededData: _seededData, page }) => {
    await page.goto('/gateway');
    await page.waitForLoadState('networkidle');
    await assertConsoleGatewaysHasData(page);
  });
});
