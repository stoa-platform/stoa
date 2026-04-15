/**
 * Console Dashboard — axe-core WCAG 2.1 AA gate (CAB-1989 P4)
 *
 * Runs against the mocked Console (smoke-mock webServer) so no live backend
 * is required. Add new pages to CONSOLE_PAGES as the app grows.
 *
 * To run locally (requires built Console):
 *   cd e2e && npx playwright test --project=a11y
 */

import { test, expect } from '@playwright/test';
import { setupMockRoutes, injectMockAuth } from '../../smoke-mock/mock-routes';
import { assertNoA11yViolations } from '../../fixtures/a11y';

/** Pages covered by this gate. */
const CONSOLE_PAGES = [
  { name: 'Operations Dashboard', path: '/operations' },
  { name: 'Gateway Status', path: '/gateway' },
  { name: 'Deployments', path: '/deployments' },
  { name: 'Applications', path: '/applications' },
  { name: 'Observability', path: '/observability' },
];

test.beforeEach(async ({ page }) => {
  await setupMockRoutes(page);
  await injectMockAuth(page);
});

for (const { name, path } of CONSOLE_PAGES) {
  test(`a11y: ${name}`, async ({ page }, testInfo) => {
    await page.goto(path);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).not.toContainText('Application error');

    // Fails on critical+serious; moderate+minor logged as annotations.
    await assertNoA11yViolations(page, testInfo, 'serious', {
      // Exclude the Keycloak iframe if present — third-party, not our responsibility.
      exclude: ['#kc-iframe', '[data-keycloak-iframe]'],
    });
  });
}
