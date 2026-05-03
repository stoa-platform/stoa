import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockHttpClient } = vi.hoisted(() => ({
  mockHttpClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

vi.mock('../http', async () => {
  const actual = await vi.importActual<typeof import('../http')>('../http');
  return { ...actual, httpClient: mockHttpClient };
});

import { apiLifecycleClient } from './apiLifecycle';

describe('apiLifecycleClient', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHttpClient.get.mockResolvedValue({ data: {} });
    mockHttpClient.post.mockResolvedValue({ data: {} });
  });

  it('creates lifecycle drafts through the canonical endpoint', async () => {
    const request = {
      name: 'payments-api',
      display_name: 'Payments API',
      version: '1.0.0',
      description: 'Payments',
      backend_url: 'https://payments.internal',
      openapi_spec: { openapi: '3.0.3', info: { title: 'Payments API', version: '1.0.0' } },
      tags: ['payments'],
    };

    await apiLifecycleClient.createDraft('tenant-1', request);

    expect(mockHttpClient.post).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/apis/lifecycle/drafts',
      request
    );
  });

  it('loads aggregate lifecycle state', async () => {
    await apiLifecycleClient.getState('tenant-1', 'payments-api');

    expect(mockHttpClient.get).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/apis/payments-api/lifecycle'
    );
  });

  it('posts validation, deployment, publication, and promotion actions', async () => {
    await apiLifecycleClient.validateDraft('tenant-1', 'payments-api', { reason: 'manual' });
    await apiLifecycleClient.deploy('tenant-1', 'payments-api', {
      environment: 'dev',
      gateway_instance_id: 'gw-1',
      force: false,
    });
    await apiLifecycleClient.publish('tenant-1', 'payments-api', {
      environment: 'dev',
      gateway_instance_id: 'gw-1',
      force: false,
    });
    await apiLifecycleClient.promote('tenant-1', 'payments-api', {
      source_environment: 'dev',
      target_environment: 'staging',
      target_gateway_instance_id: 'gw-2',
      force: false,
    });

    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      1,
      '/v1/tenants/tenant-1/apis/payments-api/lifecycle/validate',
      { reason: 'manual' }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/apis/payments-api/lifecycle/deployments',
      { environment: 'dev', gateway_instance_id: 'gw-1', force: false }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      3,
      '/v1/tenants/tenant-1/apis/payments-api/lifecycle/publications',
      { environment: 'dev', gateway_instance_id: 'gw-1', force: false }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      4,
      '/v1/tenants/tenant-1/apis/payments-api/lifecycle/promotions',
      {
        source_environment: 'dev',
        target_environment: 'staging',
        target_gateway_instance_id: 'gw-2',
        force: false,
      }
    );
  });
});
