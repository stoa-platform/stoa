import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockHttpClient } = vi.hoisted(() => ({
  mockHttpClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../../services/http', async () => {
  const actual =
    await vi.importActual<typeof import('../../../services/http')>('../../../services/http');
  return {
    ...actual,
    httpClient: mockHttpClient,
  };
});

import { subscriptionsClient } from '../../../services/api/subscriptions';
import { webhooksClient } from '../../../services/api/webhooks';
import { credentialMappingsClient } from '../../../services/api/credentialMappings';
import { contractsClient } from '../../../services/api/contracts';
import { promotionsClient } from '../../../services/api/promotions';

describe('UI-2 S2b domain clients', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('covers subscriptionsClient request delegation', async () => {
    const list = { items: [] };
    const pending = { items: [] };
    const stats = { active: 1 };
    const subscription = { id: 'sub-1' };
    const bulkResult = { success_count: 1, failure_count: 0 };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: list })
      .mockResolvedValueOnce({ data: pending })
      .mockResolvedValueOnce({ data: stats });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: subscription })
      .mockResolvedValueOnce({ data: subscription })
      .mockResolvedValueOnce({ data: bulkResult });

    await expect(subscriptionsClient.list('tenant-1', 'approved', 2, 50, 'prod')).resolves.toBe(
      list
    );
    await expect(subscriptionsClient.listPending('tenant-1', 3, 25)).resolves.toBe(pending);
    await expect(subscriptionsClient.getStats('tenant-1')).resolves.toBe(stats);
    await expect(subscriptionsClient.approve('sub-1', '2026-04-30')).resolves.toBe(subscription);
    await expect(subscriptionsClient.reject('sub-1', 'missing docs')).resolves.toBe(subscription);
    await expect(
      subscriptionsClient.bulkAction({
        subscription_ids: ['sub-1'],
        action: 'approve',
      })
    ).resolves.toBe(bulkResult);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/subscriptions/tenant/tenant-1', {
      params: {
        status: 'approved',
        page: 2,
        page_size: 50,
        environment: 'prod',
      },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      2,
      '/v1/subscriptions/tenant/tenant-1/pending',
      {
        params: { page: 3, page_size: 25 },
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      3,
      '/v1/subscriptions/tenant/tenant-1/stats'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(1, '/v1/subscriptions/sub-1/approve', {
      expires_at: '2026-04-30',
    });
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(2, '/v1/subscriptions/sub-1/reject', {
      reason: 'missing docs',
    });
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(3, '/v1/subscriptions/bulk', {
      subscription_ids: ['sub-1'],
      action: 'approve',
    });
  });

  it('covers webhooksClient request delegation', async () => {
    const webhookList = { items: [] };
    const webhook = { id: 'wh-1' };
    const testResponse = { delivered: true };
    const deliveries = { items: [] };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: webhookList })
      .mockResolvedValueOnce({ data: webhook })
      .mockResolvedValueOnce({ data: deliveries });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: webhook })
      .mockResolvedValueOnce({ data: testResponse })
      .mockResolvedValueOnce({});
    mockHttpClient.patch.mockResolvedValueOnce({ data: webhook });
    mockHttpClient.delete.mockResolvedValueOnce({});

    await expect(webhooksClient.list('tenant-1')).resolves.toBe(webhookList);
    await expect(webhooksClient.get('tenant-1', 'wh-1')).resolves.toBe(webhook);
    await expect(
      webhooksClient.create('tenant-1', {
        name: 'Ops',
        url: 'https://example.com/hook',
        events: ['subscription.created'],
      })
    ).resolves.toBe(webhook);
    await expect(
      webhooksClient.update('tenant-1', 'wh-1', {
        name: 'Ops v2',
      })
    ).resolves.toBe(webhook);
    await expect(webhooksClient.remove('tenant-1', 'wh-1')).resolves.toBeUndefined();
    await expect(webhooksClient.test('tenant-1', 'wh-1')).resolves.toBe(testResponse);
    await expect(webhooksClient.listDeliveries('tenant-1', 'wh-1', 15)).resolves.toBe(deliveries);
    await expect(
      webhooksClient.retryDelivery('tenant-1', 'wh-1', 'delivery-1')
    ).resolves.toBeUndefined();

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/webhooks');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/tenants/tenant-1/webhooks/wh-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/webhooks', {
      name: 'Ops',
      url: 'https://example.com/hook',
      events: ['subscription.created'],
    });
    expect(mockHttpClient.patch).toHaveBeenCalledWith('/v1/tenants/tenant-1/webhooks/wh-1', {
      name: 'Ops v2',
    });
    expect(mockHttpClient.delete).toHaveBeenCalledWith('/v1/tenants/tenant-1/webhooks/wh-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/webhooks/wh-1/test',
      {
        event_type: 'subscription.created',
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/webhooks/wh-1/deliveries',
      {
        params: { limit: 15 },
      }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/webhooks/wh-1/deliveries/delivery-1/retry'
    );
  });

  it('covers credentialMappingsClient request delegation', async () => {
    const list = { items: [] };
    const mapping = { id: 'map-1' };

    mockHttpClient.get.mockResolvedValueOnce({ data: list });
    mockHttpClient.post.mockResolvedValueOnce({ data: mapping });
    mockHttpClient.put.mockResolvedValueOnce({ data: mapping });
    mockHttpClient.delete.mockResolvedValueOnce({});

    await expect(credentialMappingsClient.list('tenant-1')).resolves.toBe(list);
    await expect(
      credentialMappingsClient.create('tenant-1', {
        provider: 'vault',
        remote_key: 'secret/data/foo',
      })
    ).resolves.toBe(mapping);
    await expect(
      credentialMappingsClient.update('tenant-1', 'map-1', {
        remote_key: 'secret/data/bar',
      })
    ).resolves.toBe(mapping);
    await expect(credentialMappingsClient.remove('tenant-1', 'map-1')).resolves.toBeUndefined();

    expect(mockHttpClient.get).toHaveBeenCalledWith('/v1/tenants/tenant-1/credential-mappings');
    expect(mockHttpClient.post).toHaveBeenCalledWith('/v1/tenants/tenant-1/credential-mappings', {
      provider: 'vault',
      remote_key: 'secret/data/foo',
    });
    expect(mockHttpClient.put).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/credential-mappings/map-1',
      {
        remote_key: 'secret/data/bar',
      }
    );
    expect(mockHttpClient.delete).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/credential-mappings/map-1'
    );
  });

  it('covers contractsClient request delegation', async () => {
    const list = { items: [] };
    const contract = { id: 'ct-1' };
    const publishResponse = { artifact_url: 'https://example.com/uac.json' };
    const bindings = [{ protocol: 'mcp' }];
    const binding = { protocol: 'mcp' };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: list })
      .mockResolvedValueOnce({ data: contract })
      .mockResolvedValueOnce({ data: bindings });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: contract })
      .mockResolvedValueOnce({ data: publishResponse })
      .mockResolvedValueOnce({ data: binding });
    mockHttpClient.patch.mockResolvedValueOnce({ data: contract });
    mockHttpClient.delete.mockResolvedValueOnce({}).mockResolvedValueOnce({});

    await expect(contractsClient.list('tenant-1')).resolves.toBe(list);
    await expect(contractsClient.get('tenant-1', 'ct-1')).resolves.toBe(contract);
    await expect(
      contractsClient.create('tenant-1', {
        name: 'Payments',
        version: '1.0.0',
      })
    ).resolves.toBe(contract);
    await expect(contractsClient.publish('tenant-1', 'ct-1')).resolves.toBe(publishResponse);
    await expect(
      contractsClient.update('tenant-1', 'ct-1', {
        description: 'Updated',
      })
    ).resolves.toBe(contract);
    await expect(contractsClient.remove('tenant-1', 'ct-1')).resolves.toBeUndefined();
    await expect(contractsClient.listBindings('tenant-1', 'ct-1')).resolves.toBe(bindings);
    await expect(contractsClient.enableBinding('tenant-1', 'ct-1', 'mcp')).resolves.toBe(binding);
    await expect(
      contractsClient.disableBinding('tenant-1', 'ct-1', 'mcp')
    ).resolves.toBeUndefined();

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/contracts');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/tenants/tenant-1/contracts/ct-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/contracts', {
      name: 'Payments',
      version: '1.0.0',
    });
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/contracts/ct-1/publish'
    );
    expect(mockHttpClient.patch).toHaveBeenCalledWith('/v1/tenants/tenant-1/contracts/ct-1', {
      description: 'Updated',
    });
    expect(mockHttpClient.delete).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/contracts/ct-1');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/contracts/ct-1/bindings'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/contracts/ct-1/bindings',
      { protocol: 'mcp' }
    );
    expect(mockHttpClient.delete).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/contracts/ct-1/bindings/mcp'
    );
  });

  it('covers promotionsClient request delegation', async () => {
    const list = { items: [] };
    const promotion = { id: 'promo-1' };
    const diff = { resources: [] };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: list })
      .mockResolvedValueOnce({ data: promotion })
      .mockResolvedValueOnce({ data: diff });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: promotion })
      .mockResolvedValueOnce({ data: promotion })
      .mockResolvedValueOnce({ data: promotion })
      .mockResolvedValueOnce({ data: promotion });

    await expect(
      promotionsClient.list('tenant-1', { api_id: 'api-1', status: 'pending' })
    ).resolves.toBe(list);
    await expect(promotionsClient.get('tenant-1', 'promo-1')).resolves.toBe(promotion);
    await expect(
      promotionsClient.create('tenant-1', 'api-1', {
        target_environment: 'prod',
      })
    ).resolves.toBe(promotion);
    await expect(promotionsClient.approve('tenant-1', 'promo-1')).resolves.toBe(promotion);
    await expect(promotionsClient.complete('tenant-1', 'promo-1')).resolves.toBe(promotion);
    await expect(
      promotionsClient.rollback('tenant-1', 'promo-1', { reason: 'rollback' })
    ).resolves.toBe(promotion);
    await expect(promotionsClient.getDiff('tenant-1', 'promo-1')).resolves.toBe(diff);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/promotions', {
      params: { api_id: 'api-1', status: 'pending' },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/promotions/promo-1'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      1,
      '/v1/tenants/tenant-1/promotions/api-1',
      {
        target_environment: 'prod',
      }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/promotions/promo-1/approve'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/promotions/promo-1/complete'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      4,
      '/v1/tenants/tenant-1/promotions/promo-1/rollback',
      { reason: 'rollback' }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/promotions/promo-1/diff'
    );
  });
});
