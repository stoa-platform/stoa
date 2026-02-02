import { chromium } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const DIAG_DIR = 'test-results/diagnostic';
const SS = path.join(DIAG_DIR, 'screenshots');
fs.mkdirSync(SS, { recursive: true });

const PORTAL = 'https://portal.gostoa.dev';

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();

  // Login flow
  await page.goto(PORTAL);
  await page.waitForLoadState('networkidle');

  const needsLogin = await page.locator('button:has-text("Sign in"), button:has-text("SSO")').first().isVisible().catch(() => false);

  console.log('Current URL:', page.url());
  console.log('Needs login:', needsLogin);
  await page.screenshot({ path: path.join(SS, '00-initial.png'), fullPage: true });

  if (needsLogin) {
    await page.locator('button:has-text("Sign in"), button:has-text("SSO")').first().click();
    // Wait for either Keycloak form or redirect
    await page.waitForLoadState('networkidle');
    console.log('After click URL:', page.url());
    await page.screenshot({ path: path.join(SS, '00b-after-click.png'), fullPage: true });
    await page.waitForSelector('#username', { timeout: 15000 });
    await page.locator('#username').fill('alex');
    await page.locator('#password').fill('demo');
    await page.locator('#kc-login').click();
    await page.waitForURL(
      url => {
        const hostname = new URL(url).hostname;
        return !hostname.includes('auth.');
      },
      { timeout: 30000 },
    );
  }

  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(SS, '01-dashboard.png'), fullPage: true });
  console.log('Dashboard URL:', page.url());

  // Navigate to /apis
  console.log('\n🎯 Navigating to /apis...');
  await page.goto(PORTAL + '/apis');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(5000);
  await page.screenshot({ path: path.join(SS, '02-apis.png'), fullPage: true });

  const finalUrl = page.url();
  const bodyText = await page.textContent('body') || '';

  console.log('Final URL:', finalUrl);
  console.log('Contains Access Denied:', bodyText.toLowerCase().includes('access denied'));

  if (finalUrl.includes('/unauthorized')) {
    console.log('\n🚨 STILL BLOCKED — redirected to /unauthorized');
  } else if (finalUrl.includes('/apis')) {
    console.log('\n✅ SUCCESS — /apis page loaded!');

    // Check if APIs are visible
    const apiCards = await page.locator('a[href^="/apis/"]').count();
    console.log(`API cards found: ${apiCards}`);
  }

  await context.close();
  await browser.close();
}

run().catch(e => { console.error(e); process.exit(1); });
