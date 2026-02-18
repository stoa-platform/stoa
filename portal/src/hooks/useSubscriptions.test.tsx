import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import {
  useSubscriptions,
  useSubscription,
  useMySubscriptions,
  useCreateSubscription,
  useRevokeSubscription,
  useRegenerateApiKey,
  useSubscriptionConfig,
  useRevealApiKey,
  useToggleTotpRequirement,
  useRotateApiKey,
  useSubscriptionRotationInfo,
  useSubscribe,
  useMyAPISubscriptions,
  useApplicationSubscriptions,
  useCancelSubscription,
  useRotateAPISubscriptionKey,
} from './useSubscriptions';

vi.mock('../services/subscriptions', () => ({
  subscriptionsService: {
    listSubscriptions: vi.fn(),
    getSubscription: vi.fn(),
    getMySubscriptions: vi.fn(),
    createSubscription: vi.fn(),
    revokeSubscription: vi.fn(),
    regenerateApiKey: vi.fn(),
    getConfigExport: vi.fn(),
    revealApiKey: vi.fn(),
    toggleTotpRequirement: vi.fn(),
    rotateApiKey: vi.fn(),
    getRotationInfo: vi.fn(),
  },
}));

vi.mock('../services/apiSubscriptions', () => ({
  apiSubscriptionsService: {
    createSubscription: vi.fn(),
    getMySubscriptionsFormatted: vi.fn(),
    listMySubscriptions: vi.fn(),
    cancelSubscription: vi.fn(),
    rotateKey: vi.fn(),
  },
}));

import { subscriptionsService } from '../services/subscriptions';
import { apiSubscriptionsService } from '../services/apiSubscriptions';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('MCP Subscription Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useSubscriptions', () => {
    it('should fetch subscriptions list', async () => {
      vi.mocked(subscriptionsService.listSubscriptions).mockResolvedValueOnce({
        subscriptions: [{ id: 'sub-1' }],
        total: 1,
      } as any);

      const { result } = renderHook(() => useSubscriptions(), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.subscriptions).toHaveLength(1);
    });

    it('should pass params to service', async () => {
      vi.mocked(subscriptionsService.listSubscriptions).mockResolvedValueOnce({
        subscriptions: [],
        total: 0,
      } as any);

      renderHook(() => useSubscriptions({ status: 'active' }), { wrapper: createWrapper() });
      await waitFor(() =>
        expect(subscriptionsService.listSubscriptions).toHaveBeenCalledWith({ status: 'active' })
      );
    });
  });

  describe('useSubscription', () => {
    it('should fetch a single subscription', async () => {
      vi.mocked(subscriptionsService.getSubscription).mockResolvedValueOnce({
        id: 'sub-1',
        plan: 'free',
      } as any);

      const { result } = renderHook(() => useSubscription('sub-1'), {
        wrapper: createWrapper(),
      });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.id).toBe('sub-1');
    });

    it('should not fetch when id is undefined', () => {
      const { result } = renderHook(() => useSubscription(undefined), {
        wrapper: createWrapper(),
      });
      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useMySubscriptions', () => {
    it('should fetch my subscriptions', async () => {
      vi.mocked(subscriptionsService.getMySubscriptions).mockResolvedValueOnce([
        { id: 'sub-1' },
      ] as any);

      const { result } = renderHook(() => useMySubscriptions(), { wrapper: createWrapper() });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(1);
    });
  });

  describe('useCreateSubscription', () => {
    it('should create a subscription', async () => {
      vi.mocked(subscriptionsService.createSubscription).mockResolvedValueOnce({
        subscription: { id: 'sub-new' },
        api_key: 'sk_test_123',
      } as any);

      const { result } = renderHook(() => useCreateSubscription(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ tool_id: 'tool-1', plan: 'free' } as any);
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useRevokeSubscription', () => {
    it('should revoke a subscription', async () => {
      vi.mocked(subscriptionsService.revokeSubscription).mockResolvedValueOnce(undefined);

      const { result } = renderHook(() => useRevokeSubscription(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate('sub-1');
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(subscriptionsService.revokeSubscription).toHaveBeenCalledWith('sub-1');
    });
  });

  describe('useRegenerateApiKey', () => {
    it('should regenerate API key', async () => {
      vi.mocked(subscriptionsService.regenerateApiKey).mockResolvedValueOnce({
        api_key: 'sk_new_456',
      });

      const { result } = renderHook(() => useRegenerateApiKey(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate('sub-1');
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.api_key).toBe('sk_new_456');
    });
  });

  describe('useSubscriptionConfig', () => {
    it('should fetch config export', async () => {
      vi.mocked(subscriptionsService.getConfigExport).mockResolvedValueOnce({
        mcpServers: {},
      } as any);

      const { result } = renderHook(() => useSubscriptionConfig('sub-1'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });

    it('should not fetch when id is undefined', () => {
      const { result } = renderHook(() => useSubscriptionConfig(undefined), {
        wrapper: createWrapper(),
      });
      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useRevealApiKey', () => {
    it('should reveal API key', async () => {
      vi.mocked(subscriptionsService.revealApiKey).mockResolvedValueOnce({
        api_key: 'sk_revealed_789',
      } as any);

      const { result } = renderHook(() => useRevealApiKey(), { wrapper: createWrapper() });

      await act(async () => {
        result.current.mutate({ id: 'sub-1' });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(subscriptionsService.revealApiKey).toHaveBeenCalledWith('sub-1', undefined);
    });

    it('should pass TOTP code when provided', async () => {
      vi.mocked(subscriptionsService.revealApiKey).mockResolvedValueOnce({
        api_key: 'sk_revealed_789',
      } as any);

      const { result } = renderHook(() => useRevealApiKey(), { wrapper: createWrapper() });

      await act(async () => {
        result.current.mutate({ id: 'sub-1', totpCode: '123456' });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(subscriptionsService.revealApiKey).toHaveBeenCalledWith('sub-1', '123456');
    });
  });

  describe('useToggleTotpRequirement', () => {
    it('should toggle TOTP requirement', async () => {
      vi.mocked(subscriptionsService.toggleTotpRequirement).mockResolvedValueOnce({
        totp_required: true,
      } as any);

      const { result } = renderHook(() => useToggleTotpRequirement(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ id: 'sub-1', enabled: true });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useRotateApiKey', () => {
    it('should rotate API key with grace period', async () => {
      vi.mocked(subscriptionsService.rotateApiKey).mockResolvedValueOnce({
        new_api_key: 'sk_rotated',
        grace_period_hours: 24,
      } as any);

      const { result } = renderHook(() => useRotateApiKey(), { wrapper: createWrapper() });

      await act(async () => {
        result.current.mutate({ id: 'sub-1', gracePeriodHours: 24 });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(subscriptionsService.rotateApiKey).toHaveBeenCalledWith('sub-1', {
        grace_period_hours: 24,
      });
    });

    it('should rotate without grace period', async () => {
      vi.mocked(subscriptionsService.rotateApiKey).mockResolvedValueOnce({
        new_api_key: 'sk_rotated',
      } as any);

      const { result } = renderHook(() => useRotateApiKey(), { wrapper: createWrapper() });

      await act(async () => {
        result.current.mutate({ id: 'sub-1' });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(subscriptionsService.rotateApiKey).toHaveBeenCalledWith('sub-1', undefined);
    });
  });

  describe('useSubscriptionRotationInfo', () => {
    it('should fetch rotation info', async () => {
      vi.mocked(subscriptionsService.getRotationInfo).mockResolvedValueOnce({
        id: 'sub-1',
        rotation_in_progress: true,
      } as any);

      const { result } = renderHook(() => useSubscriptionRotationInfo('sub-1'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });

    it('should not fetch when id is undefined', () => {
      const { result } = renderHook(() => useSubscriptionRotationInfo(undefined), {
        wrapper: createWrapper(),
      });
      expect(result.current.fetchStatus).toBe('idle');
    });
  });
});

describe('API Subscription Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useSubscribe', () => {
    it('should subscribe to an API', async () => {
      vi.mocked(apiSubscriptionsService.createSubscription).mockResolvedValueOnce({
        subscription_id: 'sub-api-1',
        api_key: 'sk_api_123',
        api_key_prefix: 'sk_api_',
        expires_at: null,
      } as any);

      const { result } = renderHook(() => useSubscribe(), { wrapper: createWrapper() });

      await act(async () => {
        result.current.mutate({
          applicationId: 'app-1',
          applicationName: 'My App',
          apiId: 'api-1',
          apiName: 'Payment API',
          apiVersion: '1.0',
          tenantId: 'oasis',
        });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.apiKey).toBe('sk_api_123');
      expect(result.current.data?.subscription.id).toBe('sub-api-1');
    });
  });

  describe('useMyAPISubscriptions', () => {
    it('should fetch formatted subscriptions', async () => {
      vi.mocked(apiSubscriptionsService.getMySubscriptionsFormatted).mockResolvedValueOnce([
        { id: 'sub-1', status: 'active' },
      ] as any);

      const { result } = renderHook(() => useMyAPISubscriptions(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(1);
    });
  });

  describe('useApplicationSubscriptions', () => {
    it('should fetch subscriptions for an application', async () => {
      vi.mocked(apiSubscriptionsService.listMySubscriptions).mockResolvedValueOnce({
        items: [
          {
            id: 'sub-1',
            application_id: 'app-1',
            application_name: 'My App',
            api_id: 'api-1',
            api_name: 'API',
            api_version: '1.0',
            tenant_id: 'oasis',
            status: 'active',
            api_key_prefix: 'sk_',
            created_at: '2026-01-01',
            expires_at: null,
            plan_id: null,
            plan_name: null,
          },
        ],
      } as any);

      const { result } = renderHook(() => useApplicationSubscriptions('app-1'), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(1);
    });

    it('should not fetch when applicationId is undefined', () => {
      const { result } = renderHook(() => useApplicationSubscriptions(undefined), {
        wrapper: createWrapper(),
      });
      expect(result.current.fetchStatus).toBe('idle');
    });
  });

  describe('useCancelSubscription', () => {
    it('should cancel a subscription', async () => {
      vi.mocked(apiSubscriptionsService.cancelSubscription).mockResolvedValueOnce(undefined);

      const { result } = renderHook(() => useCancelSubscription(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate('sub-1');
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
    });
  });

  describe('useRotateAPISubscriptionKey', () => {
    it('should rotate API subscription key', async () => {
      vi.mocked(apiSubscriptionsService.rotateKey).mockResolvedValueOnce({
        new_api_key: 'sk_rotated',
      } as any);

      const { result } = renderHook(() => useRotateAPISubscriptionKey(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate({ id: 'sub-1', gracePeriodHours: 48 });
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(apiSubscriptionsService.rotateKey).toHaveBeenCalledWith('sub-1', {
        grace_period_hours: 48,
      });
    });
  });
});
