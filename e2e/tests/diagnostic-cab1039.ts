/**
 * CAB-1039 — Diagnostic: Why does viewer role get Access Denied on /apis?
 *
 * This script captures JWT claims, network errors, page state, and direct API
 * responses to pinpoint whether the block is frontend or backend.
 */

import { chromium } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const DIAG_DIR = path.join(__dirname, '..', 'test-results', 'diagnostic');
const SCREENSHOTS_DIR = path.join(DIAG_DIR, 'screenshots');

const PORTAL_URL = process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev';
const ALEX_USER = process.env.ALEX_USER || 'alex';
const ALEX_PASSWORD = process.env.ALEX_PASSWORD || 'demo';

// Ensure directories
fs.mkdirSync(DIAG_DIR, { recursive: true });
fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });

// Clear previous errors file
if (fs.existsSync(path.join(DIAG_DIR, 'errors.jsonl'))) {
  fs.unlinkSync(path.join(DIAG_DIR, 'errors.jsonl'));
}

interface NetworkError {
  timestamp: string;
  url: string;
  status: number;
  statusText: string;
  responseHeaders: Record<string, string>;
  responseBody: string;
  wwwAuthenticate: string | null;
  xError: string | null;
}

interface JwtDiag {
  timestamp: string;
  requestUrl: string;
  jwt: {
    header: Record<string, any>;
    claims: Record<string, any>;
    full_payload: Record<string, any>;
  };
}

const errors: NetworkError[] = [];
let jwtDiag: JwtDiag | null = null;

async function run() {
  console.log('🔍 CAB-1039 Diagnostic — Starting\n');
  console.log(`Portal: ${PORTAL_URL}`);
  console.log(`User: ${ALEX_USER}\n`);

  const browser = await chromium.launch({ headless: true });

  // Phase 1: Create context with HAR recording + interceptors
  const context = await browser.newContext({
    recordHar: { path: path.join(DIAG_DIR, 'network.har') },
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();

  // === NETWORK INTERCEPTOR ===
  page.on('response', async (response) => {
    const url = response.url();
    const status = response.status();

    if (status >= 400) {
      const headers = response.headers();
      let body = '';
      try { body = await response.text(); } catch { body = '[unreadable]'; }

      const diagnostic: NetworkError = {
        timestamp: new Date().toISOString(),
        url,
        status,
        statusText: response.statusText(),
        responseHeaders: headers,
        responseBody: body,
        wwwAuthenticate: headers['www-authenticate'] || null,
        xError: headers['x-error'] || headers['x-stoa-error'] || null,
      };

      errors.push(diagnostic);
      fs.appendFileSync(
        path.join(DIAG_DIR, 'errors.jsonl'),
        JSON.stringify(diagnostic) + '\n',
      );
      console.error(`❌ ${status} ${url}`);
      console.error(`   WWW-Authenticate: ${diagnostic.wwwAuthenticate}`);
      console.error(`   Body: ${body.substring(0, 500)}`);
    }
  });

  // === JWT INTERCEPTOR ===
  page.on('request', (request) => {
    const authHeader = request.headers()['authorization'];
    if (authHeader && authHeader.startsWith('Bearer ')) {
      const token = authHeader.split(' ')[1];
      const parts = token.split('.');
      if (parts.length === 3) {
        try {
          const header = JSON.parse(Buffer.from(parts[0], 'base64url').toString());
          const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString());

          jwtDiag = {
            timestamp: new Date().toISOString(),
            requestUrl: request.url(),
            jwt: {
              header: {
                alg: header.alg,
                typ: header.typ,
                kid: header.kid,
              },
              claims: {
                sub: payload.sub,
                aud: payload.aud,
                iss: payload.iss,
                exp: payload.exp,
                iat: payload.iat,
                azp: payload.azp,
                scope: payload.scope,
                preferred_username: payload.preferred_username,
                email: payload.email,
                realm_access: payload.realm_access,
                resource_access: payload.resource_access,
                tenant_id: payload.tenant_id || payload.stoa_tenant || null,
                groups: payload.groups || null,
              },
              full_payload: payload,
            },
          };

          fs.writeFileSync(
            path.join(DIAG_DIR, 'jwt-decoded.json'),
            JSON.stringify(jwtDiag, null, 2),
          );
          console.log(`🔑 JWT captured for ${request.url()}`);
          console.log(`   sub: ${payload.sub}`);
          console.log(`   aud: ${JSON.stringify(payload.aud)}`);
          console.log(`   realm_access.roles: ${JSON.stringify(payload.realm_access?.roles)}`);
          console.log(`   resource_access keys: ${JSON.stringify(Object.keys(payload.resource_access || {}))}`);
          console.log(`   scope: ${payload.scope}`);
        } catch (e: any) {
          console.error(`⚠️ JWT decode failed: ${e.message}`);
        }
      }
    }
  });

  // Phase 2: Login + navigate to /apis
  console.log('\n📍 Phase 2: Login + navigate to /apis\n');

  // Step 1: Navigate to Portal
  await page.goto(PORTAL_URL);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '01-portal-home.png'), fullPage: true });
  console.log('📸 01-portal-home.png');

  // Step 2: Click login button if visible
  const loginButton = page.locator(
    'button:has-text("Sign in"), button:has-text("Login"), button:has-text("Se connecter"), a:has-text("Sign in"), button:has-text("Sign in with SSO")'
  );
  if (await loginButton.first().isVisible({ timeout: 5000 }).catch(() => false)) {
    await loginButton.first().click();
    console.log('Clicked login button');
  }

  // Step 3: Wait for Keycloak form
  await page.waitForSelector('#username', { timeout: 30000 });
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '02-keycloak-login.png'), fullPage: true });
  console.log('📸 02-keycloak-login.png');

  // Step 4: Fill and submit
  await page.locator('#username').fill(ALEX_USER);
  await page.locator('#password').fill(ALEX_PASSWORD);
  await page.locator('#kc-login').click();

  // Step 5: Wait for redirect back to Portal
  await page.waitForURL(
    url => !url.hostname.includes('auth.'),
    { timeout: 30000 },
  );
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '03-post-login.png'), fullPage: true });
  console.log('📸 03-post-login.png');
  console.log(`Post-login URL: ${page.url()}`);

  // Step 6: Capture session cookies (metadata only)
  const cookies = await context.cookies();
  const sessionCookies = cookies.filter(c =>
    c.name.includes('session') ||
    c.name.includes('token') ||
    c.name.includes('auth') ||
    c.name.includes('KC_') ||
    c.name.includes('KEYCLOAK')
  );
  fs.writeFileSync(
    path.join(DIAG_DIR, 'session-cookies.json'),
    JSON.stringify(sessionCookies.map(c => ({
      name: c.name,
      domain: c.domain,
      path: c.path,
      httpOnly: c.httpOnly,
      secure: c.secure,
      sameSite: c.sameSite,
    })), null, 2),
  );

  // Step 7: Capture localStorage contents (token storage)
  const localStorageData = await page.evaluate(() => {
    const data: Record<string, string> = {};
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key) {
        const val = localStorage.getItem(key) || '';
        // Only store key names and first 50 chars for security
        data[key] = val.length > 50 ? val.substring(0, 50) + '...[truncated]' : val;
      }
    }
    return data;
  });
  fs.writeFileSync(
    path.join(DIAG_DIR, 'localStorage-keys.json'),
    JSON.stringify(localStorageData, null, 2),
  );
  console.log(`localStorage keys: ${Object.keys(localStorageData).join(', ')}`);

  // Step 8: THE CRITICAL MOMENT — Navigate to /apis
  console.log('\n🎯 === NAVIGATION VERS /apis — MOMENT CRITIQUE ===\n');

  // Clear errors before navigation to capture only /apis-related errors
  const errorsBeforeApis = errors.length;

  await page.goto(`${PORTAL_URL}/apis`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  await page.screenshot({ path: path.join(SCREENSHOTS_DIR, '04-apis-result.png'), fullPage: true });
  console.log('📸 04-apis-result.png');

  // Step 9: Capture page state
  const pageTitle = await page.title();
  const pageUrl = page.url();
  const pageContent = await page.textContent('body') || '';

  const pageState = {
    finalUrl: pageUrl,
    title: pageTitle,
    wasRedirected: !pageUrl.includes('/apis'),
    redirectedTo: pageUrl,
    bodyContains: {
      accessDenied: pageContent.toLowerCase().includes('access denied'),
      forbidden: pageContent.toLowerCase().includes('forbidden'),
      unauthorized: pageContent.toLowerCase().includes('unauthorized'),
      error: pageContent.toLowerCase().includes('error'),
      permission: pageContent.toLowerCase().includes('permission'),
      catalogue: pageContent.toLowerCase().includes('catalog') || pageContent.toLowerCase().includes('catalogue'),
    },
    // Capture visible user info from the page
    visibleUserInfo: await page.evaluate(() => {
      const body = document.body.innerText;
      const emailMatch = body.match(/[\w.-]+@[\w.-]+\.\w+/);
      const roleMatch = body.match(/Roles?:\s*([^\n]+)/i);
      return {
        email: emailMatch?.[0] || null,
        roles: roleMatch?.[1]?.trim() || null,
      };
    }),
    bodySnippet: pageContent.substring(0, 2000),
  };

  fs.writeFileSync(
    path.join(DIAG_DIR, 'page-state.json'),
    JSON.stringify(pageState, null, 2),
  );
  console.log(`Page state: Access Denied=${pageState.bodyContains.accessDenied}, URL=${pageUrl}`);

  // Capture the HTML for selector analysis
  const html = await page.content();
  fs.writeFileSync(path.join(DIAG_DIR, 'page-apis.html'), html);

  // Phase 3: Direct API test (bypass Portal UI)
  console.log('\n🔬 === PHASE 3: TEST DIRECT API CONTROL PLANE ===\n');

  // Try to extract token from various storage locations
  const tokenInfo = await page.evaluate(() => {
    const result: Record<string, any> = {};

    // Check localStorage
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key && (key.includes('token') || key.includes('auth') || key.includes('oidc') || key.includes('keycloak'))) {
        const val = localStorage.getItem(key) || '';
        result[`localStorage.${key}`] = val.length > 20 ? 'present (' + val.length + ' chars)' : val;
        // If it looks like a JWT, extract it
        if (val.includes('eyJ')) {
          const jwtMatch = val.match(/eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/);
          if (jwtMatch) {
            result['_extractedToken'] = jwtMatch[0];
          }
        }
        // Try parsing as JSON (Keycloak stores tokens in JSON objects)
        try {
          const parsed = JSON.parse(val);
          if (parsed.access_token) {
            result['_extractedToken'] = parsed.access_token;
          } else if (parsed.token) {
            result['_extractedToken'] = parsed.token;
          }
        } catch {}
      }
    }

    // Check sessionStorage
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (key) {
        const val = sessionStorage.getItem(key) || '';
        result[`sessionStorage.${key}`] = val.length > 20 ? 'present (' + val.length + ' chars)' : val;
        try {
          const parsed = JSON.parse(val);
          if (parsed.access_token) {
            result['_extractedToken'] = parsed.access_token;
          }
        } catch {}
      }
    }

    return result;
  });

  fs.writeFileSync(
    path.join(DIAG_DIR, 'token-storage.json'),
    JSON.stringify(tokenInfo, null, 2),
  );
  console.log(`Token storage keys: ${Object.keys(tokenInfo).filter(k => !k.startsWith('_')).join(', ')}`);

  const extractedToken = tokenInfo['_extractedToken'];

  if (extractedToken) {
    console.log('Token found — making direct API call...');

    // Decode the token for the report
    try {
      const parts = extractedToken.split('.');
      const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString());
      jwtDiag = {
        timestamp: new Date().toISOString(),
        requestUrl: 'extracted-from-storage',
        jwt: {
          header: JSON.parse(Buffer.from(parts[0], 'base64url').toString()),
          claims: {
            sub: payload.sub,
            aud: payload.aud,
            iss: payload.iss,
            exp: payload.exp,
            iat: payload.iat,
            azp: payload.azp,
            scope: payload.scope,
            preferred_username: payload.preferred_username,
            email: payload.email,
            realm_access: payload.realm_access,
            resource_access: payload.resource_access,
            tenant_id: payload.tenant_id || payload.stoa_tenant || null,
            groups: payload.groups || null,
          },
          full_payload: payload,
        },
      };
      fs.writeFileSync(
        path.join(DIAG_DIR, 'jwt-decoded.json'),
        JSON.stringify(jwtDiag, null, 2),
      );
      console.log(`🔑 JWT decoded from storage:`);
      console.log(`   sub: ${payload.sub}`);
      console.log(`   realm_access.roles: ${JSON.stringify(payload.realm_access?.roles)}`);
      console.log(`   scope: ${payload.scope}`);
    } catch (e: any) {
      console.error(`JWT decode failed: ${e.message}`);
    }

    // Direct API calls to test backend
    const endpoints = [
      '/v1/portal/apis',
      '/v1/apis',
      '/apis',
      '/health',
    ];

    for (const endpoint of endpoints) {
      try {
        const apiUrl = `${process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev'}${endpoint}`;
        const response = await page.request.fetch(apiUrl, {
          headers: {
            'Authorization': `Bearer ${extractedToken}`,
            'Content-Type': 'application/json',
          },
        });
        const status = response.status();
        let body: any;
        try { body = await response.json(); } catch { body = await response.text(); }

        console.log(`API ${endpoint}: ${status}`);

        fs.writeFileSync(
          path.join(DIAG_DIR, `api-direct-${endpoint.replace(/\//g, '_')}.json`),
          JSON.stringify({ url: apiUrl, status, body: typeof body === 'string' ? body.substring(0, 1000) : body }, null, 2),
        );
      } catch (e: any) {
        console.error(`API ${endpoint}: ERROR ${e.message}`);
      }
    }
  } else {
    console.warn('⚠️ No token found in localStorage/sessionStorage');

    // Try using page cookies directly (fetch with credentials)
    const apiViaSession = await page.evaluate(async (gatewayUrl: string) => {
      const endpoints = ['/v1/portal/apis', '/v1/apis', '/apis'];
      const results: Record<string, any> = {};
      for (const ep of endpoints) {
        try {
          const res = await fetch(`${gatewayUrl}${ep}`, { credentials: 'include' });
          let body: any;
          try { body = await res.json(); } catch { body = await res.text(); }
          results[ep] = { status: res.status, body: typeof body === 'string' ? body.substring(0, 500) : body };
        } catch (e: any) {
          results[ep] = { error: e.message };
        }
      }
      return results;
    }, process.env.STOA_GATEWAY_URL || 'https://api.gostoa.dev');

    fs.writeFileSync(
      path.join(DIAG_DIR, 'api-session-response.json'),
      JSON.stringify(apiViaSession, null, 2),
    );
  }

  // Also check: does the Portal make any XHR to the backend for /apis?
  // Look at the errors captured after navigating to /apis
  const apisErrors = errors.slice(errorsBeforeApis);
  console.log(`\nErrors captured during /apis navigation: ${apisErrors.length}`);
  apisErrors.forEach(e => console.log(`  ${e.status} ${e.url}`));

  // Close context to save HAR
  await context.close();
  await browser.close();

  // Phase 4: Compile diagnostic report
  console.log('\n📋 === PHASE 4: DIAGNOSTIC REPORT ===\n');

  const apisError = errors.find(e => e.url.includes('/apis') || e.url.includes('/api'));

  let diagnosis = 'UNKNOWN';
  let action = '';

  if (!jwtDiag) {
    diagnosis = 'JWT_ABSENT';
    action = 'Portal does not transmit JWT in Authorization headers. Check OIDC flow: Keycloak → Portal (redirect URI, client config).';
  } else if (!jwtDiag.jwt.claims.realm_access?.roles?.includes('viewer')) {
    diagnosis = 'JWT_MISSING_VIEWER_ROLE';
    action = `viewer role not in realm_access.roles. Present roles: ${JSON.stringify(jwtDiag.jwt.claims.realm_access?.roles)}. Assign viewer role to Alex in Keycloak.`;
  } else if (apisError?.wwwAuthenticate?.includes('insufficient_scope')) {
    diagnosis = 'KEYCLOAK_INSUFFICIENT_SCOPE';
    action = `Keycloak rejects with insufficient_scope. Current scope: "${jwtDiag.jwt.claims.scope}". Add required scope in Keycloak client.`;
  } else if (apisError?.responseBody?.includes('role') || apisError?.responseBody?.includes('permission')) {
    diagnosis = 'BACKEND_RBAC_GUARD';
    action = 'Control Plane rejects viewer role on /apis. Modify FastAPI endpoint guard to accept any authenticated user on catalog endpoint.';
  } else if (pageState.bodyContains.accessDenied && !pageState.wasRedirected) {
    // Check if the page itself shows "Access Denied" but URL is still /apis
    // This suggests a frontend route guard
    diagnosis = 'FRONTEND_ROUTE_GUARD';
    action = 'Portal React app shows Access Denied on /apis — this is a frontend route guard. Modify the ProtectedRoute/AuthGuard component to allow viewer role on /apis route.';
  } else if (pageState.wasRedirected) {
    diagnosis = 'FRONTEND_REDIRECT';
    action = `Portal redirects to ${pageState.redirectedTo} instead of showing /apis. Check React router ProtectedRoute configuration.`;
  } else {
    diagnosis = 'OTHER';
    action = 'Cause not automatically identified. Analyze files in test-results/diagnostic/ manually.';
  }

  // Check if it's specifically a frontend guard by looking at error details
  if (pageState.bodyContains.accessDenied && pageState.visibleUserInfo?.roles) {
    diagnosis = 'FRONTEND_ROUTE_GUARD';
    action = `Portal React app shows Access Denied for user with roles [${pageState.visibleUserInfo.roles}]. The /apis route guard is checking for roles beyond 'viewer'. Modify the route guard to allow viewer access to the catalog.`;
  }

  const report = `# 🔍 Diagnostic Report — CAB-1039
## Date: ${new Date().toISOString()}

## 🎯 Diagnosis

**Verdict: ${diagnosis}**

**Action required:** ${action}

## 📊 Evidence

### JWT Claims
${jwtDiag ? `
- **sub**: ${jwtDiag.jwt.claims.sub}
- **aud**: ${JSON.stringify(jwtDiag.jwt.claims.aud)}
- **iss**: ${jwtDiag.jwt.claims.iss}
- **azp**: ${jwtDiag.jwt.claims.azp}
- **scope**: ${jwtDiag.jwt.claims.scope}
- **realm_access.roles**: ${JSON.stringify(jwtDiag.jwt.claims.realm_access?.roles)}
- **resource_access keys**: ${JSON.stringify(Object.keys(jwtDiag.jwt.claims.resource_access || {}))}
- **tenant_id**: ${jwtDiag.jwt.claims.tenant_id}
- **groups**: ${JSON.stringify(jwtDiag.jwt.claims.groups)}
- **preferred_username**: ${jwtDiag.jwt.claims.preferred_username}
- **email**: ${jwtDiag.jwt.claims.email}
` : '⚠️ No JWT captured — Portal does not transmit Authorization header'}

### Network Errors (4xx/5xx)
${errors.length > 0 ? errors.map(e => `
- **${e.status}** ${e.url}
  - WWW-Authenticate: ${e.wwwAuthenticate || 'absent'}
  - Body: ${e.responseBody?.substring(0, 200) || 'empty'}
`).join('\n') : 'No network errors captured'}

### Page State after /apis
- **Final URL**: ${pageState.finalUrl}
- **Redirected**: ${pageState.wasRedirected ? 'YES → ' + pageState.redirectedTo : 'NO'}
- **Contains "Access Denied"**: ${pageState.bodyContains.accessDenied}
- **Contains "Forbidden"**: ${pageState.bodyContains.forbidden}
- **Contains "Permission"**: ${pageState.bodyContains.permission}
- **Visible user info**: ${JSON.stringify(pageState.visibleUserInfo)}

### Token Storage
${Object.keys(tokenInfo).filter(k => !k.startsWith('_')).map(k => `- ${k}: ${tokenInfo[k]}`).join('\n') || 'No token-related keys found'}

## 📁 Files

| File | Description |
|------|-------------|
| jwt-decoded.json | Full decoded JWT with all claims |
| errors.jsonl | All 4xx/5xx errors with headers |
| page-state.json | Page state after /apis navigation |
| page-apis.html | Full HTML of /apis page |
| token-storage.json | Token storage locations |
| session-cookies.json | Session cookies (metadata only) |
| network.har | Complete network trace |
| localStorage-keys.json | localStorage contents |
| screenshots/ | Step-by-step screenshots |

## ⏭️ Next Step

Based on verdict **${diagnosis}**: ${action}
`;

  fs.writeFileSync(path.join(DIAG_DIR, 'DIAGNOSTIC-REPORT.md'), report);
  console.log(report);
}

run().catch(e => {
  console.error('Diagnostic failed:', e);
  process.exit(1);
});
