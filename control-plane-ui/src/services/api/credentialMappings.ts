import { httpClient, path } from '../http';
import type { Schemas } from '@stoa/shared/api-types';
import type { CredentialMapping, CredentialMappingListResponse } from '../../types';

export const credentialMappingsClient = {
  async list(tenantId: string): Promise<CredentialMappingListResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'credential-mappings'));
    return data;
  },

  async create(
    tenantId: string,
    payload: Schemas['CredentialMappingCreate']
  ): Promise<CredentialMapping> {
    const { data } = await httpClient.post(path('v1', 'tenants', tenantId, 'credential-mappings'), payload);
    return data;
  },

  async update(
    tenantId: string,
    mappingId: string,
    payload: Schemas['CredentialMappingUpdate']
  ): Promise<CredentialMapping> {
    const { data } = await httpClient.put(
      path('v1', 'tenants', tenantId, 'credential-mappings', mappingId),
      payload
    );
    return data;
  },

  async remove(tenantId: string, mappingId: string): Promise<void> {
    await httpClient.delete(path('v1', 'tenants', tenantId, 'credential-mappings', mappingId));
  },
};
