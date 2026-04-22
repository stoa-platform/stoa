import { httpClient } from '../http';
import type { EnvironmentConfig } from '../../types';

export interface MeResponse {
  roles: string[];
  permissions: string[];
  role_display_names?: Record<string, string>;
  tenant_id?: string;
}

export const sessionClient = {
  async getMe(): Promise<MeResponse> {
    const { data } = await httpClient.get<MeResponse>('/v1/me');
    return data;
  },

  async listEnvironments(): Promise<EnvironmentConfig[]> {
    const { data } = await httpClient.get('/v1/environments');
    return data.environments;
  },
};
