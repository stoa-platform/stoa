/**
 * Tests for Webhook hooks (CAB-315)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useWebhooks,
  useWebhook,
  useCreateWebhook,
  useUpdateWebhook,
  useDeleteWebhook,
  useTestWebhook,
  useWebhookEventTypes,
  useWebhookDeliveries,
  useRetryDelivery,
} from './useWebhooks';

vi.mock('../services/webhooks', () => ({
  webhooksService: {
    getEventTypes: vi.fn(),
    listWebhooks: vi.fn(),
    getWebhook: vi.fn(),
    createWebhook: vi.fn(),
    updateWebhook: vi.fn(),
    deleteWebhook: vi.fn(),
    testWebhook: vi.fn(),
    getDeliveries: vi.fn(),
    retryDelivery: vi.fn(),
  },
}));

import { webhooksService } from '../services/webhooks';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useWebhookEventTypes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch event types', async () => {
    vi.mocked(webhooksService.getEventTypes).mockResolvedValueOnce({
      events: [{ event: 'subscription.created', description: 'desc', payload_example: {} }],
    });

    const { result } = renderHook(() => useWebhookEventTypes('acme'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.events).toHaveLength(1);
  });

  it('should not fetch when tenantId is undefined', () => {
    const { result } = renderHook(() => useWebhookEventTypes(undefined), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useWebhooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should list webhooks for tenant', async () => {
    vi.mocked(webhooksService.listWebhooks).mockResolvedValueOnce({
      items: [{ id: 'wh-1' }],
      total: 1,
    } as any);

    const { result } = renderHook(() => useWebhooks('acme'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
  });
});

describe('useWebhook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch a single webhook', async () => {
    vi.mocked(webhooksService.getWebhook).mockResolvedValueOnce({ id: 'wh-1' } as any);

    const { result } = renderHook(() => useWebhook('acme', 'wh-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it('should not fetch when ids are undefined', () => {
    const { result } = renderHook(() => useWebhook(undefined, undefined), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useCreateWebhook', () => {
  it('should create a webhook', async () => {
    vi.mocked(webhooksService.createWebhook).mockResolvedValueOnce({ id: 'wh-2' } as any);

    const { result } = renderHook(() => useCreateWebhook(), { wrapper: createWrapper() });

    result.current.mutate({ tenantId: 'acme', data: { url: 'https://hook.com' } as any });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useUpdateWebhook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should update a webhook', async () => {
    vi.mocked(webhooksService.updateWebhook).mockResolvedValueOnce({
      id: 'wh-1',
      url: 'https://updated.com',
    } as any);

    const { result } = renderHook(() => useUpdateWebhook(), { wrapper: createWrapper() });

    result.current.mutate({
      tenantId: 'acme',
      webhookId: 'wh-1',
      data: { url: 'https://updated.com' } as any,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(webhooksService.updateWebhook).toHaveBeenCalledWith('acme', 'wh-1', {
      url: 'https://updated.com',
    });
    expect(result.current.data?.url).toBe('https://updated.com');
  });
});

describe('useDeleteWebhook', () => {
  it('should delete a webhook', async () => {
    vi.mocked(webhooksService.deleteWebhook).mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useDeleteWebhook(), { wrapper: createWrapper() });

    result.current.mutate({ tenantId: 'acme', webhookId: 'wh-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useTestWebhook', () => {
  it('should test a webhook', async () => {
    vi.mocked(webhooksService.testWebhook).mockResolvedValueOnce({
      success: true,
    } as any);

    const { result } = renderHook(() => useTestWebhook(), { wrapper: createWrapper() });

    result.current.mutate({ tenantId: 'acme', webhookId: 'wh-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useWebhookDeliveries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch deliveries for a webhook', async () => {
    vi.mocked(webhooksService.getDeliveries).mockResolvedValueOnce({
      items: [{ id: 'd-1' }],
      total: 1,
    } as any);

    const { result } = renderHook(() => useWebhookDeliveries('acme', 'wh-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
  });

  it('should not fetch when ids are undefined', () => {
    const { result } = renderHook(() => useWebhookDeliveries(undefined, undefined), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useRetryDelivery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should retry a failed delivery', async () => {
    vi.mocked(webhooksService.retryDelivery).mockResolvedValueOnce({
      id: 'd-1',
      status: 'success',
    } as any);

    const { result } = renderHook(() => useRetryDelivery(), { wrapper: createWrapper() });

    result.current.mutate({ tenantId: 'acme', webhookId: 'wh-1', deliveryId: 'd-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(webhooksService.retryDelivery).toHaveBeenCalledWith('acme', 'wh-1', 'd-1');
  });
});
