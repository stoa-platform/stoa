/**
 * Cross-Validation Assertion Helpers (CAB-1993)
 *
 * Page-specific assertion composers that combine ARIA helpers + data-testid
 * locators to verify seeded data is visible in the UI.
 */

import { Page, expect } from '@playwright/test';
import type { SeededState } from './data-seeder';
import {
  assertDashboardMetrics,
  assertNoEmptyStates,
  assertListHasItems,
  assertValidHeadingHierarchy,
} from './aria-helpers';

// ---------------------------------------------------------------------------
// Console assertions
// ---------------------------------------------------------------------------

/** Verify Dashboard KPI grid and sections show data (not empty states). */
export async function assertConsoleDashboardHasData(
  page: Page,
  _seededData: SeededState,
): Promise<void> {
  await expect(page.locator('[data-testid="dashboard-kpi-grid"]')).toBeVisible();
  await assertNoEmptyStates(page);
  await assertValidHeadingHierarchy(page);
}

/** Verify Tenants page lists at least one tenant. */
export async function assertConsoleTenantsHasData(page: Page): Promise<void> {
  const grid = page.locator('[data-testid="tenants-grid"]');
  await expect(grid).toBeVisible();
  await assertListHasItems(page, 'Tenants', 1);
}

/** Verify Gateways page shows registered gateways (no empty states). */
export async function assertConsoleGatewaysHasData(page: Page): Promise<void> {
  await assertNoEmptyStates(page);
  await assertValidHeadingHierarchy(page);
}

// ---------------------------------------------------------------------------
// Portal assertions
// ---------------------------------------------------------------------------

/** Verify API Catalog shows seeded APIs in the grid. */
export async function assertPortalCatalogHasData(
  page: Page,
  seededData: SeededState,
): Promise<void> {
  const resultsCount = page.locator('[data-testid="catalog-results-count"]');
  await expect(resultsCount).toBeVisible();
  await assertListHasItems(page, 'API catalog', seededData.apis.length);
  await assertNoEmptyStates(page);
}

/** Verify Subscriptions page shows active subscriptions. */
export async function assertPortalSubscriptionsHasData(
  page: Page,
  _seededData: SeededState,
): Promise<void> {
  const stats = page.locator('[data-testid="subscriptions-stats"]');
  await expect(stats).toBeVisible();
  const activeCount = page.locator('[data-testid="subscriptions-active-count"]');
  await expect(activeCount).toBeVisible();
  await expect(activeCount).not.toContainText('0');
}
