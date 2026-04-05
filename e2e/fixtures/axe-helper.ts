/**
 * axe-core Accessibility Helper (CAB-1995)
 *
 * Thin wrapper around @axe-core/playwright for WCAG 2.1 AA scanning.
 * Used by a11y smoke tests to gate PRs on accessibility violations.
 */

import type { Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

export const THRESHOLD_LEVELS = ['minor', 'moderate', 'serious', 'critical'] as const;
export type ImpactLevel = (typeof THRESHOLD_LEVELS)[number];

/**
 * Default: block on critical only at launch (pre-existing serious violations
 * like aria-prohibited-attr need separate fix PRs). Ratchet schedule:
 *   Launch → critical | +2 cycles → serious | +4 cycles → moderate
 * Override via A11Y_IMPACT_THRESHOLD env.
 */
const DEFAULT_THRESHOLD: ImpactLevel = 'critical';

export interface ScanResult {
  /** Violations at or above the configured threshold */
  violations: Array<{
    id: string;
    impact: string;
    description: string;
    helpUrl: string;
    nodes: number;
  }>;
  /** Human-readable summary for test attachments */
  summary: string;
  /** Total violations (all severities, before threshold filter) */
  totalAll: number;
}

/**
 * Run an axe-core WCAG 2.1 AA scan on the current page.
 *
 * @param page - Playwright Page (must be navigated and rendered)
 * @param options - Optional: exclude selectors, override threshold
 * @returns Filtered violations + summary string
 */
export async function scanPage(
  page: Page,
  options?: { exclude?: string[]; threshold?: ImpactLevel },
): Promise<ScanResult> {
  const threshold =
    options?.threshold ??
    (process.env.A11Y_IMPACT_THRESHOLD as ImpactLevel | undefined) ??
    DEFAULT_THRESHOLD;

  const thresholdIndex = THRESHOLD_LEVELS.indexOf(threshold);

  let builder = new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa']);

  if (options?.exclude) {
    for (const selector of options.exclude) {
      builder = builder.exclude(selector);
    }
  }

  const results = await builder.analyze();

  const filtered = results.violations
    .filter((v) => {
      const level = v.impact as ImpactLevel;
      return THRESHOLD_LEVELS.indexOf(level) >= thresholdIndex;
    })
    .map((v) => ({
      id: v.id,
      impact: v.impact ?? 'unknown',
      description: v.description,
      helpUrl: v.helpUrl,
      nodes: v.nodes.length,
    }));

  const summary =
    filtered.length === 0
      ? `axe scan passed (threshold: ${threshold}, total scanned: ${results.violations.length} all-severity)`
      : filtered
          .map((v) => `[${v.impact}] ${v.id}: ${v.description} (${v.nodes} nodes) — ${v.helpUrl}`)
          .join('\n');

  return {
    violations: filtered,
    summary,
    totalAll: results.violations.length,
  };
}
