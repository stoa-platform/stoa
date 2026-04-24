/**
 * Pure helpers consumed by AuthContext. Kept in a separate file so
 * that AuthContext.tsx only exports React components (satisfies the
 * react-refresh/only-export-components rule).
 */

// P1-5: JWTs use base64url (alphabet `-`, `_`, no padding). `atob()` only
// accepts standard base64 (`+`, `/`, `=`) so payloads containing a `-` or
// `_` would throw `InvalidCharacterError`, the AuthContext catch would
// swallow it, and the user silently lost all permissions. We also decode
// via TextDecoder so UTF-8 claims (non-ASCII preferred_username, display
// name, etc.) survive.
export function decodeJwtPayload(token: string): unknown {
  const [, segment] = token.split('.');
  if (!segment) throw new Error('Invalid JWT — missing payload segment');
  const padded = segment + '='.repeat((4 - (segment.length % 4)) % 4);
  const base64 = padded.replace(/-/g, '+').replace(/_/g, '/');
  const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  return JSON.parse(new TextDecoder().decode(bytes));
}

/**
 * Match `/mcp-connectors/callback` under any Vite `base` config.
 *
 * P1-15: `startsWith('/mcp-connectors/callback')` broke when the app is
 * served under a subpath (e.g. `/console/`). It also matched lookalikes
 * such as `/mcp-connectors/callback-evil`; we now require either an
 * exact match or a strict `/`-separated subpath.
 *
 * `baseUrl` is injectable so tests can drive it without patching
 * `import.meta.env` (Vite replaces the default statically at build time).
 */
export function isMcpCallbackPath(
  pathname: string,
  baseUrl: string = import.meta.env.BASE_URL || '/',
): boolean {
  const base = baseUrl.replace(/\/+$/, '');
  const target = `${base}/mcp-connectors/callback`;
  return pathname === target || pathname.startsWith(`${target}/`);
}
