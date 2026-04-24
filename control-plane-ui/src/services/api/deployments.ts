import { httpClient, path } from '../http';
import type {
  Deployment,
  DeploymentCreate,
  DeploymentListResponse,
  DeploymentLogListResponse,
  EnvironmentStatusResponse,
} from '../../types';

export const deploymentsClient = {
  // Lifecycle (CAB-1353)
  async list(
    tenantId: string,
    params?: {
      api_id?: string;
      environment?: string;
      status?: string;
      page?: number;
      page_size?: number;
    }
  ): Promise<DeploymentListResponse> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'deployments'), { params });
    return data;
  },

  async get(tenantId: string, deploymentId: string): Promise<Deployment> {
    const { data } = await httpClient.get(path('v1', 'tenants', tenantId, 'deployments', deploymentId));
    return data;
  },

  async create(tenantId: string, request: DeploymentCreate): Promise<Deployment> {
    const { data } = await httpClient.post(path('v1', 'tenants', tenantId, 'deployments'), request);
    return data;
  },

  async rollback(
    tenantId: string,
    deploymentId: string,
    targetVersion?: string
  ): Promise<Deployment> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'deployments', deploymentId, 'rollback'),
      { target_version: targetVersion }
    );
    return data;
  },

  async getLogs(
    tenantId: string,
    deploymentId: string,
    afterSeq: number = 0,
    limit: number = 200
  ): Promise<DeploymentLogListResponse> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'deployments', deploymentId, 'logs'),
      { params: { after_seq: afterSeq, limit } }
    );
    return data;
  },

  // Environment status
  async getEnvironmentStatus(
    tenantId: string,
    environment: string
  ): Promise<EnvironmentStatusResponse> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'deployments', 'environments', environment, 'status')
    );
    return data;
  },

  // API Deployment Orchestration (CAB-1888)
  async getDeployableEnvironments(
    tenantId: string,
    apiId: string
  ): Promise<{
    environments: {
      environment: string;
      deployable: boolean;
      promotion_status: string;
    }[];
  }> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'deployable-environments')
    );
    return data;
  },

  async deployApiToEnv(
    tenantId: string,
    apiId: string,
    payload: { environment: string; gateway_ids?: string[] }
  ): Promise<{ deployed: number; environment: string; deployment_ids: string[] }> {
    const { data } = await httpClient.post(path('v1', 'tenants', tenantId, 'apis', apiId, 'deploy'), payload);
    return data;
  },

  async getApiGatewayAssignments(
    tenantId: string,
    apiId: string,
    environment?: string
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ): Promise<{ items: any[]; total: number }> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'gateway-assignments'),
      { params: environment ? { environment } : {} }
    );
    return data;
  },

  async createApiGatewayAssignment(
    tenantId: string,
    apiId: string,
    payload: { gateway_id: string; environment: string; auto_deploy: boolean }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ): Promise<any> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'gateway-assignments'),
      payload
    );
    return data;
  },

  async deleteApiGatewayAssignment(
    tenantId: string,
    apiId: string,
    assignmentId: string
  ): Promise<void> {
    await httpClient.delete(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'gateway-assignments', assignmentId)
    );
  },
};
