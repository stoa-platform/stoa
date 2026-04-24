/**
 * Regression lock for services/http/sse.ts.
 * - authFetch re-reads the auth token on each call (P0-5)
 * - URL encoding via path() (P0-6 double-guard)
 * - onopen(401) triggers refreshAuthTokenWithTimeout before retry (C4 Rev1)
 * - close() aborts the connection
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setAuthToken, clearAuthToken } from './auth';

// Mock fetchEventSource so we can inspect its init (including custom fetch).
const { mockFetchEventSource } = vi.hoisted(() => ({
  mockFetchEventSource: vi.fn(),
}));
vi.mock('@microsoft/fetch-event-source', () => ({
  fetchEventSource: mockFetchEventSource,
}));

// Mock refresh helper — lets us assert it's called on 401.
const { mockRefresh } = vi.hoisted(() => ({ mockRefresh: vi.fn() }));
vi.mock('./refresh', async () => {
  const actual = await vi.importActual<typeof import('./refresh')>('./refresh');
  return {
    ...actual,
    refreshAuthTokenWithTimeout: mockRefresh,
  };
});

import { openEventStream } from './sse';

const globalFetch = globalThis.fetch;

beforeEach(() => {
  clearAuthToken();
  mockFetchEventSource.mockReset();
  mockRefresh.mockReset();
  mockFetchEventSource.mockResolvedValue(undefined);
});

afterEach(() => {
  globalThis.fetch = globalFetch;
  clearAuthToken();
});

function lastInit() {
  const call = mockFetchEventSource.mock.calls[0];
  expect(call).toBeTruthy();
  return { url: call[0] as string, init: call[1] as Parameters<typeof import('@microsoft/fetch-event-source').fetchEventSource>[1] };
}

describe('openEventStream — authFetch', () => {
  it('injects Authorization Bearer header from getAuthToken on first call', async () => {
    setAuthToken('tok-1');
    const spy = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    globalThis.fetch = spy as unknown as typeof fetch;

    openEventStream('tenant-a', undefined, { onMessage: () => {} });

    const { init } = lastInit();
    // Invoke authFetch to verify it reads the current token.
    await init!.fetch!('https://example.test/', { method: 'GET' });

    expect(spy).toHaveBeenCalled();
    const headersArg = spy.mock.calls[0][1].headers as Headers;
    expect(headersArg.get('Authorization')).toBe('Bearer tok-1');
  });

  it('re-reads token on subsequent authFetch calls (P0-5)', async () => {
    setAuthToken('tok-1');
    const spy = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    globalThis.fetch = spy as unknown as typeof fetch;

    openEventStream('tenant-a', undefined, { onMessage: () => {} });
    const { init } = lastInit();

    await init!.fetch!('https://example.test/', {});
    // Simulate Keycloak silent renew updating the token between retries.
    setAuthToken('tok-2');
    await init!.fetch!('https://example.test/', {});

    const firstHeaders = spy.mock.calls[0][1].headers as Headers;
    const secondHeaders = spy.mock.calls[1][1].headers as Headers;
    expect(firstHeaders.get('Authorization')).toBe('Bearer tok-1');
    expect(secondHeaders.get('Authorization')).toBe('Bearer tok-2');
  });

  it('deletes Authorization when no token is set', async () => {
    const spy = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    globalThis.fetch = spy as unknown as typeof fetch;

    openEventStream('tenant-a', undefined, { onMessage: () => {} });
    const { init } = lastInit();

    await init!.fetch!('https://example.test/', { headers: { Authorization: 'Bearer stale' } });

    const headersArg = spy.mock.calls[0][1].headers as Headers;
    expect(headersArg.get('Authorization')).toBeNull();
  });
});

describe('openEventStream — URL & lifecycle', () => {
  it('URL-encodes tenantId via path()', () => {
    openEventStream('a/b', undefined, { onMessage: () => {} });
    const { url } = lastInit();
    expect(url).toContain('/v1/events/stream/a%2Fb');
  });

  it('appends event_types query when provided', () => {
    openEventStream('t1', ['api-created', 'deploy-success'], { onMessage: () => {} });
    const { url } = lastInit();
    // URLSearchParams encodes "," to "%2C" in toString(); the backend decodes it back.
    expect(url).toMatch(/\?event_types=api-created(%2C|,)deploy-success$/);
  });

  it('close() aborts the underlying signal', () => {
    const conn = openEventStream('t1', undefined, { onMessage: () => {} });
    const { init } = lastInit();
    expect(init!.signal!.aborted).toBe(false);
    conn.close();
    expect(init!.signal!.aborted).toBe(true);
  });
});

describe('openEventStream — onopen 401 triggers refresh (Rev1 lock)', () => {
  it('calls refreshAuthTokenWithTimeout and throws RetriableError on 401', async () => {
    mockRefresh.mockResolvedValue('new-token');
    openEventStream('t1', undefined, { onMessage: () => {} });
    const { init } = lastInit();

    const response = new Response('', { status: 401 });
    await expect(init!.onopen!(response)).rejects.toBeInstanceOf(Error);
    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it('throws FatalError (stops retry) when refresh fails', async () => {
    mockRefresh.mockRejectedValue(new Error('refresh failed'));
    openEventStream('t1', undefined, { onMessage: () => {} });
    const { init } = lastInit();

    const response = new Response('', { status: 401 });
    await expect(init!.onopen!(response)).rejects.toThrow(/SSE auth refresh failed/);
  });

  it('fires onOpen callback on 2xx response', async () => {
    const onOpen = vi.fn();
    openEventStream('t1', undefined, { onMessage: () => {}, onOpen });
    const { init } = lastInit();

    await init!.onopen!(new Response('', { status: 200 }));
    expect(onOpen).toHaveBeenCalled();
  });

  it('throws FatalError on 4xx (non-401)', async () => {
    openEventStream('t1', undefined, { onMessage: () => {} });
    const { init } = lastInit();

    await expect(init!.onopen!(new Response('', { status: 404 }))).rejects.toThrow(
      /SSE rejected: 404/
    );
  });
});
