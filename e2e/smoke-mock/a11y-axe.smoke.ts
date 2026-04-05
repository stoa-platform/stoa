import { test, expect } from '@playwright/test';
import { setupMockRoutes, injectMockAuth } from './mock-routes';
import { scanPage } from '../fixtures/axe-helper';

/**
 * axe-core WCAG 2.1 AA smoke tests — Console pages (CAB-1995)
 *
 * Reuses the mocked backend from console-pages.smoke.ts.
 * Scans each page for accessibility violations at the configured threshold.
 * Violations are always attached as JSON for tracking, even on pass.
 */

const CONSOLE_PAGES = [
  { name: 'Operations Dashboard', path: '/operations' },
  { name: 'My Usage', path: '/my-usage' },
  { name: 'Business Analytics', path: '/business' },
  { name: 'Deployments', path: '/deployments' },
  { name: 'Gateway Status', path: '/gateway' },
  { name: 'AI Tool Catalog', path: '/ai-tools' },
  { name: 'Applications', path: '/applications' },
  { name: 'External MCP Servers', path: '/external-mcp-servers' },
  { name: 'MCP Error Snapshots', path: '/mcp/errors' },
  { name: 'Observability', path: '/observability' },
];

test.beforeEach(async ({ page }) => {
  await setupMockRoutes(page);
  await injectMockAuth(page);
});

for (const { name, path } of CONSOLE_PAGES) {
  test(`a11y: ${name} has no critical WCAG violations`, async ({ page }, testInfo) => {
    await page.goto(path);

    // Wait for the app to render (Keycloak init + route resolution)
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).not.toContainText('Application error');

    const result = await scanPage(page);

    // Always attach violation details for tracking
    await testInfo.attach('a11y-violations.json', {
      body: JSON.stringify(
        {
          page: name,
          path,
          threshold: process.env.A11Y_IMPACT_THRESHOLD ?? 'critical',
          violations: result.violations,
          totalAllSeverities: result.totalAll,
        },
        null,
        2,
      ),
      contentType: 'application/json',
    });

    expect(result.violations, result.summary).toHaveLength(0);
  });
}
