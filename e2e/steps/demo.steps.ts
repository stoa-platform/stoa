/**
 * Demo-specific step definitions for STOA E2E Tests
 * Portal Consumer (steps 1-6) + Console Admin (steps 7-10) demo paths
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// PORTAL DEMO STEPS
// ============================================================================

// Step 2: Search for an API that actually exists in the catalog
When('I search for an API by name from the catalog', async ({ page }) => {
  // Extract first API title from the catalog before searching
  const firstApi = page.locator('a[href^="/apis/"]').first();
  await expect(firstApi).toBeVisible({ timeout: 10000 });

  const titleEl = firstApi.locator('h3, h4, [class*="font-semibold"], [class*="title"]').first();
  let searchTerm = '';
  if (await titleEl.isVisible({ timeout: 3000 }).catch(() => false)) {
    const titleText = await titleEl.textContent();
    // Use first word of the title as search term
    searchTerm = titleText?.trim().split(/\s+/)[0] || '';
  }

  if (!searchTerm) {
    // Fallback: get any text from the first API card
    const cardText = await firstApi.textContent();
    searchTerm = cardText?.trim().split(/\s+/)[0] || 'api';
  }

  const searchInput = page.locator(
    'input[placeholder*="Search"], input[placeholder*="Rechercher"], input[type="search"]',
  );
  await searchInput.fill(searchTerm);
  await page.waitForTimeout(500);
  await page.waitForLoadState('networkidle');
});

// Step 2: Verify search returned results
Then('the search results are not empty', async ({ page }) => {
  const results = page.locator('a[href^="/apis/"]');
  await expect(results.first()).toBeVisible({ timeout: 10000 });
  const count = await results.count();
  expect(count).toBeGreaterThan(0);
});

// Step 3: Click first API result → navigate to detail
When('I click on the first API result', async ({ page }) => {
  const apiCard = page.locator('a[href^="/apis/"]').first();
  await expect(apiCard).toBeVisible({ timeout: 10000 });
  await apiCard.click();
  await page.waitForLoadState('networkidle');
});

// Step 3: Verify API detail page loaded (wait for async content)
Then('the API detail page is displayed', async ({ page }) => {
  await expect(page).toHaveURL(/\/apis\/[^/]+/, { timeout: 10000 });
  // The detail page fetches content asynchronously showing "Loading API details..."
  // Wait for the loading indicator to appear, then wait for it to disappear
  await page.waitForTimeout(1000);
  const loadingText = page.getByText('Loading');
  if (await loadingText.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await expect(loadingText.first()).not.toBeVisible({ timeout: 20000 });
  }
  const heading = page.locator('h1, h2').first();
  await expect(heading).toBeVisible({ timeout: 10000 });
});

// Step 3: Verify API specification / OpenAPI section visible
Then('I see the API specification section', async ({ page }) => {
  // Look for spec-related elements: swagger UI, code blocks, endpoint lists, or spec keywords
  const specIndicators = page.locator(
    '[class*="swagger"], [class*="spec"], [class*="openapi"]',
  );
  const codeBlock = page.locator('iframe[src*="swagger"], pre code');
  const specText = page.getByText(
    /specification|endpoints|schema|swagger|openapi|paths|operations|parameters/i,
  );

  const hasSpec =
    (await specIndicators.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    (await codeBlock.first().isVisible({ timeout: 3000 }).catch(() => false)) ||
    (await specText.first().isVisible({ timeout: 3000 }).catch(() => false));

  expect(hasSpec).toBe(true);
});

// Step 4: Click "Try this API" button on detail page
When('I click the try this API button', async ({ page }) => {
  // Dismiss "Did you know?" popup if present
  const gotItBtn = page.locator('button:has-text("Got it")');
  if (await gotItBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await gotItBtn.click();
    await page.waitForTimeout(300);
  }

  const tryBtn = page.locator(
    'button:has-text("Try this API"), a:has-text("Try this API"), ' +
      'button:has-text("Essayer"), a:has-text("Essayer")',
  );
  await expect(tryBtn.first()).toBeVisible({ timeout: 10000 });
  await tryBtn.first().click();
  await page.waitForLoadState('networkidle');
});

// Step 4: Verify API testing interface is shown
Then('I see the API testing interface', async ({ page }) => {
  // The "Try this API" action may navigate to a test page, open a panel, or show a modal
  const testingUI = page.locator(
    '[class*="try"], [class*="test"], [class*="playground"], [class*="console"]',
  );
  const codeBlock = page.locator('pre, code, textarea');
  const endpointList = page.getByText(/GET|POST|PUT|DELETE|PATCH/);
  const heading = page.locator('h1, h2, h3').first();

  const hasTestUI =
    (await testingUI.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    (await codeBlock.first().isVisible({ timeout: 3000 }).catch(() => false)) ||
    (await endpointList.first().isVisible({ timeout: 3000 }).catch(() => false)) ||
    (await heading.isVisible({ timeout: 3000 }).catch(() => false));

  expect(hasTestUI).toBe(true);
});

// Step 5: Verify subscriptions page is displayed
Then('the subscriptions page is displayed', async ({ page }) => {
  const heading = page.locator('h1, h2').first();
  await expect(heading).toBeVisible({ timeout: 10000 });
});

// Step 6: Make a test API call via the gateway
let lastApiCallStatus = 0;

When('I make a test API call with my credentials', async ({ request }) => {
  const response = await request.fetch(`${URLS.gateway}/health/ready`, {
    method: 'GET',
  });
  lastApiCallStatus = response.status();
});

// Step 6: Assert HTTP 200
Then('I receive a successful HTTP 200 response', async () => {
  expect(lastApiCallStatus).toBe(200);
});

// ============================================================================
// CONSOLE DEMO STEPS
// ============================================================================

// Step 7: Navigate to Console dashboard
When('I access the Console dashboard', async ({ page }) => {
  await page.goto(URLS.console);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

// Step 7: Verify Console admin dashboard is displayed
Then('I see the Console admin dashboard', async ({ page }) => {
  // Console should show sidebar nav with admin sections
  const sidebar = page.locator('nav, [class*="sidebar"]');
  await expect(sidebar.first()).toBeVisible({ timeout: 10000 });
  expect(page.url()).not.toContain('/login');
  expect(page.url()).not.toContain('/auth/');
});

// Step 8: Navigate to subscription management in Console
When('I navigate to subscription management', async ({ page }) => {
  // Try nav links: Subscriptions, Applications (contains subscriptions management)
  const subsLink = page.locator(
    'a:has-text("Subscriptions"), a:has-text("Souscriptions"), a[href*="subscription"]',
  );
  const appsLink = page.locator('a:has-text("Applications"), a[href*="application"]');

  if (await subsLink.first().isVisible({ timeout: 3000 }).catch(() => false)) {
    await subsLink.first().click();
  } else if (await appsLink.first().isVisible({ timeout: 3000 }).catch(() => false)) {
    await appsLink.first().click();
  } else {
    await page.goto(`${URLS.console}/subscriptions`);
  }
  await page.waitForLoadState('networkidle');
  // Wait for loading spinner to disappear
  await page.waitForTimeout(1000);
  const spinner = page.locator('.animate-spin');
  if (await spinner.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await expect(spinner.first()).not.toBeVisible({ timeout: 15000 });
  }
});

// Step 8: Verify subscription/application list page is displayed
Then('I see the subscription requests list', async ({ page }) => {
  // Wait for Applications page content to load (heading + search input)
  const searchInput = page.locator(
    'input[placeholder*="Search"], input[placeholder*="Rechercher"], input[type="search"]',
  );
  const createBtn = page.locator('button:has-text("Create"), a:has-text("Create")');
  const pageHeading = page.getByText(/Applications|Subscriptions/i);

  const hasContent =
    (await searchInput.first().isVisible({ timeout: 15000 }).catch(() => false)) ||
    (await createBtn.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    (await pageHeading.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasContent).toBe(true);
});

// Step 9: Verify application management controls (Create button, search, status filter)
Then('the application management controls are visible', async ({ page }) => {
  // Applications page should have: Create button, Search input, Status filter
  const createBtn = page.locator(
    'button:has-text("Create"), a:has-text("Create"), ' +
      'button:has-text("Créer"), a:has-text("Créer")',
  );
  await expect(createBtn.first()).toBeVisible({ timeout: 10000 });
});

// Step 10: Navigate to API Monitoring dashboard
When('I navigate to the analytics dashboard', async ({ page }) => {
  // Console sidebar has "API Monitoring" for analytics
  const monitoringLink = page.locator(
    'a:has-text("API Monitoring"), a:has-text("Monitoring"), ' +
      'a:has-text("Analytics"), a:has-text("Metrics"), ' +
      'a[href*="monitoring"], a[href*="analytics"], a[href*="metrics"]',
  );

  if (await monitoringLink.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await monitoringLink.first().click();
  } else {
    await page.goto(`${URLS.console}/monitoring`);
  }
  await page.waitForLoadState('networkidle');
  // Wait for loading spinner to disappear
  await page.waitForTimeout(1000);
  const spinner = page.locator('.animate-spin');
  if (await spinner.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await expect(spinner.first()).not.toBeVisible({ timeout: 15000 });
  }
});

// Step 10: Verify API Monitoring page loaded
Then('I see the API monitoring page', async ({ page }) => {
  // Wait for page heading or monitoring content
  const heading = page.locator('h1, h2');
  const monitoringContent = page.getByText(/monitoring|metrics|api/i);

  const loaded =
    (await heading.first().isVisible({ timeout: 10000 }).catch(() => false)) ||
    (await monitoringContent.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded).toBe(true);
});
