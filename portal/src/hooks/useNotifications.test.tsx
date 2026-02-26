import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useNotifications,
  useUnreadCount,
  useMarkAsRead,
  useMarkAllAsRead,
} from './useNotifications';

vi.mock('../services/notifications', () => ({
  notificationsService: {
    getNotifications: vi.fn(),
    getUnreadCount: vi.fn(),
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { notificationsService } from '../services/notifications';
import { useAuth } from '../contexts/AuthContext';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

const mockNotifications = {
  items: [
    { id: 'n1', title: 'New subscription', read: false },
    { id: 'n2', title: 'API updated', read: true },
  ],
  total: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue({
    isAuthenticated: true,
    accessToken: 'mock-token',
  } as any);
});

describe('useNotifications', () => {
  it('fetches notifications when authenticated', async () => {
    vi.mocked(notificationsService.getNotifications).mockResolvedValue(mockNotifications as any);

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockNotifications);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('handles API error', async () => {
    vi.mocked(notificationsService.getNotifications).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useNotifications(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useUnreadCount', () => {
  it('fetches unread count when authenticated', async () => {
    vi.mocked(notificationsService.getUnreadCount).mockResolvedValue(5);

    const { result } = renderHook(() => useUnreadCount(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe(5);
  });

  it('does not fetch when not authenticated', () => {
    vi.mocked(useAuth).mockReturnValue({
      isAuthenticated: false,
      accessToken: null,
    } as any);

    const { result } = renderHook(() => useUnreadCount(), { wrapper: createWrapper() });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useMarkAsRead', () => {
  it('marks a notification as read', async () => {
    vi.mocked(notificationsService.markAsRead).mockResolvedValue(undefined as any);

    const { result } = renderHook(() => useMarkAsRead(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate('n1');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(notificationsService.markAsRead).toHaveBeenCalledWith('n1');
  });

  it('handles mutation error', async () => {
    vi.mocked(notificationsService.markAsRead).mockRejectedValue(new Error('Failed'));

    const { result } = renderHook(() => useMarkAsRead(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate('n1');
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useMarkAllAsRead', () => {
  it('marks all notifications as read', async () => {
    vi.mocked(notificationsService.markAllAsRead).mockResolvedValue(undefined as any);

    const { result } = renderHook(() => useMarkAllAsRead(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(notificationsService.markAllAsRead).toHaveBeenCalled();
  });

  it('handles mutation error', async () => {
    vi.mocked(notificationsService.markAllAsRead).mockRejectedValue(new Error('Failed'));

    const { result } = renderHook(() => useMarkAllAsRead(), { wrapper: createWrapper() });

    await act(async () => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
