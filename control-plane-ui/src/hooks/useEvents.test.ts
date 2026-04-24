import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useEvents } from './useEvents';
import type { SseConnection, SseEvent, SseHandlers } from '../services/http';

// Mock the services/http barrel so we control openEventStream behavior.
const { mockOpenEventStream } = vi.hoisted(() => ({
  mockOpenEventStream: vi.fn(),
}));

vi.mock('../services/http', async () => {
  const actual = await vi.importActual<typeof import('../services/http')>('../services/http');
  return {
    ...actual,
    openEventStream: mockOpenEventStream,
  };
});

interface StreamHandle {
  handlers: SseHandlers;
  tenantId: string;
  eventTypes: string[] | undefined;
  connection: SseConnection;
  close: ReturnType<typeof vi.fn>;
}

let streams: StreamHandle[] = [];

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

beforeEach(() => {
  streams = [];
  mockOpenEventStream.mockImplementation(
    (tenantId: string, eventTypes: string[] | undefined, handlers: SseHandlers): SseConnection => {
      const close = vi.fn();
      const connection = { close };
      streams.push({ handlers, tenantId, eventTypes, connection, close });
      return connection;
    }
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('useEvents', () => {
  it('opens stream with correct params', () => {
    renderHook(() => useEvents({ tenantId: 'tenant-1', eventTypes: ['api-created'] }), {
      wrapper: createWrapper(),
    });

    expect(mockOpenEventStream).toHaveBeenCalledTimes(1);
    const call = mockOpenEventStream.mock.calls[0];
    expect(call[0]).toBe('tenant-1');
    expect(call[1]).toEqual(['api-created']);
  });

  it('does not open stream when disabled', () => {
    renderHook(() => useEvents({ tenantId: 'tenant-1', enabled: false }), {
      wrapper: createWrapper(),
    });

    expect(mockOpenEventStream).not.toHaveBeenCalled();
  });

  it('does not open stream when tenantId is empty', () => {
    renderHook(() => useEvents({ tenantId: '' }), { wrapper: createWrapper() });

    expect(mockOpenEventStream).not.toHaveBeenCalled();
  });

  it('calls onEvent handler when message received', () => {
    const onEvent = vi.fn();
    renderHook(() => useEvents({ tenantId: 'tenant-1', onEvent }), { wrapper: createWrapper() });

    const payload = { type: 'api-created', data: {} };
    act(() => {
      streams[0].handlers.onMessage({ data: JSON.stringify(payload) } as SseEvent);
    });

    expect(onEvent).toHaveBeenCalledWith(payload);
  });

  it('closes stream on unmount', () => {
    const { unmount } = renderHook(() => useEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    unmount();
    expect(streams[0].close).toHaveBeenCalled();
  });

  it('provides close function', () => {
    const { result } = renderHook(() => useEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    result.current.close();
    expect(streams[0].close).toHaveBeenCalled();
  });

  it('handles JSON parse errors gracefully', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderHook(() => useEvents({ tenantId: 'tenant-1' }), { wrapper: createWrapper() });

    act(() => {
      streams[0].handlers.onMessage({ data: 'invalid-json' } as SseEvent);
    });

    expect(consoleSpy).toHaveBeenCalledWith('Failed to parse event:', expect.any(Error));
    consoleSpy.mockRestore();
  });

  // Rev1 LOCK — P0-8 eventTypes stability
  it('stable across re-renders when eventTypes content unchanged (P0-8)', () => {
    const { rerender } = renderHook(({ types }) => useEvents({ tenantId: 't1', eventTypes: types }), {
      wrapper: createWrapper(),
      initialProps: { types: ['a', 'b'] },
    });

    // Re-render with a NEW array instance of the same content.
    rerender({ types: ['a', 'b'] });
    rerender({ types: ['a', 'b'] });

    // openEventStream called exactly once — no rebuild on content-equal rerenders.
    expect(mockOpenEventStream).toHaveBeenCalledTimes(1);
  });

  it('re-opens stream when eventTypes content changes', () => {
    const { rerender } = renderHook(({ types }) => useEvents({ tenantId: 't1', eventTypes: types }), {
      wrapper: createWrapper(),
      initialProps: { types: ['a', 'b'] },
    });

    rerender({ types: ['a', 'b', 'c'] });

    expect(mockOpenEventStream).toHaveBeenCalledTimes(2);
    // First stream must have been closed on cleanup.
    expect(streams[0].close).toHaveBeenCalled();
  });

  it('exposes isConnected=true after onOpen fires', () => {
    const { result } = renderHook(() => useEvents({ tenantId: 't1' }), {
      wrapper: createWrapper(),
    });

    expect(result.current.isConnected).toBe(false);

    act(() => {
      streams[0].handlers.onOpen?.();
    });

    expect(result.current.isConnected).toBe(true);
    expect(result.current.lastError).toBeNull();
  });

  it('exposes lastError and isConnected=false on onError', () => {
    const { result } = renderHook(() => useEvents({ tenantId: 't1' }), {
      wrapper: createWrapper(),
    });

    act(() => {
      streams[0].handlers.onOpen?.();
    });
    act(() => {
      streams[0].handlers.onError?.(new Error('boom'));
    });

    expect(result.current.isConnected).toBe(false);
    expect(result.current.lastError).toBeInstanceOf(Error);
  });

  it('handleEvent receives SseEvent shape (no MessageEvent cast) (Rev1)', () => {
    const onEvent = vi.fn();
    renderHook(() => useEvents({ tenantId: 't1', onEvent }), { wrapper: createWrapper() });

    const sseEvent: SseEvent = { data: JSON.stringify({ type: 'api-created' }), event: 'message', id: '1' };
    act(() => {
      streams[0].handlers.onMessage(sseEvent);
    });

    expect(onEvent).toHaveBeenCalledWith({ type: 'api-created' });
  });
});
