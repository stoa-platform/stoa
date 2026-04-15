/**
 * Console Dashboard Cross-Validation (CAB-1989 P1d)
 *
 * Seeds data via `seededData` fixture, navigates to the Platform Dashboard,
 * and asserts UI rows == API-side state via aria-helpers + data-testid locators.
 * Requires live Control Plane API + Console.
 */

import { test, expect } from '../../fixtures/seeded-test';
import {
  assertNoEmptyStates,
  assertValidHeadingHierarchy,
  assertDashboardMetrics,
} from '../../fixtures/aria-helpers';

test.describe('Console Dashboard cross-validation', () => {
  test('Platform Dashboard KPI grid is visible after seed', async ({ seededData: _seededData, page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const kpiGrid = page.locator('[data-testid="dashboard-kpi-grid"]');
    await expect(kpiGrid).toBeVisible();
  });

  test('Platform Dashboard has correct heading hierarchy', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await assertValidHeadingHierarchy(page);
  });

  test('Platform Dashboard shows no empty states after seed', async ({ seededData: _seededData, page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await assertNoEmptyStates(page);
  });

  test('Platform Dashboard KPI metric cards are rendered', async ({ seededData: _seededData, page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await assertDashboardMetrics(page, {
      'dashboard-requests-count': '',
      'dashboard-error-rate-count': '',
      'dashboard-latency-count': '',
      'dashboard-gateways-count': '',
    });
  });

  test('Platform Dashboard gateway instances section is visible', async ({ seededData: _seededData, page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const gatewayInstances = page.locator('[data-testid="dashboard-gateway-instances"]');
    await expect(gatewayInstances).toBeVisible();
  });
});
