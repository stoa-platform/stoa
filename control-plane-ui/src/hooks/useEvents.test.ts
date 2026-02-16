import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { useEvents } from './useEvents';

// Mock apiService
vi.mock('../services/api', () => ({
  apiService: {
    createEventSource: vi.fn(),
  },
}));

import { apiService } from '../services/api';
const mockCreateEventSource = vi.mocked(apiService.createEventSource);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client: queryClient }, children);
}

let mockEventSource: {
  onmessage: ((event: MessageEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  close: ReturnType<typeof vi.fn>;
};

beforeEach(() => {
  vi.clearAllMocks();
  mockEventSource = {
    onmessage: null,
    onerror: null,
    close: vi.fn(),
  };
  mockCreateEventSource.mockReturnValue(mockEventSource as unknown as EventSource);
});

describe('useEvents', () => {
  it('creates EventSource with correct params', () => {
    renderHook(() => useEvents({ tenantId: 'tenant-1', eventTypes: ['api-created'] }), {
      wrapper: createWrapper(),
    });

    expect(mockCreateEventSource).toHaveBeenCalledWith('tenant-1', ['api-created']);
  });

  it('does not create EventSource when disabled', () => {
    renderHook(() => useEvents({ tenantId: 'tenant-1', enabled: false }), {
      wrapper: createWrapper(),
    });

    expect(mockCreateEventSource).not.toHaveBeenCalled();
  });

  it('does not create EventSource when tenantId is empty', () => {
    renderHook(() => useEvents({ tenantId: '' }), { wrapper: createWrapper() });

    expect(mockCreateEventSource).not.toHaveBeenCalled();
  });

  it('calls onEvent handler when message received', () => {
    const onEvent = vi.fn();
    renderHook(() => useEvents({ tenantId: 'tenant-1', onEvent }), { wrapper: createWrapper() });

    const event = { type: 'api-created', data: {} };
    act(() => {
      mockEventSource.onmessage?.({
        data: JSON.stringify(event),
      } as MessageEvent);
    });

    expect(onEvent).toHaveBeenCalledWith(event);
  });

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() => useEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    unmount();
    expect(mockEventSource.close).toHaveBeenCalled();
  });

  it('provides close function', () => {
    const { result } = renderHook(() => useEvents({ tenantId: 'tenant-1' }), {
      wrapper: createWrapper(),
    });

    result.current.close();
    expect(mockEventSource.close).toHaveBeenCalled();
  });

  it('handles JSON parse errors gracefully', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderHook(() => useEvents({ tenantId: 'tenant-1' }), { wrapper: createWrapper() });

    act(() => {
      mockEventSource.onmessage?.({
        data: 'invalid-json',
      } as MessageEvent);
    });

    expect(consoleSpy).toHaveBeenCalledWith('Failed to parse event:', expect.any(Error));
    consoleSpy.mockRestore();
  });

  it('handles EventSource error event', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderHook(() => useEvents({ tenantId: 'tenant-1' }), { wrapper: createWrapper() });

    act(() => {
      mockEventSource.onerror?.(new Event('error'));
    });

    expect(consoleSpy).toHaveBeenCalledWith('EventSource error:', expect.any(Event));
    consoleSpy.mockRestore();
  });
});
