/**
 * Dynamic Value Masking for Visual Regression (CAB-1994)
 *
 * Builds a mask array from data-testid suffix conventions.
 * Elements with -count, -timestamp, -duration suffixes contain
 * dynamic values that would cause false visual diffs.
 */

import type { Locator, Page } from '@playwright/test';

const DYNAMIC_SUFFIXES = ['-count', '-timestamp', '-duration'];

/**
 * Collect all locators matching dynamic data-testid suffixes.
 * Returns an array suitable for Playwright's toHaveScreenshot({ mask }).
 */
export function buildMaskLocators(page: Page): Locator[] {
  return DYNAMIC_SUFFIXES.map((suffix) => page.locator(`[data-testid$="${suffix}"]`));
}
