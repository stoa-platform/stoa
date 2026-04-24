/**
 * Real-code regression lock for services/http/refresh.ts.
 *
 * These tests import installRefreshInterceptor + refreshAuthTokenWithTimeout
 * directly and drive them through a real axios instance with a custom adapter.
 * No logic simulation — any drift in refresh.ts will break here.
 *
 * Locks: P0-1 (_retry propagation), P0-2 (null/error clear auth), P0-3 (timeout).
 */
import axios, { type AxiosAdapter, type AxiosError, type AxiosResponse } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  clearAuthToken,
  getAuthToken,
  setAuthToken,
  setTokenRefresher,
  type TokenRefresher,
} from './auth';
import { installRefreshInterceptor, refreshAuthTokenWithTimeout } from './refresh';

// ---- helpers -------------------------------------------------------------

type AdapterBehavior = (config: Parameters<AxiosAdapter>[0]) => Promise<AxiosResponse>;

function makeInstance(adapter: AdapterBehavior) {
  const instance = axios.create({ adapter });
  installRefreshInterceptor(instance);
  return instance;
}

function ok(config: Parameters<AxiosAdapter>[0], data: unknown = {}): AxiosResponse {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  } as AxiosResponse;
}

function fail(config: Parameters<AxiosAdapter>[0], status = 401): Promise<never> {
  const response = {
    data: {},
    status,
    statusText: 'Unauthorized',
    headers: {},
    config,
  } as AxiosResponse;
  const err = new Error(`Request failed with status code ${status}`) as AxiosError;
  err.response = response;
  err.config = config;
  err.isAxiosError = true;
  return Promise.reject(err);
}

// Reset auth module-scope state between tests.
function resetAuthModule() {
  clearAuthToken();
  // setTokenRefresher(null as unknown as TokenRefresher) would cast — clear via new fn.
  setTokenRefresher((async () => null) as TokenRefresher);
}

beforeEach(() => {
  resetAuthModule();
});

afterEach(() => {
  vi.useRealTimers();
  clearAuthToken();
});

// ---- tests ---------------------------------------------------------------

describe('installRefreshInterceptor', () => {
  it('401 solo: refresh + retry succeeds with new token', async () => {
    const refresher = vi.fn<TokenRefresher>(async () => 'new-token');
    setTokenRefresher(refresher);

    let call = 0;
    const instance = makeInstance(async (config) => {
      call++;
      if (call === 1) return fail(config, 401);
      return ok(config, { ok: true });
    });

    const res = await instance.get('/v1/thing');
    expect(res.data).toEqual({ ok: true });
    expect(refresher).toHaveBeenCalledTimes(1);
    expect(getAuthToken()).toBe('new-token');
  });

  it('parallel 401s: single refresh call, queue replays all with new token', async () => {
    const refresher = vi.fn<TokenRefresher>(async () => {
      await new Promise((r) => setTimeout(r, 10));
      return 'new-token';
    });
    setTokenRefresher(refresher);

    const sawAuthHeader: string[] = [];
    const instance = makeInstance(async (config) => {
      const auth = (config.headers?.Authorization as string | undefined) ?? '';
      if (!(config as { _retry?: boolean })._retry) {
        return fail(config, 401);
      }
      sawAuthHeader.push(auth);
      return ok(config, { path: config.url });
    });

    const [a, b, c] = await Promise.all([
      instance.get('/v1/a'),
      instance.get('/v1/b'),
      instance.get('/v1/c'),
    ]);
    expect(a.data).toEqual({ path: '/v1/a' });
    expect(b.data).toEqual({ path: '/v1/b' });
    expect(c.data).toEqual({ path: '/v1/c' });
    expect(refresher).toHaveBeenCalledTimes(1);
    expect(sawAuthHeader.every((h) => h === 'Bearer new-token')).toBe(true);
  });

  it('queued request replay sets _retry flag to prevent cascade refresh (P0-1)', async () => {
    // Scenario: 2 requests trigger a refresh. After successful refresh both
    // replay. On replay one of them receives 401 again. That second 401 must
    // NOT trigger a new refresh (because _retry is now true).
    const refresher = vi.fn<TokenRefresher>(async () => {
      await new Promise((r) => setTimeout(r, 5));
      return 'new-token';
    });
    setTokenRefresher(refresher);

    let callCount = 0;
    const instance = makeInstance(async (config) => {
      callCount++;
      const retry = (config as { _retry?: boolean })._retry === true;
      // Always fail requests to /v1/broken; success on /v1/ok after refresh.
      if (config.url === '/v1/broken') return fail(config, 401);
      if (retry) return ok(config, { ok: true });
      return fail(config, 401);
    });

    const okReq = instance.get('/v1/ok');
    const brokenReq = instance.get('/v1/broken').catch((e) => e);
    const [okRes, brokenRes] = await Promise.all([okReq, brokenReq]);

    expect(okRes.data).toEqual({ ok: true });
    expect(brokenRes).toBeInstanceOf(Error);
    // LOCK: refresher called exactly once — the second 401 on /v1/broken
    // must NOT cascade into another refresh.
    expect(refresher).toHaveBeenCalledTimes(1);
    expect(callCount).toBeGreaterThanOrEqual(3); // initial broken, initial ok, broken retry
  });

  it('null token from refresher clears authToken and rejects with original error (P0-2)', async () => {
    setAuthToken('stale-token');
    const refresher = vi.fn<TokenRefresher>(async () => null);
    setTokenRefresher(refresher);

    const instance = makeInstance(async (config) => fail(config, 401));

    await expect(instance.get('/v1/thing')).rejects.toBeInstanceOf(Error);
    expect(getAuthToken()).toBeNull();
    expect(refresher).toHaveBeenCalledTimes(1);
  });

  it('refresh error (throw) clears authToken and rejects queue (P0-2)', async () => {
    setAuthToken('stale-token');
    const refresher = vi.fn<TokenRefresher>(async () => {
      throw new Error('network down');
    });
    setTokenRefresher(refresher);

    const instance = makeInstance(async (config) => fail(config, 401));

    await expect(instance.get('/v1/thing')).rejects.toThrow('network down');
    expect(getAuthToken()).toBeNull();
  });

  it('refresh hang > timeout clears authToken and rejects (P0-3)', async () => {
    vi.useFakeTimers();
    setAuthToken('stale-token');
    const refresher = vi.fn<TokenRefresher>(
      () => new Promise(() => undefined) as Promise<string | null>
    );
    setTokenRefresher(refresher);

    // Override timeout to 100ms via config mutation — refresh.ts reads this
    // dynamically per-call (Rev1 #3).
    const { config } = await import('../../config');
    const originalTimeout = config.auth.refreshTimeoutMs;
    config.auth.refreshTimeoutMs = 100;

    const instance = makeInstance(async (cfg) => fail(cfg, 401));
    const pending = instance.get('/v1/thing');
    const rejected = expect(pending).rejects.toThrow(/timeout after 100ms/);

    await vi.advanceTimersByTimeAsync(150);
    await rejected;

    expect(getAuthToken()).toBeNull();
    config.auth.refreshTimeoutMs = originalTimeout;
  });

  it('401 after successful refresh replay does not trigger new refresh (P0-1 symmetric)', async () => {
    const refresher = vi.fn<TokenRefresher>(async () => 'new-token');
    setTokenRefresher(refresher);

    const instance = makeInstance(async (config) => {
      // Always 401, regardless of retry flag.
      return fail(config, 401);
    });

    await expect(instance.get('/v1/thing')).rejects.toBeInstanceOf(Error);
    // Exactly one refresh — the retry 401 should not cascade.
    expect(refresher).toHaveBeenCalledTimes(1);
  });
});

describe('refreshWithTimeout — timer cleanup (Rev1 #2)', () => {
  it('successful refresh clears the pending timeout timer', async () => {
    vi.useFakeTimers();
    const refresher = vi.fn<TokenRefresher>(async () => 'new-token');
    setTokenRefresher(refresher);

    const p = refreshAuthTokenWithTimeout();
    // Flush microtasks so refresher resolves before the 30s timeout fires.
    await vi.advanceTimersByTimeAsync(0);
    const token = await p;

    expect(token).toBe('new-token');
    // If the timer leaked, getTimerCount() would be >=1 after success.
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('refreshAuthTokenWithTimeout — helper exposed for SSE (C4)', () => {
  it('coalesces concurrent calls via the shared queue (single refresher invocation)', async () => {
    const refresher = vi.fn<TokenRefresher>(async () => {
      await new Promise((r) => setTimeout(r, 10));
      return 'new-token';
    });
    setTokenRefresher(refresher);

    const [a, b, c] = await Promise.all([
      refreshAuthTokenWithTimeout(),
      refreshAuthTokenWithTimeout(),
      refreshAuthTokenWithTimeout(),
    ]);
    expect(a).toBe('new-token');
    expect(b).toBe('new-token');
    expect(c).toBe('new-token');
    expect(refresher).toHaveBeenCalledTimes(1);
    expect(getAuthToken()).toBe('new-token');
  });

  // P2-2 WONT-FIX lock: retry replays the same AxiosRequestConfig reference
  // without clone. With Axios defaults, already-serialized JSON data is stable
  // across replay — this test guards against a future change where a custom
  // transformRequest would accidentally double-encode the payload.
  it('retry does not double-encode default JSON body (P2-2 WONT-FIX)', async () => {
    const refresher = vi.fn<TokenRefresher>(async () => 'new-token');
    setTokenRefresher(refresher);

    const observedBodies: unknown[] = [];
    let call = 0;
    const instance = makeInstance(async (config) => {
      observedBodies.push(config.data);
      call++;
      if (call === 1) return fail(config, 401);
      return ok(config, { ok: true });
    });

    const body = { foo: 1, bar: 'baz' };
    const res = await instance.post('/v1/thing', body);
    expect(res.data).toEqual({ ok: true });
    expect(refresher).toHaveBeenCalledTimes(1);

    // Both calls saw the same serialized body (stable JSON string, not
    // double-encoded). With axios defaults, transformRequest serializes once
    // and the same string is replayed verbatim.
    expect(observedBodies.length).toBe(2);
    expect(observedBodies[0]).toBe(observedBodies[1]);
    const asString = typeof observedBodies[0] === 'string' ? observedBodies[0] : JSON.stringify(observedBodies[0]);
    expect(JSON.parse(asString)).toEqual(body);
  });
});
