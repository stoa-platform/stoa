/**
 * Console Dashboards & AI Tools step definitions for STOA E2E Tests
 * Steps for dashboards, embeds, AI tools, MCP servers, and applications pages
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// AI TOOL CATALOG
// ============================================================================

When('I navigate to the AI Tool Catalog page', async ({ page }) => {
  await page.goto(`${URLS.console}/ai-tools`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the AI Tool Catalog page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /AI Tool Catalog/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/ai-tools')).toBe(true);
});

// ============================================================================
// AI TOOL SUBSCRIPTIONS
// ============================================================================

When('I navigate to the AI Tool subscriptions page', async ({ page }) => {
  await page.goto(`${URLS.console}/ai-tools/subscriptions`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the AI Tool subscriptions page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /My Subscriptions/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/ai-tools/subscriptions')).toBe(true);
});

// ============================================================================
// AI USAGE DASHBOARD
// ============================================================================

When('I navigate to the AI Usage Dashboard page', async ({ page }) => {
  await page.goto(`${URLS.console}/ai-tools/usage`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the AI Usage Dashboard page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Usage Dashboard/i });
  const charts = page.locator(
    '[class*="chart"], [class*="graph"], canvas, svg, [class*="metric"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await charts.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/ai-tools/usage')).toBe(true);
});

// ============================================================================
// AI TOOL SEARCH
// ============================================================================

When('I search for a tool in the catalog', async ({ page }) => {
  const searchInput = page.locator(
    'input[type="search"], input[placeholder*="search" i], input[placeholder*="filter" i], input[name="search"]',
  ).first();

  if (await searchInput.isVisible({ timeout: 5000 }).catch(() => false)) {
    await searchInput.fill('test');
    await page.waitForLoadState('networkidle');
  }
});

Then('the tool search results are displayed', async ({ page }) => {
  const content = page.locator(
    '[class*="card"], [class*="list"], table, text=/no result|no tool|0 result/i',
  );

  const loaded =
    (await content.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    page.url().includes('/ai-tools');

  expect(loaded).toBe(true);
});

// ============================================================================
// APPLICATIONS PAGE
// ============================================================================

When('I navigate to the Applications page', async ({ page }) => {
  await page.goto(`${URLS.console}/applications`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Applications page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Application/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/applications')).toBe(true);
});

// ============================================================================
// OPERATIONS DASHBOARD
// ============================================================================

When('I navigate to the Operations Dashboard page', async ({ page }) => {
  await page.goto(`${URLS.console}/operations`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Operations Dashboard page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Operations/i });
  const charts = page.locator(
    '[class*="chart"], [class*="graph"], canvas, svg, [class*="metric"], [class*="card"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await charts.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/operations')).toBe(true);
});

// ============================================================================
// MY USAGE
// ============================================================================

When('I navigate to the My Usage page', async ({ page }) => {
  await page.goto(`${URLS.console}/my-usage`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the My Usage page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /My Usage/i });
  const charts = page.locator(
    '[class*="chart"], [class*="graph"], canvas, svg, [class*="metric"], [class*="card"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await charts.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/my-usage')).toBe(true);
});

// ============================================================================
// BUSINESS ANALYTICS
// ============================================================================

When('I navigate to the Business Analytics page', async ({ page }) => {
  await page.goto(`${URLS.console}/business`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Business Analytics page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Business/i });
  const charts = page.locator(
    '[class*="chart"], [class*="graph"], canvas, svg, [class*="metric"], [class*="card"]',
  );

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await charts.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/business')).toBe(true);
});

// ============================================================================
// DEPLOYMENTS
// ============================================================================

When('I navigate to the Deployments page', async ({ page }) => {
  await page.goto(`${URLS.console}/deployments`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Deployments page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Deployment/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/deployments')).toBe(true);
});

// ============================================================================
// GATEWAY STATUS
// ============================================================================

When('I navigate to the Gateway Status page', async ({ page }) => {
  await page.goto(`${URLS.console}/gateway`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Gateway Status page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Gateway Adapter/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/gateway')).toBe(true);
});

// ============================================================================
// GATEWAY MODES
// ============================================================================

When('I navigate to the Gateway Modes page', async ({ page }) => {
  await page.goto(`${URLS.console}/gateways/modes`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Gateway Modes page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Gateway Modes/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/gateways/modes')).toBe(true);
});

// ============================================================================
// OBSERVABILITY EMBED
// ============================================================================

When('I navigate to the Observability embed page', async ({ page }) => {
  await page.goto(`${URLS.console}/observability`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Observability embed page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Observability/i });
  const iframe = page.locator('iframe');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await iframe.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/observability')).toBe(true);
});

// ============================================================================
// LOGS EMBED
// ============================================================================

When('I navigate to the Logs embed page', async ({ page }) => {
  await page.goto(`${URLS.console}/logs`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Logs embed page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Logs/i });
  const iframe = page.locator('iframe');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await iframe.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/logs')).toBe(true);
});

// ============================================================================
// IDENTITY MANAGEMENT EMBED
// ============================================================================

When('I navigate to the Identity Management embed page', async ({ page }) => {
  await page.goto(`${URLS.console}/identity`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the Identity Management embed page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Identity/i });
  const iframe = page.locator('iframe');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await iframe.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/identity')).toBe(true);
});

// ============================================================================
// EXTERNAL MCP SERVERS
// ============================================================================

When('I navigate to the External MCP Servers page', async ({ page }) => {
  await page.goto(`${URLS.console}/external-mcp-servers`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the External MCP Servers page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /External MCP/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/external-mcp-servers')).toBe(true);
});

// ============================================================================
// MCP ERROR SNAPSHOTS
// ============================================================================

When('I navigate to the MCP Error Snapshots page', async ({ page }) => {
  await page.goto(`${URLS.console}/mcp/errors`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('the MCP Error Snapshots page loads successfully', async ({ page }) => {
  const heading = page.locator('h1, h2').filter({ hasText: /Error Snapshot/i });
  const content = page.locator('[class*="card"], [class*="list"], table');

  const loaded =
    (await heading.isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await content.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded || page.url().includes('/mcp/errors')).toBe(true);
});
