/**
 * ARIA Assertion Helpers for E2E tests (CAB-1990)
 *
 * Accessibility-first assertions using Playwright's role-based locators.
 * These helpers verify UI state through the accessibility tree, making
 * tests resilient to CSS/layout changes while asserting semantic correctness.
 */

import { Page, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Table assertions
// ---------------------------------------------------------------------------

/**
 * Assert that a table (identified by aria-label) has a specific number of rows.
 * Uses role-based locators: the table must have role="table" or be a <table>.
 *
 * @param page - Playwright page
 * @param tableName - The aria-label of the table
 * @param expectedMinRows - Minimum expected data rows (excludes header)
 */
export async function assertTableHasRows(
  page: Page,
  tableName: string,
  expectedMinRows: number,
): Promise<void> {
  const table = page.getByRole('table', { name: tableName });
  await expect(table).toBeVisible();

  const rows = table.getByRole('row');
  // First row is typically the header; data rows start from index 1
  const rowCount = await rows.count();
  const dataRows = Math.max(0, rowCount - 1);

  expect(dataRows).toBeGreaterThanOrEqual(expectedMinRows);
}

/**
 * Assert that a list (identified by aria-label) has a minimum number of items.
 * Works with role="list" containers and role="listitem" children.
 */
export async function assertListHasItems(
  page: Page,
  listName: string,
  expectedMinItems: number,
): Promise<void> {
  const list = page.getByRole('list', { name: listName });
  await expect(list).toBeVisible();

  const items = list.getByRole('listitem');
  const count = await items.count();

  expect(count).toBeGreaterThanOrEqual(expectedMinItems);
}

// ---------------------------------------------------------------------------
// Dashboard / metric assertions
// ---------------------------------------------------------------------------

/**
 * Assert that dashboard metric cards display expected values.
 * Locates cards by their data-testid (with `-count` suffix convention).
 *
 * @param page - Playwright page
 * @param expected - Map of data-testid → expected text content (substring match)
 */
export async function assertDashboardMetrics(
  page: Page,
  expected: Record<string, string>,
): Promise<void> {
  for (const [testId, expectedValue] of Object.entries(expected)) {
    const card = page.locator(`[data-testid="${testId}"]`);
    await expect(card).toBeVisible();
    await expect(card).toContainText(expectedValue);
  }
}

// ---------------------------------------------------------------------------
// Empty state detection
// ---------------------------------------------------------------------------

/** Common empty-state text patterns across STOA UI */
const EMPTY_STATE_PATTERNS = [
  'No data',
  'No results',
  'No APIs found',
  'No gateways registered',
  'No tenants',
  'No subscriptions',
  'No external MCP servers',
  'Loading...',
];

/**
 * Assert that no empty states or loading spinners are visible.
 * Useful after data seeding to confirm the UI displays real content.
 *
 * @param page - Playwright page
 * @param extraPatterns - Additional patterns to check (appended to defaults)
 */
export async function assertNoEmptyStates(
  page: Page,
  extraPatterns: string[] = [],
): Promise<void> {
  const patterns = [...EMPTY_STATE_PATTERNS, ...extraPatterns];

  for (const pattern of patterns) {
    const elements = page.getByText(pattern, { exact: false });
    const count = await elements.count();
    if (count > 0) {
      // Check visibility — hidden elements are OK (e.g., conditional renders)
      for (let i = 0; i < count; i++) {
        const el = elements.nth(i);
        const isVisible = await el.isVisible();
        if (isVisible) {
          throw new Error(
            `Empty state detected: found visible text "${pattern}" on page ${page.url()}`,
          );
        }
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Accessibility tree snapshot
// ---------------------------------------------------------------------------

/**
 * Capture the full accessibility tree of the page.
 * Useful for debugging and logging ARIA state during test failures.
 *
 * @param page - Playwright page
 * @returns Serialized accessibility snapshot (JSON-compatible object)
 */
export async function captureAriaTree(
  page: Page,
): Promise<Record<string, unknown> | null> {
  const snapshot = await page.accessibility.snapshot();
  return snapshot as Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Heading hierarchy validation
// ---------------------------------------------------------------------------

/**
 * Assert that the page has a valid heading hierarchy (no level skips).
 * E.g., h1 → h2 → h3 is valid; h1 → h3 (skipping h2) is invalid.
 */
export async function assertValidHeadingHierarchy(page: Page): Promise<void> {
  const headings = await page.evaluate(() => {
    const elements = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
    return Array.from(elements)
      .filter((el) => {
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden';
      })
      .map((el) => ({
        level: parseInt(el.tagName[1], 10),
        text: el.textContent?.trim().slice(0, 50) || '',
      }));
  });

  if (headings.length === 0) return;

  for (let i = 1; i < headings.length; i++) {
    const prev = headings[i - 1];
    const curr = headings[i];
    // A heading can go deeper by 1, stay same, or go up (any amount)
    if (curr.level > prev.level + 1) {
      throw new Error(
        `Heading hierarchy violation: h${prev.level} "${prev.text}" → h${curr.level} "${curr.text}" (skipped h${prev.level + 1})`,
      );
    }
  }
}
