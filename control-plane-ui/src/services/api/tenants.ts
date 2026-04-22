import { httpClient } from '../http';
import type { Schemas } from '@stoa/shared/api-types';
import type {
  Tenant,
  TenantCreate,
  TenantCAInfo,
  IssuedCertificateListResponse,
} from '../../types';

export const tenantsClient = {
  async list(): Promise<Tenant[]> {
    const { data } = await httpClient.get('/v1/tenants');
    return data;
  },

  async get(tenantId: string): Promise<Tenant> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}`);
    return data;
  },

  async create(tenant: TenantCreate): Promise<Tenant> {
    const { data } = await httpClient.post('/v1/tenants', tenant);
    return data;
  },

  async update(tenantId: string, patch: Partial<TenantCreate>): Promise<Tenant> {
    const { data } = await httpClient.put(`/v1/tenants/${tenantId}`, patch);
    return data;
  },

  async remove(tenantId: string): Promise<void> {
    await httpClient.delete(`/v1/tenants/${tenantId}`);
  },

  // Tenant CA (CAB-1787/1788)
  async getCA(tenantId: string): Promise<TenantCAInfo> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/ca`);
    return data;
  },

  async generateCA(tenantId: string): Promise<TenantCAInfo> {
    const { data } = await httpClient.post(`/v1/tenants/${tenantId}/ca/generate`);
    return data;
  },

  async signCSR(
    tenantId: string,
    csrPem: string,
    validityDays: number = 365
  ): Promise<Schemas['CSRSignResponse']> {
    const { data } = await httpClient.post(`/v1/tenants/${tenantId}/ca/sign`, {
      csr_pem: csrPem,
      validity_days: validityDays,
    });
    return data;
  },

  async revokeCA(tenantId: string): Promise<void> {
    await httpClient.delete(`/v1/tenants/${tenantId}/ca`);
  },

  async listIssuedCertificates(
    tenantId: string,
    status?: string
  ): Promise<IssuedCertificateListResponse> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/ca/certificates`, {
      params: status ? { status } : undefined,
    });
    return data;
  },

  async revokeIssuedCertificate(tenantId: string, certId: string): Promise<void> {
    await httpClient.post(`/v1/tenants/${tenantId}/ca/certificates/${certId}/revoke`);
  },
};
