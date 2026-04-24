import { httpClient, path } from '../http';
import type {
  WorkflowInstance,
  WorkflowListResponse,
  WorkflowTemplate,
  WorkflowTemplateCreate,
  WorkflowTemplateListResponse,
  WorkflowTemplateUpdate,
} from '../../types';

export const workflowsClient = {
  async listTemplates(tenantId: string): Promise<WorkflowTemplateListResponse> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'workflows', 'templates')
    );
    return data;
  },

  async createTemplate(
    tenantId: string,
    payload: WorkflowTemplateCreate
  ): Promise<WorkflowTemplate> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'workflows', 'templates'),
      payload
    );
    return data;
  },

  async updateTemplate(
    tenantId: string,
    templateId: string,
    payload: WorkflowTemplateUpdate
  ): Promise<WorkflowTemplate> {
    const { data } = await httpClient.put(
      path('v1', 'tenants', tenantId, 'workflows', 'templates', templateId),
      payload
    );
    return data;
  },

  async deleteTemplate(tenantId: string, templateId: string): Promise<void> {
    await httpClient.delete(path('v1', 'tenants', tenantId, 'workflows', 'templates', templateId));
  },

  async listInstances(
    tenantId: string,
    params?: { status?: string; skip?: number; limit?: number }
  ): Promise<WorkflowListResponse> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'workflows', 'instances'),
      {
        params,
      }
    );
    return data;
  },

  async start(
    tenantId: string,
    payload: { template_id: string; subject_id: string; subject_email: string }
  ): Promise<WorkflowInstance> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'workflows', 'instances'),
      payload
    );
    return data;
  },

  async approveStep(
    tenantId: string,
    instanceId: string,
    payload: { comment?: string }
  ): Promise<WorkflowInstance> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'workflows', 'instances', instanceId, 'approve'),
      payload
    );
    return data;
  },

  async rejectStep(
    tenantId: string,
    instanceId: string,
    payload: { comment?: string }
  ): Promise<WorkflowInstance> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'workflows', 'instances', instanceId, 'reject'),
      payload
    );
    return data;
  },

  async seedTemplates(tenantId: string): Promise<{ message: string }> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'workflows', 'templates', 'seed')
    );
    return data;
  },
};
