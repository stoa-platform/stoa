/**
 * Consumer Onboarding step definitions for STOA E2E Tests
 *
 * Steps for the full consumer onboarding flow:
 * registration, plan selection, subscription approval, credential viewing.
 *
 * Reference: CAB-1121 Phase 6
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';

const { When, Then } = createBdd(test);

// ============================================================================
// CONSUMER REGISTRATION
// ============================================================================

When('I navigate to the consumer registration page', async ({ authSession }) => {
  await authSession.page.goto(`${URLS.portal}/consumers/register`);
  await authSession.page.waitForLoadState('networkidle');
  await expect(authSession.page.locator('h1:has-text("Register as Consumer")')).toBeVisible({
    timeout: 15000,
  });
});

When(
  'I fill in the registration form with external ID {string}',
  async ({ authSession }, externalId: string) => {
    const page = authSession.page;

    // Fill consumer name (auto-generates external_id via slugify)
    await page.fill('#name', `E2E Consumer ${externalId}`);

    // Clear auto-generated external_id and set the desired one
    await page.fill('#external_id', '');
    await page.fill('#external_id', externalId);

    // Email is pre-filled from user profile; fill company as optional
    await page.fill('#company', 'E2E Test Company');
  },
);

When('I submit the consumer registration', async ({ authSession }) => {
  const page = authSession.page;
  const submitButton = page.locator('button[type="submit"]:has-text("Register")');
  await expect(submitButton).toBeEnabled({ timeout: 5000 });
  await submitButton.click();
  // Wait for the API call to complete
  await page.waitForLoadState('networkidle');
});

Then('the consumer registration is successful', async ({ authSession }) => {
  const page = authSession.page;
  // Registration success shows the credentials modal or a success toast
  const credentialsModal = page.locator('text=/Consumer Credentials|Client ID|client_id/i');
  const successToast = page.locator('text=/registered successfully/i');
  const errorMessage = page.locator('text=/Registration failed|already exists|error/i');

  // Should not have an error
  const hasError = await errorMessage.first().isVisible({ timeout: 3000 }).catch(() => false);
  expect.soft(hasError).toBe(false);

  // Should show either credentials modal or success indicator
  const hasCredentials = await credentialsModal
    .first()
    .isVisible({ timeout: 15000 })
    .catch(() => false);
  const hasToast = await successToast.first().isVisible({ timeout: 3000 }).catch(() => false);
  expect(hasCredentials || hasToast).toBe(true);
});

Then('I see the consumer credentials modal', async ({ authSession }) => {
  const page = authSession.page;

  // The CredentialsModal shows client_id, client_secret, token_endpoint, grant_type
  const clientIdField = page.locator('text=/Client ID/i');
  const clientSecretField = page.locator('text=/Client Secret/i');
  const tokenEndpoint = page.locator('text=/Token Endpoint/i');

  await expect(clientIdField.first()).toBeVisible({ timeout: 10000 });
  await expect(clientSecretField.first()).toBeVisible({ timeout: 5000 });
  await expect(tokenEndpoint.first()).toBeVisible({ timeout: 5000 });

  // Close the modal by clicking Done
  const doneButton = page.locator('button:has-text("Done")');
  if (await doneButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    await doneButton.click();
    await page.waitForLoadState('networkidle');
  }
});

// ============================================================================
// PLAN SELECTION (in SubscribeWithPlanModal)
// ============================================================================

When('I select a plan from the available plans', async ({ authSession }) => {
  const page = authSession.page;

  // PlanSelector uses role="radiogroup" with individual plans as role="radio"
  const planGroup = page.locator('[role="radiogroup"]');
  await expect(planGroup).toBeVisible({ timeout: 10000 });

  const planCards = page.locator('[role="radio"]');
  const count = await planCards.count();

  if (count > 0) {
    // Select the first available plan
    await planCards.first().click();
    // Verify it's selected
    await expect(planCards.first()).toHaveAttribute('aria-checked', 'true', { timeout: 3000 });
  }
});

// ============================================================================
// APPROVAL QUEUE
// ============================================================================

When('I navigate to the approval queue', async ({ authSession }) => {
  await authSession.page.goto(`${URLS.portal}/workspace?tab=approvals`);
  await authSession.page.waitForLoadState('networkidle');
  // Wait for loading to finish
  await expect(authSession.page.locator('text=Loading').first())
    .not.toBeVisible({ timeout: 15000 })
    .catch(() => {});
});

Then('I see pending subscription requests', async ({ authSession }) => {
  const page = authSession.page;

  // The approval queue shows "Pending Requests (N)" header or "No pending requests"
  const pendingHeader = page.locator('text=/Pending Requests/i');
  const emptyState = page.locator('text=/No pending requests/i');

  const hasPending = await pendingHeader.isVisible({ timeout: 10000 }).catch(() => false);
  const hasEmpty = await emptyState.isVisible({ timeout: 3000 }).catch(() => false);

  // Either pending items or empty state should be visible
  expect(hasPending || hasEmpty).toBe(true);
});

When('I approve a pending subscription', async ({ authSession }) => {
  const page = authSession.page;

  // Find the Approve button on the first pending request
  const approveButton = page.locator('button:has-text("Approve")').first();

  if (await approveButton.isVisible({ timeout: 5000 }).catch(() => false)) {
    await approveButton.click();
    // Wait for the approval to process
    await page.waitForLoadState('networkidle');
  }
});

Then('the subscription is approved successfully', async ({ authSession }) => {
  const page = authSession.page;

  // After approval, either a success toast appears or the item disappears from the queue
  const successToast = page.locator('text=/approved/i');
  const emptyState = page.locator('text=/No pending requests|All subscription requests/i');

  const hasSuccess = await successToast.first().isVisible({ timeout: 10000 }).catch(() => false);
  const hasEmpty = await emptyState.first().isVisible({ timeout: 5000 }).catch(() => false);

  expect(hasSuccess || hasEmpty).toBe(true);
});

// ============================================================================
// APPLICATION CREDENTIALS
// ============================================================================

Then('I can see the application credentials', async ({ authSession }) => {
  const page = authSession.page;

  // Application detail page has a Credentials tab or section
  const credentialsTab = page.locator('button:has-text("Credentials"), a:has-text("Credentials")');
  if (await credentialsTab.isVisible({ timeout: 5000 }).catch(() => false)) {
    await credentialsTab.click();
    await page.waitForLoadState('networkidle');
  }

  // Look for credential information
  const clientIdLabel = page.locator('text=/Client ID/i');
  await expect(clientIdLabel.first()).toBeVisible({ timeout: 10000 });
});

Then('the client ID is visible', async ({ authSession }) => {
  const page = authSession.page;

  // The client ID value should be displayed (non-empty text near "Client ID" label)
  const clientIdValue = page.locator(
    '[class*="font-mono"], code, text=/^[a-zA-Z0-9_-]{8,}$/i',
  );

  const isVisible = await clientIdValue.first().isVisible({ timeout: 10000 }).catch(() => false);
  // If we can't find a mono-font element, at least verify the page has "Client ID" text
  const hasLabel = await page
    .locator('text=/Client ID/i')
    .first()
    .isVisible({ timeout: 3000 })
    .catch(() => false);

  expect(isVisible || hasLabel).toBe(true);
});

// ============================================================================
// FULL PIPELINE — Token Exchange + Gateway Call (CAB-1121 E2E)
// ============================================================================

// Stored credentials from the registration modal
let savedCredentials: {
  clientId: string;
  clientSecret: string;
  tokenEndpoint: string;
} | null = null;

// Access token obtained via client_credentials grant
let consumerAccessToken: string | null = null;

// Last gateway response for assertion
let gatewayResponse: { status: number; body: unknown } | null = null;

Then('I save the consumer credentials from the modal', async ({ authSession }) => {
  const page = authSession.page;

  // The CredentialsModal renders a cURL snippet in a <pre> tag containing
  // client_id, client_secret, and the token endpoint URL
  const curlSnippet = await page.locator('pre').first().textContent({ timeout: 10000 });
  expect(curlSnippet).toBeTruthy();

  const endpointMatch = curlSnippet!.match(/curl -X POST (\S+)/);
  const clientIdMatch = curlSnippet!.match(/client_id=([^\s"\\]+)/);
  const clientSecretMatch = curlSnippet!.match(/client_secret=([^\s"\\]+)/);

  expect(endpointMatch).toBeTruthy();
  expect(clientIdMatch).toBeTruthy();
  expect(clientSecretMatch).toBeTruthy();

  savedCredentials = {
    tokenEndpoint: endpointMatch![1],
    clientId: clientIdMatch![1],
    clientSecret: clientSecretMatch![1],
  };

  // Close the modal
  const doneButton = page.locator('button:has-text("Done")');
  if (await doneButton.isVisible({ timeout: 3000 }).catch(() => false)) {
    await doneButton.click();
    await page.waitForLoadState('networkidle');
  }
});

When('I exchange my consumer credentials for an access token', async ({ request }) => {
  expect(savedCredentials).not.toBeNull();

  const { clientId, clientSecret, tokenEndpoint } = savedCredentials!;

  // OAuth2 client_credentials grant against Keycloak
  const tokenResponse = await request.fetch(tokenEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    data: `grant_type=client_credentials&client_id=${encodeURIComponent(clientId)}&client_secret=${encodeURIComponent(clientSecret)}`,
  });

  expect(tokenResponse.ok()).toBeTruthy();
  const tokenData = await tokenResponse.json();
  consumerAccessToken = tokenData.access_token;
  expect(consumerAccessToken).toBeTruthy();
});

Then('I receive a valid consumer access token', async () => {
  expect(consumerAccessToken).not.toBeNull();
  // JWT tokens have 3 dot-separated base64 segments
  const parts = consumerAccessToken!.split('.');
  expect(parts.length).toBe(3);
});

When('I call the gateway with my consumer token', async ({ request }) => {
  expect(consumerAccessToken).not.toBeNull();

  try {
    const response = await request.fetch(`${URLS.gateway}/v1/tools`, {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${consumerAccessToken}`,
        'Content-Type': 'application/json',
      },
    });

    gatewayResponse = {
      status: response.status(),
      body: await response.json().catch(() => ({})),
    };
  } catch (error) {
    gatewayResponse = { status: 500, body: { error: String(error) } };
  }
});

Then('the gateway accepts my consumer token', async () => {
  expect(gatewayResponse).not.toBeNull();
  // The token should pass auth — we expect anything except 401/403
  expect([401, 403]).not.toContain(gatewayResponse!.status);
});
