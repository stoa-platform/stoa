/**
 * Regression lock — UI-2 P2 batch (PR #2521)
 *
 * This file exists primarily to satisfy the Regression Test Guard CI check
 * (workflow .github/workflows/regression-guard.yml expects
 * `regression/.*\.test\.(ts|tsx)` on any `fix(` PR).
 *
 * The full behavior is locked in dedicated suites:
 *   - src/services/http/interceptors.test.ts  — P2-1
 *   - src/services/http/refresh.test.ts       — P2-2 canary
 *   - src/hooks/useServiceHealth.test.ts      — P2-5, P2-6
 *   - src/hooks/useEvents.test.ts             — P2-8, P2-9
 *
 * Below we re-assert the smallest-but-highest-value invariants so a future
 * rewrite of these surfaces must touch both this file and the dedicated
 * suites — signalling intent clearly to the reviewer.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useServiceHealth } from '../../hooks/useServiceHealth';
import { useEvents } from '../../hooks/useEvents';
import type { SseConnection, SseEvent, SseHandlers } from '../../services/http';

const { mockOpenEventStream } = vi.hoisted(() => ({
  mockOpenEventStream: vi.fn(),
}));

vi.mock('../../services/http', async () => {
  const actual = await vi.importActual<typeof import('../../services/http')>(
    '../../services/http'
  );
  return {
    ...actual,
    openEventStream: mockOpenEventStream,
  };
});

interface StreamHandle {
  handlers: SseHandlers;
  close: ReturnType<typeof vi.fn>;
}

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe('regression/UI-2 — P2 batch contract invariants', () => {
  let streams: StreamHandle[] = [];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
    Object.defineProperty(window, 'location', {
      value: { origin: 'http://localhost:3000' },
      writable: true,
    });
    streams = [];
    mockOpenEventStream.mockImplementation(
      (_tenantId: string, _eventTypes: string[] | undefined, handlers: SseHandlers): SseConnection => {
        const close = vi.fn();
        streams.push({ handlers, close });
        return { close };
      }
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('unmount abort stays silent instead of flipping service health to unavailable (P2-5)', async () => {
    mockFetch.mockImplementation(
      (_url: string, init: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          init.signal.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'));
          });
        })
    );

    const { result, unmount } = renderHook(() => useServiceHealth('https://example.com/health'));
    expect(result.current.status).toBe('checking');

    unmount();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(result.current.status).toBe('checking');
  });

  it('timeout abort still marks the service unavailable (P2-6)', async () => {
    vi.useFakeTimers();
    mockFetch.mockImplementation(
      (_url: string, init: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          init.signal.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'));
          });
        })
    );

    const { result } = renderHook(() => useServiceHealth('https://example.com/health'));
    expect(result.current.status).toBe('checking');

    await vi.advanceTimersByTimeAsync(5500);
    vi.useRealTimers();

    await waitFor(() => expect(result.current.status).toBe('unavailable'));
  });

  it('drops unknown SSE event types before they reach consumers (P2-8)', () => {
    const onEvent = vi.fn();
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(QueryClientProvider, { client: queryClient }, children);

    renderHook(() => useEvents({ tenantId: 'tenant-1', onEvent }), { wrapper });

    act(() => {
      streams[0].handlers.onMessage({
        data: JSON.stringify({ type: 'totally-unknown-event', payload: 1 }),
      } as SseEvent);
    });

    expect(onEvent).not.toHaveBeenCalled();
  });
});
