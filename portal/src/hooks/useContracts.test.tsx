/* eslint-disable @typescript-eslint/no-explicit-any */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useContracts,
  useContract,
  useCreateContract,
  usePublishContract,
  useUpdateContract,
  useDeleteContract,
  useBindings,
  useEnableBinding,
  useDisableBinding,
} from './useContracts';

vi.mock('../services/contracts', () => ({
  contractsService: {
    listContracts: vi.fn(),
    getContract: vi.fn(),
    createContract: vi.fn(),
    publishContract: vi.fn(),
    updateContract: vi.fn(),
    deleteContract: vi.fn(),
    getBindings: vi.fn(),
    enableBinding: vi.fn(),
    disableBinding: vi.fn(),
  },
}));

import { contractsService } from '../services/contracts';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('Contract Hooks', () => {
  beforeEach(() => vi.clearAllMocks());

  describe('useContracts', () => {
    it('should fetch contracts list', async () => {
      vi.mocked(contractsService.listContracts).mockResolvedValueOnce({
        items: [{ id: 'c-1', name: 'orders-api' }],
        total: 1,
      } as any);

      const { result } = renderHook(() => useContracts(), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.items).toHaveLength(1);
    });

    it('should pass params', async () => {
      vi.mocked(contractsService.listContracts).mockResolvedValueOnce({
        items: [],
        total: 0,
      } as any);

      renderHook(() => useContracts({ status: 'published' }), { wrapper: createWrapper() });
      await waitFor(() =>
        expect(contractsService.listContracts).toHaveBeenCalledWith({ status: 'published' })
      );
    });
  });

  describe('useContract', () => {
    it('should fetch a single contract', async () => {
      vi.mocked(contractsService.getContract).mockResolvedValueOnce({
        id: 'c-1',
        name: 'orders-api',
      } as any);

      const { result } = renderHook(() => useContract('c-1'), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.id).toBe('c-1');
    });

    it('should not fetch when contractId is undefined', () => {
      const { result } = renderHook(() => useContract(undefined), { wrapper: createWrapper() });
      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useCreateContract', () => {
    it('should create a contract', async () => {
      vi.mocked(contractsService.createContract).mockResolvedValueOnce({
        id: 'c-new',
        name: 'new-api',
      } as any);

      const { result } = renderHook(() => useCreateContract(), { wrapper: createWrapper() });

      await act(async () => {
        result.current.mutate({ name: 'new-api', display_name: 'New API' } as any);
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.id).toBe('c-new');
    });
  });

  describe('usePublishContract', () => {
    it('should publish a contract and call onSuccess', async () => {
      const onSuccess = vi.fn();
      vi.mocked(contractsService.publishContract).mockResolvedValueOnce({
        contract: { id: 'c-1' },
        bindings: [],
      } as any);

      const { result } = renderHook(() => usePublishContract({ onSuccess }), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ name: 'test' } as any);
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(onSuccess).toHaveBeenCalled();
    });

    it('should call onError on failure', async () => {
      const onError = vi.fn();
      vi.mocked(contractsService.publishContract).mockRejectedValueOnce(new Error('fail'));

      const { result } = renderHook(() => usePublishContract({ onError }), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ name: 'test' } as any);
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(onError).toHaveBeenCalled();
    });
  });

  describe('useUpdateContract', () => {
    it('should update a contract', async () => {
      vi.mocked(contractsService.updateContract).mockResolvedValueOnce({
        id: 'c-1',
        name: 'updated',
      } as any);

      const { result } = renderHook(() => useUpdateContract('c-1'), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ name: 'updated' });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(contractsService.updateContract).toHaveBeenCalledWith('c-1', { name: 'updated' });
    });
  });

  describe('useDeleteContract', () => {
    it('should delete a contract', async () => {
      vi.mocked(contractsService.deleteContract).mockResolvedValueOnce(undefined);

      const { result } = renderHook(() => useDeleteContract(), { wrapper: createWrapper() });

      await act(async () => {
        result.current.mutate('c-1');
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(contractsService.deleteContract).toHaveBeenCalledWith('c-1');
    });
  });
});

describe('Binding Hooks', () => {
  beforeEach(() => vi.clearAllMocks());

  describe('useBindings', () => {
    it('should fetch bindings for a contract', async () => {
      vi.mocked(contractsService.getBindings).mockResolvedValueOnce({
        bindings: [
          { protocol: 'rest', enabled: true },
          { protocol: 'mcp', enabled: false },
        ],
      } as any);

      const { result } = renderHook(() => useBindings('c-1'), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.bindings).toHaveLength(2);
    });

    it('should not fetch when contractId is undefined', () => {
      const { result } = renderHook(() => useBindings(undefined), { wrapper: createWrapper() });
      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useEnableBinding', () => {
    it('should enable a binding', async () => {
      vi.mocked(contractsService.enableBinding).mockResolvedValueOnce({
        protocol: 'mcp',
        enabled: true,
        endpoint: '/tools/orders-api',
      } as any);

      const { result } = renderHook(() => useEnableBinding('c-1'), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate('mcp' as any);
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(contractsService.enableBinding).toHaveBeenCalledWith('c-1', 'mcp');
    });
  });

  describe('useDisableBinding', () => {
    it('should disable a binding', async () => {
      vi.mocked(contractsService.disableBinding).mockResolvedValueOnce({
        protocol: 'graphql',
        enabled: false,
      } as any);

      const { result } = renderHook(() => useDisableBinding('c-1'), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate('graphql' as any);
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });
});
