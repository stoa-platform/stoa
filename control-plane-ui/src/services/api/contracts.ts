import { httpClient, path } from '../http';
import type { Schemas } from '@stoa/shared/api-types';
import type {
  Contract,
  ContractCreate,
  ContractListResponse,
  ProtocolBinding,
  PublishContractResponse,
} from '../../types';

export const contractsClient = {
  async list(tenantId: string): Promise<ContractListResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'contracts'));
    return data;
  },

  async get(tenantId: string, contractId: string): Promise<Contract> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'contracts', contractId));
    return data;
  },

  async create(tenantId: string, payload: ContractCreate): Promise<Contract> {
    const { data } = await httpClient.post(path('v1', 'tenants', tenantId, 'contracts'), payload);
    return data;
  },

  async publish(tenantId: string, contractId: string): Promise<PublishContractResponse> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'contracts', contractId, 'publish')
    );
    return data;
  },

  async update(
    tenantId: string,
    contractId: string,
    payload: Schemas['ContractUpdate']
  ): Promise<Contract> {
    const { data } = await httpClient.patch(
      path('v1', 'tenants', tenantId, 'contracts', contractId),
      payload
    );
    return data;
  },

  async remove(tenantId: string, contractId: string): Promise<void> {
    await httpClient.delete(path('v1', 'tenants', tenantId, 'contracts', contractId));
  },

  async listBindings(tenantId: string, contractId: string): Promise<ProtocolBinding[]> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'contracts', contractId, 'bindings')
    );
    return data;
  },

  async enableBinding(
    tenantId: string,
    contractId: string,
    protocol: string
  ): Promise<ProtocolBinding> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'contracts', contractId, 'bindings'),
      { protocol }
    );
    return data;
  },

  async disableBinding(tenantId: string, contractId: string, protocol: string): Promise<void> {
    await httpClient.delete(
      path('v1', 'tenants', tenantId, 'contracts', contractId, 'bindings', protocol)
    );
  },
};
