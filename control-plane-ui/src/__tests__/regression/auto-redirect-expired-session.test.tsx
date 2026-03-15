/**
 * Regression test for auto-redirect on expired Keycloak session
 *
 * PR: #1706
 * Root cause: When a Keycloak session expires, the API returns 401. The
 *   tokenRefresher called signinSilent() which could succeed but return no
 *   access_token (session expired server-side). Without a redirect, the user
 *   was stuck in a broken state — authenticated UI but all API calls failing.
 *
 * Fix (AuthContext.tsx): When signinSilent() returns without a token, call
 *   signinRedirect() to send the user back to the Keycloak login page.
 *
 * Fix (api.ts): When the token refresher returns null (session expired),
 *   reject all queued requests so they don't hang indefinitely.
 *
 * Invariant: A 401 response must always result in either a successful token
 *   refresh + retry, or a redirect to the login page. The user must never be
 *   left in a state where API calls silently fail.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ---- ApiService 401 interceptor logic (extracted for unit testing) ----

type TokenRefresher = () => Promise<string | null>;

interface RefreshQueueItem {
  resolve: (token: string | null) => void;
  reject: (error: unknown) => void;
}

/**
 * Simulates the ApiService 401 interceptor behavior.
 * Returns the action taken: 'retried', 'queued', 'rejected', or 'passthrough'.
 */
async function simulate401Handler(opts: {
  status: number;
  isRetry: boolean;
  tokenRefresher: TokenRefresher | null;
  isRefreshing: boolean;
  refreshQueue: RefreshQueueItem[];
}): Promise<{ action: string; newToken?: string | null }> {
  const { status, isRetry, tokenRefresher, isRefreshing, refreshQueue } = opts;

  if (status === 401 && !isRetry && tokenRefresher) {
    if (isRefreshing) {
      return { action: 'queued' };
    }

    try {
      const newToken = await tokenRefresher();
      if (newToken) {
        // Token refreshed — retry the request
        refreshQueue.forEach(({ resolve }) => resolve(newToken));
        refreshQueue.length = 0;
        return { action: 'retried', newToken };
      }
      // Token refresh returned null — session expired
      refreshQueue.forEach(({ reject }) => reject(new Error('Session expired')));
      refreshQueue.length = 0;
      return { action: 'rejected', newToken: null };
    } catch (refreshError) {
      refreshQueue.forEach(({ reject }) => reject(refreshError));
      refreshQueue.length = 0;
      return { action: 'rejected', newToken: null };
    }
  }

  return { action: 'passthrough' };
}

// ---- Token refresher logic (mirrors AuthContext.tsx) ----

function createTokenRefresher(oidcMock: {
  signinSilent: () => Promise<{ access_token?: string } | null>;
  signinRedirect: () => void;
}): TokenRefresher {
  return async () => {
    try {
      const renewed = await oidcMock.signinSilent();
      if (renewed?.access_token) {
        return renewed.access_token;
      }
      // Silent renew succeeded but no token — session expired
      oidcMock.signinRedirect();
      return null;
    } catch {
      oidcMock.signinRedirect();
      return null;
    }
  };
}

describe('regression/auto-redirect-expired-session', () => {
  let signinSilent: ReturnType<typeof vi.fn>;
  let signinRedirect: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    signinSilent = vi.fn();
    signinRedirect = vi.fn();
  });

  describe('AuthContext tokenRefresher — redirect on expired session', () => {
    it('returns new token when signinSilent succeeds with a token', async () => {
      signinSilent.mockResolvedValue({ access_token: 'new-jwt-token' });
      const refresher = createTokenRefresher({ signinSilent, signinRedirect });

      const result = await refresher();

      expect(result).toBe('new-jwt-token');
      expect(signinRedirect).not.toHaveBeenCalled();
    });

    it('redirects to login when signinSilent returns no token (session expired)', async () => {
      // This is the core regression case: signinSilent resolves but without a token
      signinSilent.mockResolvedValue({ access_token: undefined });
      const refresher = createTokenRefresher({ signinSilent, signinRedirect });

      const result = await refresher();

      expect(result).toBeNull();
      expect(signinRedirect).toHaveBeenCalledTimes(1);
    });

    it('redirects to login when signinSilent returns null', async () => {
      signinSilent.mockResolvedValue(null);
      const refresher = createTokenRefresher({ signinSilent, signinRedirect });

      const result = await refresher();

      expect(result).toBeNull();
      expect(signinRedirect).toHaveBeenCalledTimes(1);
    });

    it('redirects to login when signinSilent throws (network error, etc.)', async () => {
      signinSilent.mockRejectedValue(new Error('Network error'));
      const refresher = createTokenRefresher({ signinSilent, signinRedirect });

      const result = await refresher();

      expect(result).toBeNull();
      expect(signinRedirect).toHaveBeenCalledTimes(1);
    });
  });

  describe('ApiService 401 interceptor — queue cleanup on expired session', () => {
    it('retries the request when token refresh succeeds', async () => {
      const refresher = vi.fn().mockResolvedValue('fresh-token');
      const queue: RefreshQueueItem[] = [];

      const result = await simulate401Handler({
        status: 401,
        isRetry: false,
        tokenRefresher: refresher,
        isRefreshing: false,
        refreshQueue: queue,
      });

      expect(result.action).toBe('retried');
      expect(result.newToken).toBe('fresh-token');
    });

    it('rejects queued requests when token refresh returns null (session expired)', async () => {
      const refresher = vi.fn().mockResolvedValue(null);
      const queueReject = vi.fn();
      const queue: RefreshQueueItem[] = [
        { resolve: vi.fn(), reject: queueReject },
        { resolve: vi.fn(), reject: queueReject },
      ];

      const result = await simulate401Handler({
        status: 401,
        isRetry: false,
        tokenRefresher: refresher,
        isRefreshing: false,
        refreshQueue: queue,
      });

      expect(result.action).toBe('rejected');
      expect(queueReject).toHaveBeenCalledTimes(2);
      expect(queue).toHaveLength(0);
    });

    it('rejects queued requests when token refresh throws', async () => {
      const refresher = vi.fn().mockRejectedValue(new Error('Refresh failed'));
      const queueReject = vi.fn();
      const queue: RefreshQueueItem[] = [{ resolve: vi.fn(), reject: queueReject }];

      const result = await simulate401Handler({
        status: 401,
        isRetry: false,
        tokenRefresher: refresher,
        isRefreshing: false,
        refreshQueue: queue,
      });

      expect(result.action).toBe('rejected');
      expect(queueReject).toHaveBeenCalledTimes(1);
      expect(queue).toHaveLength(0);
    });

    it('does not intercept non-401 errors', async () => {
      const refresher = vi.fn();

      const result = await simulate401Handler({
        status: 403,
        isRetry: false,
        tokenRefresher: refresher,
        isRefreshing: false,
        refreshQueue: [],
      });

      expect(result.action).toBe('passthrough');
      expect(refresher).not.toHaveBeenCalled();
    });

    it('does not retry if already retried (prevents infinite loop)', async () => {
      const refresher = vi.fn();

      const result = await simulate401Handler({
        status: 401,
        isRetry: true,
        tokenRefresher: refresher,
        isRefreshing: false,
        refreshQueue: [],
      });

      expect(result.action).toBe('passthrough');
      expect(refresher).not.toHaveBeenCalled();
    });

    it('queues request if another refresh is already in progress', async () => {
      const refresher = vi.fn();

      const result = await simulate401Handler({
        status: 401,
        isRetry: false,
        tokenRefresher: refresher,
        isRefreshing: true,
        refreshQueue: [],
      });

      expect(result.action).toBe('queued');
      expect(refresher).not.toHaveBeenCalled();
    });
  });

  describe('end-to-end: 401 with expired session triggers redirect', () => {
    it('401 → signinSilent fails → signinRedirect called + queued requests rejected', async () => {
      // Wire up the full chain: AuthContext tokenRefresher → ApiService interceptor
      signinSilent.mockResolvedValue(null); // Session expired
      const refresher = createTokenRefresher({ signinSilent, signinRedirect });

      const queueReject = vi.fn();
      const queue: RefreshQueueItem[] = [{ resolve: vi.fn(), reject: queueReject }];

      const result = await simulate401Handler({
        status: 401,
        isRetry: false,
        tokenRefresher: refresher,
        isRefreshing: false,
        refreshQueue: queue,
      });

      expect(result.action).toBe('rejected');
      expect(signinRedirect).toHaveBeenCalledTimes(1);
      expect(queueReject).toHaveBeenCalledTimes(1);
      expect(queue).toHaveLength(0);
    });
  });
});
