import { httpClient, path } from '../http';
import type { Schemas } from '@stoa/shared/api-types';
import type { Promotion, PromotionListResponse } from '../../types';

export const promotionsClient = {
  async list(
    tenantId: string,
    params?: {
      api_id?: string;
      status?: string;
      target_environment?: string;
      page?: number;
      page_size?: number;
    }
  ): Promise<PromotionListResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'promotions'), { params });
    return data;
  },

  async get(tenantId: string, promotionId: string): Promise<Promotion> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'promotions', promotionId));
    return data;
  },

  async create(
    tenantId: string,
    apiId: string,
    request: Schemas['PromotionCreate']
  ): Promise<Promotion> {
    const { data } = await httpClient.post(path('v1', 'tenants', tenantId, 'promotions', apiId), request);
    return data;
  },

  async approve(tenantId: string, promotionId: string): Promise<Promotion> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'promotions', promotionId, 'approve')
    );
    return data;
  },

  async complete(tenantId: string, promotionId: string): Promise<Promotion> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'promotions', promotionId, 'complete')
    );
    return data;
  },

  async rollback(
    tenantId: string,
    promotionId: string,
    request: Schemas['PromotionRollbackRequest']
  ): Promise<Promotion> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'promotions', promotionId, 'rollback'),
      request
    );
    return data;
  },

  async getDiff(tenantId: string, promotionId: string): Promise<Schemas['PromotionDiffResponse']> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'promotions', promotionId, 'diff'));
    return data;
  },
};
