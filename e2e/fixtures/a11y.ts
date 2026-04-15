/**
 * axe-core Accessibility Gate Helpers (CAB-1989 P4)
 *
 * Public API for writing a11y assertions in Playwright specs.
 * For internal scan details see axe-helper.ts.
 *
 * Gate policy:
 *   critical + serious  → CI fail  (hard assertion)
 *   moderate + minor    → warn only (logged as annotation)
 */

import type { Page, TestInfo } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

export type ImpactLevel = 'minor' | 'moderate' | 'serious' | 'critical';

const IMPACT_ORDER: ImpactLevel[] = ['minor', 'moderate', 'serious', 'critical'];

export interface A11yOptions {
  /** CSS selectors to exclude from the scan (e.g. third-party widgets). */
  exclude?: string[];
  /** WCAG tag filters. Default: ['wcag2a', 'wcag2aa']. */
  tags?: string[];
}

export interface A11yViolation {
  id: string;
  impact: ImpactLevel;
  description: string;
  helpUrl: string;
  nodes: number;
}

export interface A11yResult {
  violations: A11yViolation[];
  /** All violations regardless of level, for warn-only reporting. */
  all: A11yViolation[];
}

/**
 * Run an axe-core scan and return structured results.
 * Does NOT throw — callers decide what to do with violations.
 */
export async function auditA11y(page: Page, options?: A11yOptions): Promise<A11yResult> {
  const tags = options?.tags ?? ['wcag2a', 'wcag2aa'];

  let builder = new AxeBuilder({ page }).withTags(tags);

  for (const selector of options?.exclude ?? []) {
    builder = builder.exclude(selector);
  }

  const results = await builder.analyze();

  const toViolation = (v: (typeof results.violations)[number]): A11yViolation => ({
    id: v.id,
    impact: (v.impact ?? 'minor') as ImpactLevel,
    description: v.description,
    helpUrl: v.helpUrl,
    nodes: v.nodes.length,
  });

  const all = results.violations.map(toViolation);
  const violations = all.filter(
    (v) => v.impact === 'critical' || v.impact === 'serious',
  );

  return { violations, all };
}

/**
 * Assert that the page has no critical or serious WCAG violations.
 *
 * - Fails the test if any violations at `level` or above are found.
 * - Logs moderate+minor violations as annotations (warn-only).
 * - Attaches the full violation list as a JSON artifact.
 *
 * @param page      Playwright Page (must be navigated + rendered)
 * @param testInfo  Playwright TestInfo (for attach + annotations)
 * @param level     Minimum impact level to fail on (default: 'serious')
 * @param options   Exclude selectors, WCAG tag overrides
 */
export async function assertNoA11yViolations(
  page: Page,
  testInfo: TestInfo,
  level: ImpactLevel = 'serious',
  options?: A11yOptions,
): Promise<void> {
  const result = await auditA11y(page, options);

  const levelIndex = IMPACT_ORDER.indexOf(level);

  const blocking = result.all.filter(
    (v) => IMPACT_ORDER.indexOf(v.impact) >= levelIndex,
  );
  const warnings = result.all.filter(
    (v) => IMPACT_ORDER.indexOf(v.impact) < levelIndex,
  );

  // Attach full report as artifact (always, for tracking trends)
  await testInfo.attach('a11y-violations.json', {
    body: JSON.stringify(
      {
        url: page.url(),
        threshold: level,
        blocking,
        warnings,
      },
      null,
      2,
    ),
    contentType: 'application/json',
  });

  // Warn-only annotations for moderate/minor
  for (const v of warnings) {
    testInfo.annotations.push({
      type: 'a11y-warning',
      description: `[${v.impact}] ${v.id}: ${v.description} (${v.nodes} node(s)) — ${v.helpUrl}`,
    });
  }

  // Hard fail on critical+serious (or whatever level was requested)
  if (blocking.length > 0) {
    const lines = blocking.map(
      (v) => `  [${v.impact}] ${v.id}: ${v.description} (${v.nodes} node(s))\n    ${v.helpUrl}`,
    );
    throw new Error(
      `${blocking.length} WCAG violation(s) at level >=${level} on ${page.url()}:\n${lines.join('\n')}`,
    );
  }
}
