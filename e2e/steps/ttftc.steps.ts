/**
 * TTFTC (Time to First Tool Call) step definitions — CAB-1034
 *
 * Measures each step of Alex Freelance's onboarding journey through 7 timed steps.
 * Every step uses soft assertions: on failure the friction is documented and the
 * scenario continues (the test is NOT blocking).
 *
 * Auth strategy: uses Playwright storageState via the authSession fixture (CAB-1041).
 */

import { createBdd } from 'playwright-bdd';
import { test, expect, URLS } from '../fixtures/test-base';
import { PERSONAS, PersonaKey, getAuthStatePath } from '../fixtures/personas';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';
import type { Page } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const { Given, When, Then } = createBdd(test);

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

interface StepTiming {
  start: number;
  end: number;
  durationMs: number;
  status: 'pass' | 'friction' | 'fail';
  friction: string | null;
}

let ttftcStart = 0;
let lastStepEnd = 0;
const stepTimings: Record<string, StepTiming> = {};
const frictions: { step: string; message: string }[] = [];

/** API key captured during the subscribe flow */
let capturedApiKey: string | null = null;

/** Tracks which page holds the detail we're looking at (/apis/:id or /servers/:id) */
let currentDetailUrl: string | null = null;

const RESULTS_DIR = path.join(__dirname, '..', 'test-results');
const METRICS_DIR = path.join(RESULTS_DIR, 'metrics');
const SCREENSHOTS_DIR = path.join(RESULTS_DIR, 'screenshots');
const REPORT_PATH = path.join(RESULTS_DIR, 'alex-ttftc-report.md');

const FRICTION_THRESHOLD_MS = 30_000; // 30 seconds = friction

function ensureDir(dir: string) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

/**
 * Record a friction event. The test continues — we just document the problem.
 */
function recordFriction(step: string, message: string) {
  frictions.push({ step, message });
  console.log(`[FRICTION] ${step}: ${message}`);
}

/**
 * Soft-assert helper: runs fn() and returns true if it succeeded, false otherwise.
 * On failure, records friction and does NOT throw.
 */
async function softAssert(
  step: string,
  description: string,
  fn: () => Promise<void>,
): Promise<boolean> {
  try {
    await fn();
    return true;
  } catch (err) {
    const message = `${description}: ${(err as Error).message?.substring(0, 200) || 'unknown error'}`;
    recordFriction(step, message);
    return false;
  }
}

/**
 * Take a screenshot (always succeeds — writes a placeholder on error).
 */
async function safeScreenshot(page: Page, name: string): Promise<void> {
  try {
    ensureDir(path.join(SCREENSHOTS_DIR, path.dirname(name)));
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, `${name}.png`),
      fullPage: true,
    });
  } catch (err) {
    console.log(`[SCREENSHOT] Failed for ${name}: ${(err as Error).message}`);
  }
}

// ============================================================================
// TIMER STEPS
// ============================================================================

Given('I start the TTFTC timer', async () => {
  ttftcStart = Date.now();
  lastStepEnd = ttftcStart;
  ensureDir(METRICS_DIR);
  ensureDir(path.join(SCREENSHOTS_DIR, 'alex'));
  // Reset state from any previous run
  Object.keys(stepTimings).forEach((k) => delete stepTimings[k]);
  frictions.length = 0;
  capturedApiKey = null;
  currentDetailUrl = null;
});

Then(
  'I record TTFTC step {string} with screenshot',
  async ({ page, authSession }, stepName: string) => {
    const now = Date.now();
    const durationMs = now - lastStepEnd;

    const isFriction = durationMs > FRICTION_THRESHOLD_MS;
    const existingFriction = frictions.find((f) => f.step === stepName);
    const status: StepTiming['status'] = existingFriction
      ? 'fail'
      : isFriction
        ? 'friction'
        : 'pass';

    stepTimings[stepName] = {
      start: lastStepEnd,
      end: now,
      durationMs,
      status,
      friction: existingFriction?.message || (isFriction ? `Duration ${(durationMs / 1000).toFixed(1)}s exceeds 30s threshold` : null),
    };

    lastStepEnd = now;

    const statusIcon = status === 'pass' ? 'PASS' : status === 'friction' ? 'SLOW' : 'FAIL';
    console.log(
      `[TTFTC] ${stepName}: ${(durationMs / 1000).toFixed(1)}s [${statusIcon}] (total: ${((now - ttftcStart) / 1000).toFixed(1)}s)`,
    );

    // Use authSession.page if available (post-login), fallback to default page
    const activePage = authSession?.page || page;
    await safeScreenshot(activePage, `alex/${stepName}`);
  },
);

Then('I stop the TTFTC timer', async () => {
  const totalMs = Date.now() - ttftcStart;
  const result = {
    persona: 'alex',
    totalMs,
    totalSeconds: totalMs / 1000,
    target: 600,
    pass: totalMs < 600_000,
    steps: stepTimings,
    frictions,
    timestamp: new Date().toISOString(),
  };

  ensureDir(METRICS_DIR);
  fs.writeFileSync(
    path.join(METRICS_DIR, 'ttftc-alex.json'),
    JSON.stringify(result, null, 2),
  );

  const passLabel = result.pass ? 'PASS' : 'FAIL';
  console.log(
    `\n[TTFTC] Alex Freelance total: ${result.totalSeconds.toFixed(1)}s (target <600s) — ${passLabel}`,
  );
  console.log(`[TTFTC] Frictions recorded: ${frictions.length}`);
});

Then('the TTFTC is under {int} seconds', async ({}, targetSeconds: number) => {
  const totalMs = Date.now() - ttftcStart;
  // Soft check — log but do not fail the test
  if (totalMs >= targetSeconds * 1000) {
    console.log(
      `[TTFTC] WARNING: Total ${(totalMs / 1000).toFixed(1)}s exceeds target ${targetSeconds}s`,
    );
  }
});

// ============================================================================
// STEP 1 — LANDING PAGE
// ============================================================================

When('I navigate to the Portal homepage', async ({ page }) => {
  await page.goto(URLS.portal);
  await page.waitForLoadState('networkidle').catch(() => {});
});

Then('the Portal loads successfully', async ({ page }) => {
  await softAssert('01-landing', 'Portal hostname check', async () => {
    expect(page.url()).toContain(new URL(URLS.portal).hostname);
  });

  // Check that something rendered (not a blank page)
  await softAssert('01-landing', 'Page has content', async () => {
    await page.waitForSelector('body', { timeout: 10000 });
    const bodyText = await page.textContent('body');
    expect(bodyText?.length).toBeGreaterThan(10);
  });
});

// ============================================================================
// STEP 2 — BROWSE CATALOGUE (unauthenticated)
// ============================================================================

When('I attempt to browse the API catalog', async ({ page }) => {
  try {
    await page.goto(`${URLS.portal}/apis`);
    await page.waitForLoadState('networkidle').catch(() => {});
  } catch (err) {
    recordFriction('02-catalog-browse', `Navigation to /apis failed: ${(err as Error).message}`);
  }
});

Then('I see catalog content or a login prompt', async ({ page }) => {
  // The portal may redirect unauthenticated users to a login page.
  // Either outcome is acceptable — we document the experience.
  const url = page.url();

  const isOnLogin =
    url.includes('/auth/') ||
    url.includes('auth.') ||
    (await page.locator('#username').isVisible().catch(() => false)) ||
    (await page
      .locator(
        'button:has-text("Sign in"), button:has-text("Login"), button:has-text("Sign in with SSO")',
      )
      .first()
      .isVisible()
      .catch(() => false));

  const isOnCatalog =
    url.includes('/apis') &&
    (await page.locator('a[href^="/apis/"]').first().isVisible({ timeout: 5000 }).catch(() => false));

  if (!isOnLogin && !isOnCatalog) {
    recordFriction(
      '02-catalog-browse',
      `Unexpected state: neither login prompt nor catalog. URL: ${url}`,
    );
  } else if (isOnLogin) {
    console.log('[TTFTC] 02-catalog-browse: Portal requires login before catalog access.');
  } else {
    console.log('[TTFTC] 02-catalog-browse: Catalog is publicly accessible.');
  }
});

// ============================================================================
// STEP 3 — LOGIN AS ALEX (using storageState from CAB-1041)
// ============================================================================

When(
  'I login as {string} using auth fixtures',
  async ({ authSession }, personaKey: string) => {
    const persona = PERSONAS[personaKey as PersonaKey];
    if (!persona) {
      recordFriction('03-login', `Unknown persona: ${personaKey}`);
      return;
    }

    const authStatePath = getAuthStatePath(personaKey as PersonaKey);
    if (fs.existsSync(authStatePath)) {
      // Use the storageState fixture (CAB-1041 pattern)
      await authSession.switchPersona(personaKey as PersonaKey);
      console.log(`[TTFTC] 03-login: Restored auth state for ${personaKey} via storageState.`);
    } else {
      // Fallback: manual Keycloak login
      console.log(
        `[TTFTC] 03-login: No storageState for ${personaKey}, attempting manual Keycloak login.`,
      );
      const page = authSession.page;

      try {
        await page.goto(URLS.portal);
        await page.waitForLoadState('networkidle').catch(() => {});

        // Click login button if present
        const loginBtn = page.locator(
          'button:has-text("Sign in"), button:has-text("Login"), button:has-text("Sign in with SSO"), a:has-text("Sign in")',
        );
        if (await loginBtn.first().isVisible({ timeout: 5000 }).catch(() => false)) {
          await loginBtn.first().click();
        }

        // Fill Keycloak form
        const isKeycloak = await page
          .waitForSelector('#username', { timeout: 15000 })
          .then(() => true)
          .catch(() => false);

        if (isKeycloak) {
          await page.locator('#username').fill(persona.username);
          await page.locator('#password').fill(persona.password);
          await page.locator('#kc-login').click();
          await page.waitForURL(
            (url) => !url.hostname.includes('auth.') && !url.pathname.includes('/auth/'),
            { timeout: 30000 },
          );
        } else {
          recordFriction('03-login', 'Keycloak login form not found within 15s');
        }
      } catch (err) {
        recordFriction('03-login', `Manual login failed: ${(err as Error).message}`);
      }
    }
  },
);

Then('I am on an authenticated page', async ({ authSession }) => {
  const page = authSession.page;

  await softAssert('03-login', 'Not on a login/auth page', async () => {
    await page.goto(URLS.portal);
    await page.waitForLoadState('networkidle').catch(() => {});

    const url = page.url();
    expect(url).not.toContain('/auth/');

    // Verify we see authenticated content (sidebar, user icon, etc.)
    const hasAuthContent =
      (await page.locator('text=Home').first().isVisible({ timeout: 10000 }).catch(() => false)) ||
      (await page.locator('nav').first().isVisible({ timeout: 5000 }).catch(() => false)) ||
      (await page
        .locator('[aria-label="User menu"]')
        .isVisible({ timeout: 5000 })
        .catch(() => false));

    if (!hasAuthContent) {
      recordFriction('03-login', 'No authenticated content detected after login');
    }
  });
});

// ============================================================================
// STEP 4 — BROWSE CATALOGUE (authenticated)
// ============================================================================

When('I navigate to the API catalog as authenticated user', async ({ authSession }) => {
  const page = authSession.page;
  try {
    await page.goto(`${URLS.portal}/apis`);
    await page.waitForLoadState('networkidle').catch(() => {});
    // Wait for loading spinners to disappear
    await page
      .locator('text=Loading')
      .first()
      .waitFor({ state: 'hidden', timeout: 15000 })
      .catch(() => {});
  } catch (err) {
    recordFriction(
      '04-catalog-authenticated',
      `Navigation to /apis failed: ${(err as Error).message}`,
    );
  }
});

Then('I see APIs or MCP tools in the catalog', async ({ authSession }) => {
  const page = authSession.page;

  // Check for API cards (a[href^="/apis/"]) or MCP server cards (a[href^="/servers/"])
  const hasApiCards = await page
    .locator('a[href^="/apis/"]')
    .first()
    .isVisible({ timeout: 10000 })
    .catch(() => false);

  if (hasApiCards) {
    const count = await page.locator('a[href^="/apis/"]').count();
    console.log(`[TTFTC] 04-catalog-authenticated: Found ${count} API card(s) in catalog.`);
    return;
  }

  // Maybe no APIs but the page loaded correctly
  const hasEmptyState = await page
    .locator('text=No APIs Found, text=No APIs found, text=No APIs available')
    .first()
    .isVisible({ timeout: 3000 })
    .catch(() => false);

  if (hasEmptyState) {
    recordFriction(
      '04-catalog-authenticated',
      'Catalog loaded but contains no APIs. Try /servers for MCP tools.',
    );

    // Attempt fallback to MCP servers page
    try {
      await page.goto(`${URLS.portal}/servers`);
      await page.waitForLoadState('networkidle').catch(() => {});
      const hasServers = await page
        .locator('a[href^="/servers/"]')
        .first()
        .isVisible({ timeout: 10000 })
        .catch(() => false);
      if (hasServers) {
        const sCount = await page.locator('a[href^="/servers/"]').count();
        console.log(
          `[TTFTC] 04-catalog-authenticated: Found ${sCount} MCP server(s) via fallback.`,
        );
      }
    } catch {
      // Already documented
    }
  } else {
    recordFriction(
      '04-catalog-authenticated',
      'Neither API cards nor empty state found. Page may not have loaded.',
    );
  }
});

// ============================================================================
// STEP 5 — SELECT ITEM DETAIL
// ============================================================================

When('I click on the first available catalog item', async ({ authSession }) => {
  const page = authSession.page;

  // Try API cards first, then server cards
  const apiLink = page.locator('a[href^="/apis/"]').first();
  const serverLink = page.locator('a[href^="/servers/"]').first();

  try {
    if (await apiLink.isVisible({ timeout: 3000 }).catch(() => false)) {
      const href = await apiLink.getAttribute('href');
      await apiLink.click();
      await page.waitForLoadState('networkidle').catch(() => {});
      currentDetailUrl = page.url();
      console.log(`[TTFTC] 05-item-detail: Clicked API link -> ${href}`);
    } else if (await serverLink.isVisible({ timeout: 3000 }).catch(() => false)) {
      const href = await serverLink.getAttribute('href');
      await serverLink.click();
      await page.waitForLoadState('networkidle').catch(() => {});
      currentDetailUrl = page.url();
      console.log(`[TTFTC] 05-item-detail: Clicked server link -> ${href}`);
    } else {
      recordFriction('05-item-detail', 'No API or server links found on the page to click.');
    }
  } catch (err) {
    recordFriction('05-item-detail', `Click failed: ${(err as Error).message}`);
  }
});

Then('I see the item detail page', async ({ authSession }) => {
  const page = authSession.page;
  const url = page.url();

  await softAssert('05-item-detail', 'URL contains /apis/ or /servers/', async () => {
    const isDetail = url.includes('/apis/') || url.includes('/servers/');
    expect(isDetail).toBe(true);
  });

  // Verify the page has a heading (API name or tool name)
  await softAssert('05-item-detail', 'Detail page has h1 heading', async () => {
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 });
  });
});

// ============================================================================
// STEP 6 — SUBSCRIBE / REQUEST CREDENTIALS
// ============================================================================

When('I attempt to subscribe to the current item', async ({ authSession }) => {
  const page = authSession.page;

  // Look for Subscribe button on the detail page
  const subscribeBtn = page.locator(
    'button:has-text("Subscribe"), a:has-text("Subscribe")',
  );

  try {
    if (await subscribeBtn.first().isVisible({ timeout: 5000 }).catch(() => false)) {
      await subscribeBtn.first().click();
      console.log('[TTFTC] 06-subscribe: Clicked Subscribe button.');

      // Wait for the subscribe modal to open
      const modalVisible = await page
        .locator('text=Subscribe to API, text=Subscribe to Tool, h2:has-text("Subscribe")')
        .first()
        .isVisible({ timeout: 5000 })
        .catch(() => false);

      if (modalVisible) {
        console.log('[TTFTC] 06-subscribe: Subscribe modal opened.');

        // Select application if available
        const appSelect = page.locator('select#application');
        if (await appSelect.isVisible({ timeout: 3000 }).catch(() => false)) {
          const options = await appSelect.locator('option').allTextContents();
          if (options.length > 1) {
            // Select the first non-placeholder option
            await appSelect.selectOption({ index: 1 });
            console.log('[TTFTC] 06-subscribe: Selected application from dropdown.');
          } else {
            recordFriction(
              '06-subscribe',
              'No applications available in the dropdown. Alex needs to create an app first.',
            );
            // Close modal and return
            const closeBtn = page.locator('button:has-text("Cancel"), button:has-text("Close")');
            await closeBtn.first().click().catch(() => {});
            return;
          }
        }

        // Select the Free plan (click the plan button)
        const freePlanBtn = page.locator('button:has-text("Free")');
        if (await freePlanBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
          await freePlanBtn.click();
          console.log('[TTFTC] 06-subscribe: Selected Free plan.');
        }

        // Submit the subscription form
        const submitBtn = page.locator(
          'button[type="submit"]:has-text("Subscribe"), button:has-text("Subscribing")',
        );
        if (await submitBtn.first().isVisible({ timeout: 3000 }).catch(() => false)) {
          const isDisabled = await submitBtn.first().isDisabled();
          if (!isDisabled) {
            await submitBtn.first().click();
            console.log('[TTFTC] 06-subscribe: Submitted subscription.');

            // Wait for success or error
            await page.waitForTimeout(2000);

            // Check for API key in the success modal
            const apiKeyEl = page.locator('code[aria-label="API Key"]');
            if (await apiKeyEl.isVisible({ timeout: 5000 }).catch(() => false)) {
              capturedApiKey = (await apiKeyEl.textContent())?.trim() || null;
              console.log(
                `[TTFTC] 06-subscribe: Captured API key (${capturedApiKey ? capturedApiKey.substring(0, 8) + '...' : 'null'}).`,
              );

              // Close the success modal
              const doneBtn = page.locator('button:has-text("Done")');
              await doneBtn.click().catch(() => {});
            }
          } else {
            recordFriction(
              '06-subscribe',
              'Submit button is disabled. Missing required fields (application or plan).',
            );
          }
        }
      } else {
        recordFriction('06-subscribe', 'Subscribe modal did not open after clicking Subscribe.');
      }
    } else {
      recordFriction(
        '06-subscribe',
        'No Subscribe button found on detail page. Feature may be disabled or user lacks permissions.',
      );
    }
  } catch (err) {
    recordFriction('06-subscribe', `Subscribe flow error: ${(err as Error).message}`);
  }
});

Then('the subscribe action completes or is documented as friction', async () => {
  // This step is intentionally a no-op for assertion.
  // Any friction was already recorded in the When step above.
  if (capturedApiKey) {
    console.log('[TTFTC] 06-subscribe: Subscription successful, API key obtained.');
  } else {
    const hasFriction = frictions.some((f) => f.step === '06-subscribe');
    if (!hasFriction) {
      recordFriction(
        '06-subscribe',
        'Subscribe flow completed but no API key was captured. May need manual verification.',
      );
    }
  }
});

// ============================================================================
// STEP 7 — FIRST TOOL CALL
// ============================================================================

When('I attempt my first API or tool call', async ({ authSession }) => {
  const page = authSession.page;

  try {
    // Attempt to call the gateway health endpoint with the captured key
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (capturedApiKey) {
      headers['X-API-Key'] = capturedApiKey;
      headers['Authorization'] = `Bearer ${capturedApiKey}`;
    }

    const response = await page.request.fetch(`${URLS.gateway}/api/v1/health`, {
      headers,
    });

    const status = response.status();
    console.log(`[TTFTC] 07-first-call: API response HTTP ${status}`);

    if (status >= 500) {
      recordFriction('07-first-call', `Server error: HTTP ${status}`);
    } else if (status === 401 || status === 403) {
      recordFriction(
        '07-first-call',
        `Auth error: HTTP ${status}. API key may be invalid or missing.`,
      );
    } else {
      console.log(`[TTFTC] 07-first-call: Received HTTP ${status} — call completed.`);
    }

    // Store for assertion
    (page as any).__lastApiResponse = response;
  } catch (err) {
    recordFriction('07-first-call', `API call failed: ${(err as Error).message}`);
  }
});

Then('the call response is recorded', async ({ authSession }) => {
  const page = authSession.page;
  const response = (page as any).__lastApiResponse;

  if (response) {
    const status = response.status();
    console.log(`[TTFTC] 07-first-call: Final status HTTP ${status}`);
    // We accept any response that isn't a 5xx as "recorded"
  } else {
    const hasFriction = frictions.some((f) => f.step === '07-first-call');
    if (!hasFriction) {
      recordFriction('07-first-call', 'No API response object available.');
    }
  }
});

// ============================================================================
// FRICTION REPORT GENERATOR
// ============================================================================

Then('I generate the TTFTC friction report', async () => {
  const totalMs = Date.now() - ttftcStart;
  const totalSeconds = totalMs / 1000;
  const date = new Date().toISOString().split('T')[0];

  const stepDescriptions: Record<string, string> = {
    '01-landing': 'Landing page loads',
    '02-catalog-browse': 'Browse catalogue (unauthenticated)',
    '03-login': 'Login as Alex via Keycloak',
    '04-catalog-authenticated': 'Browse catalogue (authenticated)',
    '05-item-detail': 'Select API/tool detail',
    '06-subscribe': 'Subscribe / request credentials',
    '07-first-call': 'First API/tool call (TTFTC)',
  };

  const lines: string[] = [];
  lines.push(`# Alex TTFTC Report -- ${date}`);
  lines.push('');
  lines.push('## Step Timings');
  lines.push('');
  lines.push('| Step | Description | Duration | Status | Notes |');
  lines.push('|------|-------------|----------|--------|-------|');

  let frictionCount = 0;

  for (const [stepName, timing] of Object.entries(stepTimings)) {
    const desc = stepDescriptions[stepName] || stepName;
    const durationStr = `${(timing.durationMs / 1000).toFixed(1)}s`;
    let statusStr: string;
    switch (timing.status) {
      case 'pass':
        statusStr = 'PASS';
        break;
      case 'friction':
        statusStr = 'SLOW (>30s)';
        frictionCount++;
        break;
      case 'fail':
        statusStr = 'FAIL';
        frictionCount++;
        break;
    }
    const notes = timing.friction || '';
    lines.push(`| ${stepName} | ${desc} | ${durationStr} | ${statusStr} | ${notes} |`);
  }

  lines.push('');
  lines.push('## Summary');
  lines.push('');

  const totalFormatted =
    totalSeconds >= 60
      ? `${Math.floor(totalSeconds / 60)}m${Math.round(totalSeconds % 60)}s`
      : `${totalSeconds.toFixed(1)}s`;

  const verdict = totalMs < 600_000 && frictionCount <= 3 ? 'PASS' : 'FAIL';

  lines.push(`**Total TTFTC**: ${totalFormatted}`);
  lines.push(`**Frictions**: ${frictionCount}`);
  lines.push(`**Target**: < 10 min`);
  lines.push(`**Verdict**: ${verdict} ${verdict === 'PASS' ? '(target met)' : '(target exceeded or too many frictions)'}`);
  lines.push('');

  if (frictions.length > 0) {
    lines.push('## Friction Log');
    lines.push('');
    for (const f of frictions) {
      lines.push(`- **${f.step}**: ${f.message}`);
    }
    lines.push('');
  }

  lines.push('## Recommendations');
  lines.push('');
  if (frictionCount === 0) {
    lines.push('No frictions detected. Onboarding flow is smooth.');
  } else {
    lines.push('Review the friction log above and address the following:');
    lines.push('');
    for (const f of frictions) {
      lines.push(`- [ ] Fix ${f.step}: ${f.message.substring(0, 100)}`);
    }
  }
  lines.push('');
  lines.push('---');
  lines.push(`*Generated by e2e/steps/ttftc.steps.ts on ${new Date().toISOString()}*`);

  const report = lines.join('\n');

  ensureDir(RESULTS_DIR);
  fs.writeFileSync(REPORT_PATH, report);
  console.log(`[TTFTC] Friction report written to ${REPORT_PATH}`);
});

// ============================================================================
// SCREENSHOT STEP (generic, used by other features too — kept for compat)
// ============================================================================

Then('I take a screenshot {string}', async ({ page }, name: string) => {
  await safeScreenshot(page, name);
});
