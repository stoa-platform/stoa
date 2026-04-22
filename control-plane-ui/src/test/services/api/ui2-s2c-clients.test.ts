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

vi.mock('../../../services/http', () => ({
  httpClient: mockHttpClient,
}));

import { tenantsClient } from '../../../services/api/tenants';
import { apisClient } from '../../../services/api/apis';
import { applicationsClient } from '../../../services/api/applications';
import { consumersClient } from '../../../services/api/consumers';

describe('UI-2 S2c domain clients', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('covers tenantsClient request delegation', async () => {
    const tenantList = [{ id: 'tenant-1' }];
    const tenant = { id: 'tenant-1', name: 'Acme' };
    const ca = { issuer: 'stoa-root' };
    const signResponse = { certificate_pem: 'cert', serial_number: '123' };
    const issuedCertificates = { items: [{ id: 'cert-1' }] };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: tenantList })
      .mockResolvedValueOnce({ data: tenant })
      .mockResolvedValueOnce({ data: ca })
      .mockResolvedValueOnce({ data: issuedCertificates });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: tenant })
      .mockResolvedValueOnce({ data: ca })
      .mockResolvedValueOnce({ data: signResponse })
      .mockResolvedValueOnce({});
    mockHttpClient.put.mockResolvedValueOnce({ data: tenant });
    mockHttpClient.delete.mockResolvedValueOnce({}).mockResolvedValueOnce({});

    await expect(tenantsClient.list()).resolves.toBe(tenantList);
    await expect(tenantsClient.get('tenant-1')).resolves.toBe(tenant);
    await expect(
      tenantsClient.create({
        name: 'Acme',
        slug: 'acme',
      } as never)
    ).resolves.toBe(tenant);
    await expect(
      tenantsClient.update('tenant-1', {
        name: 'Acme 2',
      } as never)
    ).resolves.toBe(tenant);
    await expect(tenantsClient.remove('tenant-1')).resolves.toBeUndefined();
    await expect(tenantsClient.getCA('tenant-1')).resolves.toBe(ca);
    await expect(tenantsClient.generateCA('tenant-1')).resolves.toBe(ca);
    await expect(tenantsClient.signCSR('tenant-1', 'csr-pem', 90)).resolves.toBe(signResponse);
    await expect(tenantsClient.revokeCA('tenant-1')).resolves.toBeUndefined();
    await expect(tenantsClient.listIssuedCertificates('tenant-1', 'active')).resolves.toBe(
      issuedCertificates
    );
    await expect(
      tenantsClient.revokeIssuedCertificate('tenant-1', 'cert-1')
    ).resolves.toBeUndefined();

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/tenants/tenant-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(1, '/v1/tenants', {
      name: 'Acme',
      slug: 'acme',
    });
    expect(mockHttpClient.put).toHaveBeenCalledWith('/v1/tenants/tenant-1', {
      name: 'Acme 2',
    });
    expect(mockHttpClient.delete).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(3, '/v1/tenants/tenant-1/ca');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(2, '/v1/tenants/tenant-1/ca/generate');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(3, '/v1/tenants/tenant-1/ca/sign', {
      csr_pem: 'csr-pem',
      validity_days: 90,
    });
    expect(mockHttpClient.delete).toHaveBeenNthCalledWith(2, '/v1/tenants/tenant-1/ca');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      4,
      '/v1/tenants/tenant-1/ca/certificates',
      {
        params: { status: 'active' },
      }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      4,
      '/v1/tenants/tenant-1/ca/certificates/cert-1/revoke'
    );
  });

  it('covers apisClient request delegation', async () => {
    const apiList = { items: [{ id: 'api-1' }] };
    const api = { id: 'api-1', name: 'Payments' };
    const adminList = { items: [{ id: 'api-2' }] };
    const versions = [{ version: '1.0.0' }];
    const audienceUpdate = {
      api_id: 'api-1',
      tenant_id: 'tenant-1',
      audience: 'payments',
      updated_by: 'admin',
    };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: apiList })
      .mockResolvedValueOnce({ data: adminList })
      .mockResolvedValueOnce({ data: api })
      .mockResolvedValueOnce({ data: versions });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: api })
      .mockResolvedValueOnce({});
    mockHttpClient.put.mockResolvedValueOnce({ data: api });
    mockHttpClient.patch.mockResolvedValueOnce({ data: audienceUpdate });
    mockHttpClient.delete.mockResolvedValueOnce({});

    await expect(apisClient.list('tenant-1', 'prod')).resolves.toEqual(apiList.items);
    await expect(apisClient.listAdmin(2, 25)).resolves.toEqual(adminList.items);
    await expect(apisClient.get('tenant-1', 'api-1')).resolves.toBe(api);
    await expect(
      apisClient.create('tenant-1', {
        name: 'Payments',
      } as never)
    ).resolves.toBe(api);
    await expect(
      apisClient.update('tenant-1', 'api-1', {
        description: 'Updated',
      } as never)
    ).resolves.toBe(api);
    await expect(apisClient.remove('tenant-1', 'api-1')).resolves.toBeUndefined();
    await expect(apisClient.listVersions('tenant-1', 'api-1', 50)).resolves.toBe(versions);
    await expect(
      apisClient.updateAudience('tenant-1', 'api-1', 'payments')
    ).resolves.toBe(audienceUpdate);
    await expect(apisClient.triggerCatalogSync('tenant-1')).resolves.toBeUndefined();

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/apis', {
      params: { page: 1, page_size: 100, environment: 'prod' },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/admin/catalog/apis', {
      params: { page: 2, page_size: 25 },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(3, '/v1/tenants/tenant-1/apis/api-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/apis', {
      name: 'Payments',
    });
    expect(mockHttpClient.put).toHaveBeenCalledWith('/v1/tenants/tenant-1/apis/api-1', {
      description: 'Updated',
    });
    expect(mockHttpClient.delete).toHaveBeenCalledWith('/v1/tenants/tenant-1/apis/api-1');
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      4,
      '/v1/tenants/tenant-1/apis/api-1/versions',
      {
        params: { limit: 50 },
      }
    );
    expect(mockHttpClient.patch).toHaveBeenCalledWith(
      '/v1/admin/catalog/tenant-1/api-1/audience',
      {
        audience: 'payments',
      }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(2, '/v1/admin/catalog/sync/tenant/tenant-1');
  });

  it('covers applicationsClient request delegation', async () => {
    const list = { items: [{ id: 'app-1' }] };
    const app = { id: 'app-1', name: 'Console' };

    mockHttpClient.get.mockResolvedValueOnce({ data: list }).mockResolvedValueOnce({ data: app });
    mockHttpClient.post.mockResolvedValueOnce({ data: app });
    mockHttpClient.put.mockResolvedValueOnce({ data: app });
    mockHttpClient.delete.mockResolvedValueOnce({});

    await expect(applicationsClient.list('tenant-1')).resolves.toEqual(list.items);
    await expect(applicationsClient.get('tenant-1', 'app-1')).resolves.toBe(app);
    await expect(
      applicationsClient.create('tenant-1', {
        name: 'Console',
      } as never)
    ).resolves.toBe(app);
    await expect(
      applicationsClient.update('tenant-1', 'app-1', {
        description: 'Updated',
      } as never)
    ).resolves.toBe(app);
    await expect(applicationsClient.remove('tenant-1', 'app-1')).resolves.toBeUndefined();

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/tenants/tenant-1/applications', {
      params: { page: 1, page_size: 100 },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      2,
      '/v1/tenants/tenant-1/applications/app-1'
    );
    expect(mockHttpClient.post).toHaveBeenCalledWith('/v1/tenants/tenant-1/applications', {
      name: 'Console',
    });
    expect(mockHttpClient.put).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/applications/app-1',
      {
        description: 'Updated',
      }
    );
    expect(mockHttpClient.delete).toHaveBeenCalledWith(
      '/v1/tenants/tenant-1/applications/app-1'
    );
  });

  it('covers consumersClient request delegation', async () => {
    const list = { items: [{ id: 'consumer-1' }] };
    const consumer = { id: 'consumer-1', status: 'active' };
    const expiring = { items: [{ id: 'consumer-1' }] };
    const bulkRevoke = { success_count: 1, failure_count: 0 };

    mockHttpClient.get
      .mockResolvedValueOnce({ data: list })
      .mockResolvedValueOnce({ data: consumer })
      .mockResolvedValueOnce({ data: expiring });
    mockHttpClient.post
      .mockResolvedValueOnce({ data: consumer })
      .mockResolvedValueOnce({ data: consumer })
      .mockResolvedValueOnce({ data: consumer })
      .mockResolvedValueOnce({ data: consumer })
      .mockResolvedValueOnce({ data: consumer })
      .mockResolvedValueOnce({ data: consumer })
      .mockResolvedValueOnce({ data: bulkRevoke });
    mockHttpClient.delete.mockResolvedValueOnce({});

    await expect(consumersClient.list('tenant-1', 'prod')).resolves.toEqual(list.items);
    await expect(consumersClient.get('tenant-1', 'consumer-1')).resolves.toBe(consumer);
    await expect(consumersClient.suspend('tenant-1', 'consumer-1')).resolves.toBe(consumer);
    await expect(consumersClient.activate('tenant-1', 'consumer-1')).resolves.toBe(consumer);
    await expect(consumersClient.remove('tenant-1', 'consumer-1')).resolves.toBeUndefined();
    await expect(
      consumersClient.rotateCertificate('tenant-1', 'consumer-1', 'cert-pem', 12)
    ).resolves.toBe(consumer);
    await expect(
      consumersClient.revokeCertificate('tenant-1', 'consumer-1')
    ).resolves.toBe(consumer);
    await expect(consumersClient.block('tenant-1', 'consumer-1')).resolves.toBe(consumer);
    await expect(
      consumersClient.bindCertificate('tenant-1', 'consumer-1', 'cert-pem')
    ).resolves.toBe(consumer);
    await expect(consumersClient.getExpiringCertificates('tenant-1', 14)).resolves.toBe(expiring);
    await expect(
      consumersClient.bulkRevokeCertificates('tenant-1', ['consumer-1'])
    ).resolves.toBe(bulkRevoke);

    expect(mockHttpClient.get).toHaveBeenNthCalledWith(1, '/v1/consumers/tenant-1', {
      params: { page: 1, page_size: 100, environment: 'prod' },
    });
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(2, '/v1/consumers/tenant-1/consumer-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      1,
      '/v1/consumers/tenant-1/consumer-1/suspend'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      2,
      '/v1/consumers/tenant-1/consumer-1/activate'
    );
    expect(mockHttpClient.delete).toHaveBeenCalledWith('/v1/consumers/tenant-1/consumer-1');
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      3,
      '/v1/consumers/tenant-1/consumer-1/certificate/rotate',
      {
        certificate_pem: 'cert-pem',
        grace_period_hours: 12,
      }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      4,
      '/v1/consumers/tenant-1/consumer-1/certificate/revoke'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      5,
      '/v1/consumers/tenant-1/consumer-1/block'
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      6,
      '/v1/consumers/tenant-1/consumer-1/certificate',
      {
        certificate_pem: 'cert-pem',
      }
    );
    expect(mockHttpClient.get).toHaveBeenNthCalledWith(
      3,
      '/v1/consumers/tenant-1/certificates/expiring',
      {
        params: { days: 14 },
      }
    );
    expect(mockHttpClient.post).toHaveBeenNthCalledWith(
      7,
      '/v1/consumers/tenant-1/certificates/bulk-revoke',
      {
        consumer_ids: ['consumer-1'],
      }
    );
  });
});
