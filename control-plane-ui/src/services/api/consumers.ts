import { httpClient, path, extractList } from '../http';
import type { Schemas } from '@stoa/shared/api-types';
import type { Consumer } from '../../types';

export const consumersClient = {
  async list(tenantId: string, environment?: string): Promise<Consumer[]> {
    const { data } = await httpClient.get(path('v1', 'consumers', tenantId), {
      params: { page: 1, page_size: 100, environment },
    });
    return extractList<Consumer>(data, 'consumers');
  },

  async get(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await httpClient.get(path('v1', 'consumers', tenantId, consumerId));
    return data;
  },

  async suspend(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await httpClient.post(
      path('v1', 'consumers', tenantId, consumerId, 'suspend')
    );
    return data;
  },

  async activate(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await httpClient.post(
      path('v1', 'consumers', tenantId, consumerId, 'activate')
    );
    return data;
  },

  async remove(tenantId: string, consumerId: string): Promise<void> {
    await httpClient.delete(path('v1', 'consumers', tenantId, consumerId));
  },

  async rotateCertificate(
    tenantId: string,
    consumerId: string,
    certificatePem: string,
    gracePeriodHours: number = 24
  ): Promise<Consumer> {
    const { data } = await httpClient.post(
      path('v1', 'consumers', tenantId, consumerId, 'certificate', 'rotate'),
      { certificate_pem: certificatePem, grace_period_hours: gracePeriodHours }
    );
    return data;
  },

  async revokeCertificate(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await httpClient.post(
      path('v1', 'consumers', tenantId, consumerId, 'certificate', 'revoke')
    );
    return data;
  },

  async block(tenantId: string, consumerId: string): Promise<Consumer> {
    const { data } = await httpClient.post(path('v1', 'consumers', tenantId, consumerId, 'block'));
    return data;
  },

  // Certificate Lifecycle (CAB-872)
  async bindCertificate(
    tenantId: string,
    consumerId: string,
    certificatePem: string
  ): Promise<Consumer> {
    const { data } = await httpClient.post(
      path('v1', 'consumers', tenantId, consumerId, 'certificate'),
      {
        certificate_pem: certificatePem,
      }
    );
    return data;
  },

  async getExpiringCertificates(
    tenantId: string,
    days: number = 30
  ): Promise<Schemas['CertificateExpiryResponse']> {
    const { data } = await httpClient.get(
      path('v1', 'consumers', tenantId, 'certificates', 'expiring'),
      {
        params: { days },
      }
    );
    return data;
  },

  async bulkRevokeCertificates(
    tenantId: string,
    consumerIds: string[]
  ): Promise<Schemas['BulkRevokeResponse']> {
    const { data } = await httpClient.post(
      path('v1', 'consumers', tenantId, 'certificates', 'bulk-revoke'),
      {
        consumer_ids: consumerIds,
      }
    );
    return data;
  },
};
