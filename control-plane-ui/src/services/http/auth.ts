/**
 * Auth token state for the HTTP layer.
 *
 * Module-scope storage is **intentional** and paired with the Keycloak
 * `sessionStorage` store wired in `src/main.tsx`. This means each browser
 * tab keeps its own token and performs its own silent renew — tabs do
 * NOT share refreshed tokens via BroadcastChannel or `storage` events.
 *
 * Rationale (P1-3, WONT-FIX by design): sessionStorage-per-tab bounds the
 * XSS blast radius — a script exfiltrating localStorage would leak all
 * live sessions at once; sessionStorage isolates one tab at a time.
 * Cross-tab token sync would partially re-open that surface and is not
 * worth the complexity for the UX gain (each tab refreshes naturally on
 * its own 401).
 *
 * Consequence: two tabs can briefly hold divergent tokens until each
 * tab's next 401 → refresh cycle. Acceptable under the audit.
 *
 * P2-7 (WONT-FIX): the getters, setters, enqueueRefresh and
 * drainRefreshQueue exports below are internals for files under
 * `src/services/http/` and the `services/api.ts` façade.
 * **Do not import them from consumer code** (pages, hooks, contexts).
 * Use the `apiService` façade for auth state mutations. Enforcement is
 * done at lint level via `no-restricted-imports` in `.eslintrc.cjs`
 * (see the P2-7 override for alias-aware glob patterns).
 * A runtime refactor (namespace class or IIFE closure) was considered but
 * rejected for a P2 — the risk of introducing a bug on the critical auth
 * path outweighs the encapsulation gain that the lint rule already buys.
 */
export type TokenRefresher = () => Promise<string | null>;

type QueueItem = {
  resolve: (token: string | null) => void;
  reject: (error: unknown) => void;
};

let authToken: string | null = null;
let tokenRefresher: TokenRefresher | null = null;
let isRefreshing = false;
let refreshQueue: QueueItem[] = [];

export function setAuthToken(token: string): void {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

export function clearAuthToken(): void {
  authToken = null;
}

export function setTokenRefresher(refresher: TokenRefresher): void {
  tokenRefresher = refresher;
}

export function getTokenRefresher(): TokenRefresher | null {
  return tokenRefresher;
}

export function getIsRefreshing(): boolean {
  return isRefreshing;
}

export function setIsRefreshing(value: boolean): void {
  isRefreshing = value;
}

export function enqueueRefresh(item: QueueItem): void {
  refreshQueue.push(item);
}

export function drainRefreshQueue(
  outcome: { resolveWith: string | null } | { rejectWith: unknown }
): void {
  if ('resolveWith' in outcome) {
    refreshQueue.forEach(({ resolve }) => resolve(outcome.resolveWith));
  } else {
    refreshQueue.forEach(({ reject }) => reject(outcome.rejectWith));
  }
  refreshQueue = [];
}
