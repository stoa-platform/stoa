import { httpClient } from '../http';
import type { CommitInfo, MergeRequest } from '../../types';

export const gitClient = {
  async listCommits(tenantId: string, path?: string): Promise<CommitInfo[]> {
    const params = path ? { path } : {};
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/git/commits`, { params });
    return data;
  },

  async listMergeRequests(tenantId: string): Promise<MergeRequest[]> {
    const { data } = await httpClient.get(`/v1/tenants/${tenantId}/git/merge-requests`);
    return data;
  },
};
