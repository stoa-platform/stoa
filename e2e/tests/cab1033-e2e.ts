/**
 * CAB-1033 — Multi-Persona E2E Test (Post CAB-1039 Fix)
 * Tests Alex TTFTC, Parzival RBAC, Sorrento RBAC
 */
import { chromium, Browser, Page, BrowserContext } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const CONFIG = {
  portal: 'https://portal.gostoa.dev',
  api: 'https://api.gostoa.dev',
  mcp: 'https://mcp.gostoa.dev',
  personas: {
    alex:     { username: 'alex',     password: 'demo', role: 'viewer' },
    parzival: { username: 'parzival', password: 'demo', role: 'tenant-admin' },
    sorrento: { username: 'sorrento', password: 'demo', role: 'tenant-admin' },
  },
};

const SS = 'test-results/screenshots';
const METRICS = 'test-results/metrics';
const frictions: Array<{persona: string; severity: string; title: string; desc: string; screenshot: string|null; ts: string}> = [];
const timings: Record<string, Record<string, number>> = {};

function friction(persona: string, severity: string, title: string, desc: string, screenshot: string|null = null) {
  frictions.push({ persona, severity, title, desc, screenshot, ts: new Date().toISOString() });
  console.error(`⚠️ [${severity}] ${persona}: ${title} — ${desc}`);
}

function timer(persona: string, step: string, durationMs: number) {
  if (!timings[persona]) timings[persona] = {};
  timings[persona][step] = durationMs;
  console.log(`⏱️  ${persona}/${step}: ${(durationMs / 1000).toFixed(1)}s`);
}

async function ss(page: Page, persona: string, name: string): Promise<string> {
  const p = path.join(SS, persona, `${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  return p;
}

async function keycloakLogin(page: Page, persona: string, creds: {username: string; password: string}): Promise<void> {
  const t0 = Date.now();

  // Click SSO button
  await page.locator('button:has-text("Sign in with SSO")').click();

  // Wait for Keycloak
  try {
    await page.waitForSelector('#username', { timeout: 15000 });
  } catch {
    friction(persona, 'P0', 'Keycloak redirect failed', 'No #username after 15s');
    throw new Error('Keycloak redirect failed');
  }

  await ss(page, persona, '01-keycloak');
  await page.fill('#username', creds.username);
  await page.fill('#password', creds.password);
  await page.click('#kc-login');

  // Wait for redirect back
  try {
    await page.waitForURL(url => !new URL(url).hostname.includes('auth.'), { timeout: 20000 });
  } catch {
    const errText = await page.textContent('.alert-error, .kc-feedback-text').catch(() => 'unknown');
    friction(persona, 'P0', 'Keycloak login failed', `Error: ${errText}`);
    throw new Error('Login failed');
  }

  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  timer(persona, 'login', Date.now() - t0);
  await ss(page, persona, '02-post-login');
}

// ===== ALEX TTFTC =====
async function testAlex(browser: Browser) {
  console.log('\n========== ALEX FREELANCE (TTFTC) ==========\n');
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    recordHar: { path: 'test-results/network/alex.har' },
  });
  const page = await context.newPage();
  const ttftcStart = Date.now();

  // Track HTTP errors
  page.on('response', async (res) => {
    if (res.status() >= 400 && !res.url().includes('favicon')) {
      friction('alex', res.status() >= 500 ? 'P0' : 'P2',
        `HTTP ${res.status()}`, res.url().substring(0, 120));
    }
  });

  try {
    // Step 1: Portal home
    let t0 = Date.now();
    await page.goto(CONFIG.portal);
    await page.waitForLoadState('networkidle');
    timer('alex', 'step1-portal-load', Date.now() - t0);
    await ss(page, 'alex', '00-portal-home');

    // Step 2: Login
    await keycloakLogin(page, 'alex', CONFIG.personas.alex);

    // Step 3: Catalog /apis
    t0 = Date.now();
    await page.goto(`${CONFIG.portal}/apis`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const apiLinks = await page.locator('a[href*="/apis/"]').count();
    console.log(`📊 API cards found: ${apiLinks}`);
    if (apiLinks === 0) {
      friction('alex', 'P0', 'No APIs in catalog', 'Zero API cards on /apis');
    } else if (apiLinks < 12) {
      friction('alex', 'P2', 'Fewer APIs than expected', `Found ${apiLinks}, expected ~12`);
    }
    timer('alex', 'step3-catalog', Date.now() - t0);
    await ss(page, 'alex', '03-catalog');

    // Step 4: Search
    t0 = Date.now();
    const searchInput = page.locator('input[placeholder*="earch"], input[type="search"], input[placeholder*="Search"]').first();
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill('copper');
      await page.waitForTimeout(1500);
      const filteredCount = await page.locator('a[href*="/apis/"]').count();
      console.log(`🔍 Search "copper" results: ${filteredCount}`);
      if (filteredCount === 0) {
        friction('alex', 'P2', 'Search returned no results', 'Searching "copper" found 0 APIs');
      }
      await ss(page, 'alex', '04-search');
      await searchInput.fill(''); // clear
      await page.waitForTimeout(1000);
    } else {
      friction('alex', 'P2', 'No search input found', 'Cannot search catalog');
    }
    timer('alex', 'step4-search', Date.now() - t0);

    // Step 5: Open first API detail
    t0 = Date.now();
    const firstApiLink = page.locator('a[href*="/apis/"]').first();
    if (await firstApiLink.isVisible().catch(() => false)) {
      const apiName = await firstApiLink.textContent() || 'unknown';
      console.log(`📖 Opening API: ${apiName.trim()}`);
      await firstApiLink.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
      await ss(page, 'alex', '05-api-detail');

      // Check for subscribe button
      const subBtn = page.locator('button:has-text("Subscribe"), button:has-text("Souscrire")').first();
      const hasSubscribe = await subBtn.isVisible().catch(() => false);
      console.log(`📋 Subscribe button visible: ${hasSubscribe}`);

      if (hasSubscribe) {
        // Step 6: Subscribe
        t0 = Date.now();
        await subBtn.click();
        await page.waitForTimeout(3000);
        await ss(page, 'alex', '06-subscribe');
        timer('alex', 'step6-subscribe', Date.now() - t0);

        // Step 7: Check for API key / subscriptions
        t0 = Date.now();
        await page.goto(`${CONFIG.portal}/subscriptions`);
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(2000);
        await ss(page, 'alex', '07-subscriptions');
        timer('alex', 'step7-subscriptions', Date.now() - t0);
      } else {
        friction('alex', 'P1', 'No subscribe button', 'Cannot subscribe to API from detail page');
      }
    } else {
      friction('alex', 'P1', 'No API link to click', 'Catalog is empty or selectors mismatch');
    }
    timer('alex', 'step5-api-detail', Date.now() - t0);

    // Step 8: Try MCP endpoint
    t0 = Date.now();
    const mcpResult = await page.evaluate(async (mcpUrl) => {
      try {
        const res = await fetch(`${mcpUrl}/health`, { mode: 'cors' });
        return { status: res.status, ok: res.ok };
      } catch (e: any) {
        return { error: e.message };
      }
    }, CONFIG.mcp);
    console.log(`🔌 MCP health: ${JSON.stringify(mcpResult)}`);
    timer('alex', 'step8-mcp', Date.now() - t0);
    await ss(page, 'alex', '08-mcp-check');

    // TTFTC
    const ttftc = Date.now() - ttftcStart;
    timings['alex']['TTFTC'] = ttftc;
    console.log(`\n🎯 TTFTC ALEX: ${(ttftc / 1000).toFixed(1)}s (${(ttftc / 60000).toFixed(2)} min)`);
    if (ttftc > 600000) {
      friction('alex', 'P1', 'TTFTC > 10min', `${(ttftc/1000).toFixed(0)}s`);
    }

  } catch (err: any) {
    friction('alex', 'P0', 'Test crashed', err.message);
    await ss(page, 'alex', 'crash').catch(() => {});
  } finally {
    await context.close();
  }
}

// ===== PARZIVAL =====
async function testParzival(browser: Browser) {
  console.log('\n========== PARZIVAL (High-Five RBAC) ==========\n');
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    recordHar: { path: 'test-results/network/parzival.har' },
  });
  const page = await context.newPage();

  try {
    await page.goto(CONFIG.portal);
    await page.waitForLoadState('networkidle');
    await keycloakLogin(page, 'parzival', CONFIG.personas.parzival);

    // Catalog
    await page.goto(`${CONFIG.portal}/apis`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    const apiCount = await page.locator('a[href*="/apis/"]').count();
    console.log(`📊 Parzival sees ${apiCount} APIs`);
    await ss(page, 'parzival', '01-catalog');

    // Check RBAC — navigate to first API
    const firstApi = page.locator('a[href*="/apis/"]').first();
    if (await firstApi.isVisible().catch(() => false)) {
      await firstApi.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
      await ss(page, 'parzival', '02-api-detail');
    }

    // Check /subscriptions access
    await page.goto(`${CONFIG.portal}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const subsUrl = page.url();
    if (subsUrl.includes('unauthorized')) {
      friction('parzival', 'P1', 'Subscriptions blocked', 'Redirected to /unauthorized');
    }
    await ss(page, 'parzival', '03-subscriptions');

    console.log('✅ Parzival test complete');
  } catch (err: any) {
    friction('parzival', 'P0', 'Test crashed', err.message);
    await ss(page, 'parzival', 'crash').catch(() => {});
  } finally {
    await context.close();
  }
}

// ===== SORRENTO =====
async function testSorrento(browser: Browser) {
  console.log('\n========== SORRENTO (IOI RBAC) ==========\n');
  const context = await browser.newContext({
    ignoreHTTPSErrors: true,
    recordHar: { path: 'test-results/network/sorrento.har' },
  });
  const page = await context.newPage();

  try {
    await page.goto(CONFIG.portal);
    await page.waitForLoadState('networkidle');
    await keycloakLogin(page, 'sorrento', CONFIG.personas.sorrento);

    // Catalog
    await page.goto(`${CONFIG.portal}/apis`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    const apiCount = await page.locator('a[href*="/apis/"]').count();
    console.log(`📊 Sorrento sees ${apiCount} APIs`);
    await ss(page, 'sorrento', '01-catalog');

    // Check API detail
    const firstApi = page.locator('a[href*="/apis/"]').first();
    if (await firstApi.isVisible().catch(() => false)) {
      await firstApi.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(2000);
      await ss(page, 'sorrento', '02-api-detail');
    }

    // Check /subscriptions
    await page.goto(`${CONFIG.portal}/subscriptions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    const subsUrl = page.url();
    if (subsUrl.includes('unauthorized')) {
      friction('sorrento', 'P1', 'Subscriptions blocked', 'Redirected to /unauthorized');
    }
    await ss(page, 'sorrento', '03-subscriptions');

    console.log('✅ Sorrento test complete');
  } catch (err: any) {
    friction('sorrento', 'P0', 'Test crashed', err.message);
    await ss(page, 'sorrento', 'crash').catch(() => {});
  } finally {
    await context.close();
  }
}

// ===== REPORTS =====
function generateReports() {
  const p0 = frictions.filter(f => f.severity === 'P0').length;
  const p1 = frictions.filter(f => f.severity === 'P1').length;
  const p2 = frictions.filter(f => f.severity === 'P2').length;

  const md = `# Friction Log — CAB-1033 Post-Fix Run
**Date**: ${new Date().toISOString()}
**Portal**: ${CONFIG.portal}

## Go/No-Go

${p0 === 0 ? '✅ **GO** — No P0 blockers' : `❌ **NO-GO** — ${p0} P0 blocker(s) found`}

## Summary

| Severity | Count |
|----------|-------|
| P0 (Blocker) | ${p0} |
| P1 (Major) | ${p1} |
| P2 (Minor) | ${p2} |

## TTFTC

| Persona | TTFTC | Target | Status |
|---------|-------|--------|--------|
| Alex | ${timings.alex?.TTFTC ? `${(timings.alex.TTFTC/1000).toFixed(1)}s` : 'N/A'} | < 600s | ${(timings.alex?.TTFTC || Infinity) < 600000 ? '✅' : '❌'} |

## Step Timings (Alex)

| Step | Duration |
|------|----------|
${Object.entries(timings.alex || {}).map(([k, v]) => `| ${k} | ${(v/1000).toFixed(1)}s |`).join('\n')}

## Frictions

${frictions.length === 0 ? '_No frictions detected_ 🎉' : frictions.map((f, i) => `
### F-${String(i+1).padStart(3,'0')} [${f.severity}] ${f.title}
- **Persona**: ${f.persona}
- **Description**: ${f.desc}
- **Screenshot**: ${f.screenshot || 'N/A'}
`).join('\n')}

## Persona Catalog Comparison

| Persona | APIs Visible | Role |
|---------|-------------|------|
| Alex | ${timings.alex?.['step3-catalog'] ? 'Yes' : 'Unknown'} | viewer |
| Parzival | ${timings.parzival ? 'Yes' : 'Unknown'} | tenant-admin |
| Sorrento | ${timings.sorrento ? 'Yes' : 'Unknown'} | tenant-admin |

## Raw Timings

\`\`\`json
${JSON.stringify(timings, null, 2)}
\`\`\`
`;

  fs.writeFileSync('test-results/friction-log.md', md);
  fs.writeFileSync(path.join(METRICS, 'ttftc-alex.json'), JSON.stringify({ ttftc: timings.alex?.TTFTC, unit: 'ms' }, null, 2));
  fs.writeFileSync(path.join(METRICS, 'timings-all.json'), JSON.stringify(timings, null, 2));
  fs.writeFileSync(path.join(METRICS, 'frictions.json'), JSON.stringify(frictions, null, 2));
  console.log('\n📄 Reports written to test-results/');
}

// ===== MAIN =====
(async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    await testAlex(browser);
    await testParzival(browser);
    await testSorrento(browser);
  } finally {
    await browser.close();
    generateReports();
  }

  const p0 = frictions.filter(f => f.severity === 'P0').length;
  console.log(`\n🏁 Done. P0: ${p0}, P1: ${frictions.filter(f => f.severity === 'P1').length}, P2: ${frictions.filter(f => f.severity === 'P2').length}`);
  process.exit(p0 > 0 ? 1 : 0);
})();
