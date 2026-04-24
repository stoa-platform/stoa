/**
 * Tracks whether the app is in the middle of an auth redirect
 * (e.g. `oidc.signinRedirect()` awaiting navigation).
 *
 * While the flag is set, `applyFriendlyErrorMessage` skips decorating
 * rejected errors so the UI does not flash a tech error message between
 * the moment the redirect is initiated and the moment the browser
 * actually unloads the current page (P1-16).
 *
 * The flag has a TTL watchdog: if `signinRedirect()` never completes
 * (Keycloak down, navigation cancelled, etc.), the flag resets itself
 * so later errors surface normally — we never stay in "silence forever"
 * mode. The default TTL is 30 s (generous upper bound for browser
 * navigation).
 */

const DEFAULT_TTL_MS = 30_000;

let redirecting = false;
let ttlTimer: ReturnType<typeof setTimeout> | undefined;

export function markRedirecting(ttlMs: number = DEFAULT_TTL_MS): void {
  redirecting = true;
  if (ttlTimer) clearTimeout(ttlTimer);
  ttlTimer = setTimeout(() => {
    redirecting = false;
    ttlTimer = undefined;
  }, ttlMs);
}

export function isRedirecting(): boolean {
  return redirecting;
}

export function resetRedirecting(): void {
  redirecting = false;
  if (ttlTimer) {
    clearTimeout(ttlTimer);
    ttlTimer = undefined;
  }
}
