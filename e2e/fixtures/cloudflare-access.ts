/**
 * Cloudflare Access service-token headers for E2E runs.
 *
 * When CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET are set, the two
 * CF-Access-Client-* headers are added only to requests whose origin is the
 * portal or the console. Other origins (identity provider, CDNs, third parties)
 * never receive them, including through redirects. Values are never logged.
 *
 * playwright.config.ts turns traces and videos off when the secret is set, so
 * the headers cannot end up in uploaded reports.
 */

import type { BrowserContext } from '@playwright/test';

const PROTECTED_URLS = [
  process.env.STOA_PORTAL_URL || 'https://portal.gostoa.dev',
  process.env.STOA_CONSOLE_URL || 'https://console.gostoa.dev',
];

function protectedOrigins(): Set<string> {
  const origins = new Set<string>();
  for (const value of PROTECTED_URLS) {
    try {
      origins.add(new URL(value).origin);
    } catch {
      // Ignore malformed URLs; the tests will report the navigation error.
    }
  }
  return origins;
}

export async function installCloudflareAccessHeaders(context: BrowserContext): Promise<void> {
  const clientId = process.env.CF_ACCESS_CLIENT_ID;
  const clientSecret = process.env.CF_ACCESS_CLIENT_SECRET;
  if (!clientId || !clientSecret) return;

  const origins = protectedOrigins();
  await context.route(
    (url) => origins.has(url.origin),
    async (route) => {
      // Fetch without following redirects so the headers never travel to another
      // origin: the browser follows any 30x itself, and the new request goes
      // through this origin check again.
      const response = await route.fetch({
        headers: {
          ...route.request().headers(),
          'CF-Access-Client-Id': clientId,
          'CF-Access-Client-Secret': clientSecret,
        },
        maxRedirects: 0,
      });
      await route.fulfill({ response });
    },
  );
}
