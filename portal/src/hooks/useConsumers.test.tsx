/**
 * Tests for Consumer hooks (CAB-1121 P5)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useConsumers,
  useConsumer,
  useRegisterConsumer,
  useUpdateConsumer,
  useConsumerCredentials,
  useSuspendConsumer,
  useActivateConsumer,
} from './useConsumers';

vi.mock('../services/consumers', () => ({
  consumersService: {
    list: vi.fn(),
    get: vi.fn(),
    register: vi.fn(),
    update: vi.fn(),
    getCredentials: vi.fn(),
    suspend: vi.fn(),
    activate: vi.fn(),
  },
}));

import { consumersService } from '../services/consumers';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useConsumers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch consumers list', async () => {
    vi.mocked(consumersService.list).mockResolvedValueOnce({
      items: [{ id: 'c-1', name: 'App' }],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    } as any);

    const { result } = renderHook(() => useConsumers('acme'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.items).toHaveLength(1);
    expect(consumersService.list).toHaveBeenCalledWith('acme', undefined);
  });

  it('should not fetch when tenantId is undefined', () => {
    const { result } = renderHook(() => useConsumers(undefined), { wrapper: createWrapper() });

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useConsumer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should fetch a single consumer', async () => {
    vi.mocked(consumersService.get).mockResolvedValueOnce({
      id: 'c-1',
      name: 'App',
    } as any);

    const { result } = renderHook(() => useConsumer('acme', 'c-1'), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.id).toBe('c-1');
  });

  it('should not fetch when tenantId is undefined', () => {
    const { result } = renderHook(() => useConsumer(undefined, 'c-1'), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
  });

  it('should not fetch when consumerId is undefined', () => {
    const { result } = renderHook(() => useConsumer('acme', undefined), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useRegisterConsumer', () => {
  it('should register a consumer', async () => {
    vi.mocked(consumersService.register).mockResolvedValueOnce({
      id: 'c-2',
      name: 'New App',
    } as any);

    const { result } = renderHook(() => useRegisterConsumer(), { wrapper: createWrapper() });

    result.current.mutate({
      tenantId: 'acme',
      data: { name: 'New App', external_id: 'new-app', contact_email: 'dev@acme.com' } as any,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.id).toBe('c-2');
  });
});

describe('useUpdateConsumer', () => {
  it('should update a consumer', async () => {
    vi.mocked(consumersService.update).mockResolvedValueOnce({
      id: 'c-1',
      name: 'Updated',
    } as any);

    const { result } = renderHook(() => useUpdateConsumer(), { wrapper: createWrapper() });

    result.current.mutate({
      tenantId: 'acme',
      consumerId: 'c-1',
      data: { name: 'Updated' } as any,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.name).toBe('Updated');
  });
});

describe('useConsumerCredentials', () => {
  it('should fetch consumer credentials', async () => {
    vi.mocked(consumersService.getCredentials).mockResolvedValueOnce({
      client_id: 'client-123',
      client_secret: 'secret-xyz',
      token_endpoint: 'https://auth.gostoa.dev/realms/stoa/protocol/openid-connect/token',
      grant_type: 'client_credentials',
    });

    const { result } = renderHook(() => useConsumerCredentials(), { wrapper: createWrapper() });

    result.current.mutate({ tenantId: 'acme', consumerId: 'c-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.client_id).toBe('client-123');
  });
});

describe('useSuspendConsumer', () => {
  it('should suspend a consumer', async () => {
    vi.mocked(consumersService.suspend).mockResolvedValueOnce({
      id: 'c-1',
      status: 'suspended',
    } as any);

    const { result } = renderHook(() => useSuspendConsumer(), { wrapper: createWrapper() });

    result.current.mutate({ tenantId: 'acme', consumerId: 'c-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useActivateConsumer', () => {
  it('should activate a consumer', async () => {
    vi.mocked(consumersService.activate).mockResolvedValueOnce({
      id: 'c-1',
      status: 'active',
    } as any);

    const { result } = renderHook(() => useActivateConsumer(), { wrapper: createWrapper() });

    result.current.mutate({ tenantId: 'acme', consumerId: 'c-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});
