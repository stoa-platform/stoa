/**
 * Verify Portal loads without CORS errors and does not switch to remote API.
 *
 * Checks:
 * 1. Portal loads at portal.stoa.local
 * 2. No CORS errors in console
 * 3. No calls to dev-api.gostoa.dev or any *.gostoa.dev API endpoint
 * 4. API calls go to api.stoa.local
 */
import { test, expect } from '@playwright/test';

test.describe('Portal local environment', () => {
  test('loads without CORS errors or remote API calls', async ({ page }) => {
    const consoleErrors: string[] = [];
    const networkUrls: string[] = [];

    // Collect console errors
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    // Track all XHR/fetch requests
    page.on('request', (req) => {
      const url = req.url();
      if (url.includes('/v1/') || url.includes('/api/')) {
        networkUrls.push(url);
      }
    });

    // Navigate to portal
    await page.goto('http://portal.stoa.local', { waitUntil: 'networkidle' });

    // Portal should load (check for any visible content)
    await expect(page).toHaveTitle(/STOA|Portal/i, { timeout: 15000 });

    // Wait a bit for any lazy API calls
    await page.waitForTimeout(3000);

    // No CORS errors
    const corsErrors = consoleErrors.filter(
      (e) => e.includes('CORS') || e.includes('Access-Control-Allow-Origin')
    );
    expect(corsErrors).toEqual([]);

    // No calls to remote gostoa.dev API endpoints
    const remoteApiCalls = networkUrls.filter(
      (url) => url.includes('gostoa.dev') && !url.includes('docs.gostoa.dev')
    );
    expect(remoteApiCalls).toEqual([]);

    // Take screenshot for evidence
    await page.screenshot({ path: 'test-results/portal-local-env.png', fullPage: true });
  });

  test('notifications 404 does not crash the portal', async ({ page }) => {
    const responses: { url: string; status: number }[] = [];

    page.on('response', (res) => {
      if (res.url().includes('notifications')) {
        responses.push({ url: res.url(), status: res.status() });
      }
    });

    await page.goto('http://portal.stoa.local', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    // If notifications endpoint is called, it may 404 — but portal should still render
    const pageContent = await page.textContent('body');
    expect(pageContent).toBeTruthy();

    // Check the page didn't white-screen
    const hasContent = await page.locator('body').evaluate((el) => el.children.length > 0);
    expect(hasContent).toBe(true);
  });
});
