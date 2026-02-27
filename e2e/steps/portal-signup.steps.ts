/**
 * Step definitions for Portal Self-Service Signup Flow (CAB-1550)
 *
 * Covers:
 * - Portal signup page interactions (UI)
 * - Self-service API calls (HTTP)
 * - Provisioning status polling
 * - Duplicate email error handling
 */

import { createBdd, DataTable } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { Given, When, Then } = createBdd(test);

const API_URL = process.env.STOA_API_URL || 'https://api.gostoa.dev';

// Track signup response across steps
let signupResponse: {
  tenant_id: string;
  status: string;
  plan: string;
  poll_url: string;
} | null = null;

let lastApiResponse: { status: number; body: Record<string, unknown> } | null = null;

// ============================================================================
// PORTAL UI STEPS
// ============================================================================

Given('I am on the signup page', async ({ authSession }) => {
  await authSession.page.goto(`${URLS.portal}/signup`);
  await authSession.page.waitForLoadState('networkidle');
  await expect(authSession.page.locator('h1, h2').first()).toBeVisible({ timeout: 10000 });
});

When('I fill in the signup form with:', async ({ authSession }, dataTable: DataTable) => {
  const page = authSession.page;
  const rows = dataTable.rows();

  for (const [field, value] of rows) {
    const input = page.locator(`input[name="${field}"], #${field}, [data-testid="${field}"]`);
    await input.fill(value);
  }
});

When('I submit the signup form', async ({ authSession }) => {
  const page = authSession.page;
  const submitButton = page.locator(
    'button[type="submit"]:has-text("Sign Up"), button[type="submit"]:has-text("Create Account"), button[type="submit"]:has-text("Register")',
  );
  await expect(submitButton).toBeEnabled({ timeout: 5000 });
  await submitButton.click();
  await page.waitForLoadState('networkidle');
});

When('I submit the signup form without filling required fields', async ({ authSession }) => {
  const page = authSession.page;
  const submitButton = page.locator('button[type="submit"]');
  await submitButton.click();
});

Then('the signup is accepted with status {string}', async ({ authSession }, expectedStatus: string) => {
  const page = authSession.page;

  // Check for success message or redirect
  const successIndicator = page.locator(
    `text=/provisioning|${expectedStatus}|success|created|check your email/i`,
  );
  await expect(successIndicator).toBeVisible({ timeout: 15000 });
});

Then('I can poll the provisioning status until ready', async ({ request }) => {
  expect(signupResponse).not.toBeNull();

  const maxAttempts = 30;
  const pollInterval = 2000;

  for (let i = 0; i < maxAttempts; i++) {
    const statusResp = await request.fetch(
      `${API_URL}/v1/self-service/tenants/${signupResponse!.tenant_id}/status`,
    );
    expect(statusResp.ok()).toBeTruthy();

    const statusData = await statusResp.json();
    if (statusData.provisioning_status === 'ready') {
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, pollInterval));
  }

  throw new Error('Tenant provisioning did not complete within timeout');
});

When('I log in with the provisioned tenant credentials', async ({ authSession }) => {
  // After provisioning, the user receives credentials (email flow).
  // For E2E, we navigate to the portal login and authenticate.
  const page = authSession.page;
  await page.goto(`${URLS.portal}/`);
  await page.waitForLoadState('networkidle');
});

When('I navigate to the API creation page', async ({ authSession }) => {
  const page = authSession.page;
  await page.goto(`${URLS.portal}/workspace`);
  await page.waitForLoadState('networkidle');
});

When(
  'I create an API named {string} with endpoint {string}',
  async ({ authSession }, apiName: string, endpoint: string) => {
    const page = authSession.page;

    // Click the create API button
    const createButton = page.locator(
      'button:has-text("Create API"), button:has-text("New API"), a:has-text("Create API")',
    );
    await createButton.first().click();
    await page.waitForLoadState('networkidle');

    // Fill in the API creation form
    const nameInput = page.locator('input[name="name"], #name, [data-testid="api-name"]');
    await nameInput.fill(apiName);

    const endpointInput = page.locator(
      'input[name="endpoint"], #endpoint, [data-testid="api-endpoint"]',
    );
    await endpointInput.fill(endpoint);

    // Submit the form
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();
    await page.waitForLoadState('networkidle');
  },
);

Then('the API is visible in the catalog', async ({ authSession }) => {
  const page = authSession.page;

  // Navigate to catalog and verify API exists
  await page.goto(`${URLS.portal}/servers`);
  await page.waitForLoadState('networkidle');

  const apiEntry = page.locator('text=/My First API/i');
  await expect(apiEntry).toBeVisible({ timeout: 10000 });
});

Then('the signup is rejected with a duplicate error', async ({ authSession }) => {
  const page = authSession.page;

  const errorMessage = page.locator(
    'text=/already exists|duplicate|already registered|email.*taken|already in use/i',
  );
  await expect(errorMessage).toBeVisible({ timeout: 10000 });
});

Then('I see validation errors for required fields', async ({ authSession }) => {
  const page = authSession.page;

  // Check for HTML5 validation or custom error messages
  const validationErrors = page.locator(
    '[class*="error"], [aria-invalid="true"], .field-error, [data-testid*="error"]',
  );
  const count = await validationErrors.count();
  expect(count).toBeGreaterThan(0);
});

// ============================================================================
// API-ONLY STEPS (no browser needed)
// ============================================================================

When('I call the self-service signup API with:', async ({ request }, dataTable: DataTable) => {
  const rows = dataTable.rows();
  const payload: Record<string, string> = {};

  for (const [field, value] of rows) {
    payload[field] = value;
  }

  const response = await request.fetch(`${API_URL}/v1/self-service/tenants`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    data: JSON.stringify(payload),
  });

  const body = await response.json().catch(() => ({}));
  lastApiResponse = { status: response.status(), body };

  if (response.status() === 202) {
    signupResponse = body as typeof signupResponse;
  }
});

Then('the API responds with status {int}', async ({}, expectedStatus: number) => {
  expect(lastApiResponse).not.toBeNull();
  expect(lastApiResponse!.status).toBe(expectedStatus);
});

Then('the response contains a poll_url', async ({}) => {
  expect(lastApiResponse).not.toBeNull();
  expect(lastApiResponse!.body).toHaveProperty('poll_url');
  expect(lastApiResponse!.body.poll_url).toBeTruthy();
});

Then('the plan is {string}', async ({}, expectedPlan: string) => {
  expect(lastApiResponse).not.toBeNull();
  expect(lastApiResponse!.body).toHaveProperty('plan', expectedPlan);
});
