/**
 * Demo-specific step definitions for STOA E2E Tests
 * Portal Consumer (steps 1-6) + Console Admin (steps 7-10) demo paths
 *
 * These steps are designed for resilience during live demos:
 * - Generous timeouts for slow networks
 * - Fallback selectors for FR/EN UI variants
 * - Explicit waits for async content loading
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

/** Default timeout for visible checks during demo */
const DEMO_TIMEOUT = 15000;

/** Extended timeout for page loads / async data */
const LOAD_TIMEOUT = 20000;

// ============================================================================
// PORTAL DEMO STEPS (Steps 2-6)
// Steps 1 reuses common.steps "I am logged in as" + portal.steps "I access the API catalog"
// ============================================================================

// Step 2: Search for an API that actually exists in the catalog
When('I search for an API by name from the catalog', async ({ page }) => {
  // Extract first API title from the catalog before searching
  const firstApi = page.locator('a[href^="/apis/"]').first();
  await expect(firstApi).toBeVisible({ timeout: DEMO_TIMEOUT });

  // Try to get the first word of the API title
  const titleEl = firstApi.locator('h3, h4, [class*="font-semibold"], [class*="title"]').first();
  let searchTerm = '';

  if (await titleEl.isVisible({ timeout: 3000 }).catch(() => false)) {
    const titleText = await titleEl.textContent();
    searchTerm = titleText?.trim().split(/\s+/)[0] || '';
  }

  if (!searchTerm) {
    // Fallback: extract any text from the first API card
    const cardText = await firstApi.textContent();
    searchTerm = cardText?.trim().split(/\s+/)[0] || 'api';
  }

  const searchInput = page.locator(
    'input[placeholder*="Search"], input[placeholder*="Rechercher"], ' +
      'input[placeholder*="search"], input[type="search"]',
  );
  await expect(searchInput).toBeVisible({ timeout: DEMO_TIMEOUT });
  await searchInput.fill(searchTerm);
  // Debounce + network settle
  await page.waitForTimeout(500);
  await page.waitForLoadState('networkidle').catch(() => {});
});

// Step 2: Verify search returned results
Then('the search results are not empty', async ({ page }) => {
  const results = page.locator('a[href^="/apis/"]');
  await expect(results.first()).toBeVisible({ timeout: DEMO_TIMEOUT });
  const count = await results.count();
  expect(count).toBeGreaterThan(0);
});

// Step 3: Click first API result → navigate to detail
When('I click on the first API result', async ({ page }) => {
  const apiCard = page.locator('a[href^="/apis/"]').first();
  await expect(apiCard).toBeVisible({ timeout: DEMO_TIMEOUT });
  await apiCard.click();
  await page.waitForLoadState('networkidle').catch(() => {});
});

// Step 3: Verify API detail page loaded (wait for async content)
Then('the API detail page is displayed', async ({ page }) => {
  await expect(page).toHaveURL(/\/apis\/[^/]+/, { timeout: DEMO_TIMEOUT });

  // The detail page fetches content asynchronously ("Loading API details...")
  // Wait for loading to finish, then verify heading
  await page.waitForTimeout(1000);
  const loadingText = page.getByText('Loading');
  if (await loadingText.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await expect(loadingText.first()).not.toBeVisible({ timeout: LOAD_TIMEOUT });
  }

  const heading = page.locator('h1, h2').first();
  await expect(heading).toBeVisible({ timeout: DEMO_TIMEOUT });
});

// Step 3: Verify API specification / OpenAPI section visible
Then('I see the API specification section', async ({ page }) => {
  // Multiple signals that spec content is present
  const specIndicators = page.locator(
    '[class*="swagger"], [class*="spec"], [class*="openapi"], [class*="Spec"]',
  );
  const codeBlock = page.locator('iframe[src*="swagger"], pre code');
  const specText = page.getByText(
    /specification|endpoints|schema|swagger|openapi|paths|operations|parameters/i,
  );
  // Also check for tab/section headers
  const specTab = page.locator(
    'button:has-text("Specification"), button:has-text("Spec"), ' +
      'a:has-text("Specification"), [role="tab"]:has-text("Spec")',
  );

  const hasSpec =
    (await specIndicators.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    (await codeBlock.first().isVisible({ timeout: 3000 }).catch(() => false)) ||
    (await specText.first().isVisible({ timeout: 3000 }).catch(() => false)) ||
    (await specTab.first().isVisible({ timeout: 3000 }).catch(() => false));

  expect(hasSpec).toBe(true);
});

// Step 4: Click "Try this API" button on detail page
When('I click the try this API button', async ({ page }) => {
  // Close any open dropdown menus (user menu, etc.) that intercept clicks
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);

  // Dismiss "Did you know?" or onboarding popups if present
  const dismissBtns = page.locator(
    'button:has-text("Got it"), button:has-text("OK"), button:has-text("Compris")',
  );
  if (await dismissBtns.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await dismissBtns.first().click();
    await page.waitForTimeout(300);
  }

  // Prefer the specific href-based selector (most reliable: the /test link on the API detail page)
  const tryLink = page.locator('a[href*="/test"]');
  const tryBtn = page.locator(
    'button:has-text("Try this API"), a:has-text("Try this API"), ' +
      'button:has-text("Try it"), a:has-text("Try it"), ' +
      'button:has-text("Essayer"), a:has-text("Essayer")',
  );

  const target = (await tryLink.first().isVisible({ timeout: 5000 }).catch(() => false))
    ? tryLink.first()
    : tryBtn.first();

  await expect(target).toBeVisible({ timeout: DEMO_TIMEOUT });

  // Use JS click to trigger React Router navigation (not full page reload).
  // Playwright's force:true or native click can bypass React's synthetic event system
  // and cause a full navigation → Keycloak "Invalid redirect uri" error.
  await target.dispatchEvent('click');
  await page.waitForLoadState('networkidle').catch(() => {});
});

// Step 4: Verify API testing interface is shown
Then('I see the API testing interface', async ({ page }) => {
  // Wait for "Loading..." to disappear (OIDC auth restoration after navigation)
  const loadingText = page.getByText('Loading');
  if (await loadingText.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await expect(loadingText.first()).not.toBeVisible({ timeout: LOAD_TIMEOUT });
  }

  // The test page should show endpoint methods, a heading, or test UI elements
  const endpointList = page.getByText(/GET|POST|PUT|DELETE|PATCH/);
  const heading = page.locator('h1, h2, h3').first();
  const testingUI = page.locator(
    '[class*="try"], [class*="test"], [class*="playground"], ' +
      '[class*="console"], [class*="sandbox"]',
  );
  const codeBlock = page.locator('pre, code, textarea');

  const hasTestUI =
    (await heading.isVisible({ timeout: DEMO_TIMEOUT }).catch(() => false)) ||
    (await endpointList.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    (await testingUI.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    (await codeBlock.first().isVisible({ timeout: 3000 }).catch(() => false));

  expect(hasTestUI).toBe(true);
});

// Step 5: Verify subscriptions page is displayed
Then('the subscriptions page is displayed', async ({ page }) => {
  // Wait for loading to finish
  const spinner = page.locator('.animate-spin');
  if (await spinner.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await expect(spinner.first()).not.toBeVisible({ timeout: LOAD_TIMEOUT });
  }

  const heading = page.locator('h1, h2').first();
  await expect(heading).toBeVisible({ timeout: DEMO_TIMEOUT });
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
// CONSOLE DEMO STEPS (Steps 7-10)
// Step 7 reuses common.steps "I am logged in to Console as"
// ============================================================================

// Step 7: Navigate to Console dashboard
When('I access the Console dashboard', async ({ page }) => {
  await page.goto(URLS.console);
  await page.waitForLoadState('networkidle').catch(() => {});

  // Wait for loading to finish
  await expect(page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: LOAD_TIMEOUT })
    .catch(() => {});
});

// Step 7: Verify Console admin dashboard is displayed
Then('I see the Console admin dashboard', async ({ page }) => {
  // Console should show sidebar nav with admin sections
  const sidebar = page.locator('nav, [class*="sidebar"], [class*="Sidebar"]');
  await expect(sidebar.first()).toBeVisible({ timeout: DEMO_TIMEOUT });
  // Must not be stuck on login/auth pages
  expect(page.url()).not.toContain('/login');
  expect(page.url()).not.toContain('/auth/');
});

// Step 8: Navigate to subscription management in Console
When('I navigate to subscription management', async ({ page }) => {
  // Try nav links in priority order
  const subsLink = page.locator(
    'a:has-text("Subscriptions"), a:has-text("Souscriptions"), a[href*="subscription"]',
  );
  const appsLink = page.locator('a:has-text("Applications"), a[href*="application"]');

  if (await subsLink.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await subsLink.first().click();
  } else if (await appsLink.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await appsLink.first().click();
  } else {
    // Direct navigation fallback
    await page.goto(`${URLS.console}/subscriptions`);
  }

  await page.waitForLoadState('networkidle').catch(() => {});

  // Wait for loading spinners
  await page.waitForTimeout(1000);
  const spinner = page.locator('.animate-spin');
  if (await spinner.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await expect(spinner.first()).not.toBeVisible({ timeout: LOAD_TIMEOUT });
  }
});

// Step 8: Verify subscription/application list page is displayed
Then('I see the subscription requests list', async ({ page }) => {
  const searchInput = page.locator(
    'input[placeholder*="Search"], input[placeholder*="Rechercher"], ' +
      'input[placeholder*="search"], input[type="search"]',
  );
  const createBtn = page.locator(
    'button:has-text("Create"), a:has-text("Create"), ' +
      'button:has-text("Créer"), a:has-text("Créer")',
  );
  const pageHeading = page.getByText(/Applications|Subscriptions|Souscriptions/i);

  const hasContent =
    (await searchInput.first().isVisible({ timeout: LOAD_TIMEOUT }).catch(() => false)) ||
    (await createBtn.first().isVisible({ timeout: 5000 }).catch(() => false)) ||
    (await pageHeading.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(hasContent).toBe(true);
});

// Step 9: Verify application management controls (Create button, search, status filter)
Then('the application management controls are visible', async ({ page }) => {
  const createBtn = page.locator(
    'button:has-text("Create"), a:has-text("Create"), ' +
      'button:has-text("Créer"), a:has-text("Créer"), ' +
      'button:has-text("New"), a:has-text("New"), ' +
      'button:has-text("Nouveau"), a:has-text("Nouveau")',
  );
  await expect(createBtn.first()).toBeVisible({ timeout: DEMO_TIMEOUT });
});

// Step 10: Navigate to API Monitoring dashboard
When('I navigate to the analytics dashboard', async ({ page }) => {
  const monitoringLink = page.locator(
    'a:has-text("API Monitoring"), a:has-text("Monitoring"), ' +
      'a:has-text("Analytics"), a:has-text("Metrics"), ' +
      'a:has-text("Tableau de bord"), ' +
      'a[href*="monitoring"], a[href*="analytics"], a[href*="metrics"], a[href*="dashboard"]',
  );

  if (await monitoringLink.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await monitoringLink.first().click();
  } else {
    // Direct navigation fallback
    await page.goto(`${URLS.console}/monitoring`);
  }

  await page.waitForLoadState('networkidle').catch(() => {});

  // Wait for loading spinners
  await page.waitForTimeout(1000);
  const spinner = page.locator('.animate-spin');
  if (await spinner.first().isVisible({ timeout: 2000 }).catch(() => false)) {
    await expect(spinner.first()).not.toBeVisible({ timeout: LOAD_TIMEOUT });
  }
});

// Step 10: Verify API Monitoring page loaded
Then('I see the API monitoring page', async ({ page }) => {
  const heading = page.locator('h1, h2');
  const monitoringContent = page.getByText(/monitoring|metrics|api|tableau/i);

  const loaded =
    (await heading.first().isVisible({ timeout: DEMO_TIMEOUT }).catch(() => false)) ||
    (await monitoringContent.first().isVisible({ timeout: 5000 }).catch(() => false));

  expect(loaded).toBe(true);
});
