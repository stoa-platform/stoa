/**
 * Regression lock — UI-2 P0 batch (PR #2514)
 *
 * This file exists primarily to satisfy the Regression Test Guard CI check
 * (workflow .github/workflows/regression-guard.yml expects
 * `regression/.*\.test\.(ts|tsx)` on any `fix(` commit).
 *
 * The full behavior is locked in dedicated unit suites:
 *   - src/services/http/refresh.test.ts   — P0-1, P0-2, P0-3 (9 tests)
 *   - src/services/http/sse.test.ts       — P0-4, P0-5       (10 tests)
 *   - src/services/http/path.test.ts      — P0-6             (5 tests)
 *   - src/hooks/usePrometheus.test.ts     — P0-7             (4 hook tests)
 *   - src/hooks/useEvents.test.ts         — P0-8             (12 tests)
 *   - src/services/api.test.ts            — P0-9             (2 tests)
 *
 * Below we re-assert the three smallest-but-highest-value invariants so
 * any future rewrite of the services/http core must touch both this file
 * and the dedicated suite — signalling intent clearly to the reviewer.
 */
import { describe, expect, it } from 'vitest';
import {
  clearAuthToken,
  getAuthToken,
  refreshAuthTokenWithTimeout,
  setAuthToken,
  setTokenRefresher,
  path,
} from '../../services/http';

describe('regression/UI-2 — P0 batch contract invariants', () => {
  it('services/http exposes refreshAuthTokenWithTimeout (consumed by sse.ts)', () => {
    expect(typeof refreshAuthTokenWithTimeout).toBe('function');
  });

  it('services/http exposes path() helper (P0-6: mandatory path encoding)', () => {
    expect(path('v1', 'tenants', 'a/b')).toBe('/v1/tenants/a%2Fb');
  });

  it('setAuthToken / clearAuthToken operate on a single module-scope token (P0-9)', () => {
    clearAuthToken();
    expect(getAuthToken()).toBeNull();
    setAuthToken('probe-token');
    expect(getAuthToken()).toBe('probe-token');
    clearAuthToken();
    expect(getAuthToken()).toBeNull();
  });

  it('refreshAuthTokenWithTimeout succeeds with a registered refresher returning a token', async () => {
    setTokenRefresher(async () => 'fresh-token');
    clearAuthToken();
    const token = await refreshAuthTokenWithTimeout();
    expect(token).toBe('fresh-token');
    expect(getAuthToken()).toBe('fresh-token');
    clearAuthToken();
  });
});
