import { httpClient, path } from '../http';

export type ApiLifecycleSpecDocument = Record<string, unknown>;

export interface ApiLifecycleCreateDraftRequest {
  name: string;
  display_name: string;
  version: string;
  description?: string;
  backend_url: string;
  openapi_spec?: string | ApiLifecycleSpecDocument | null;
  spec_reference?: string | null;
  tags?: string[];
  owner_team?: string | null;
}

export interface ApiLifecycleValidationResult {
  valid: boolean;
  code: string;
  message: string;
  spec_source: string;
  spec_format?: string | null;
  spec_version?: string | null;
  title?: string | null;
  version?: string | null;
  path_count: number;
  operation_count: number;
  validated_at?: string | null;
}

export interface ApiLifecycleSpecState {
  source: string;
  has_openapi_spec: boolean;
  git_path?: string | null;
  git_commit_sha?: string | null;
  reference?: string | null;
  fallback_reason?: string | null;
}

export interface ApiLifecycleSyncStep {
  name: string;
  status: string;
  detail?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface ApiLifecycleGatewayDeployment {
  id: string;
  environment: string;
  gateway_instance_id: string;
  gateway_name: string;
  gateway_type: string;
  sync_status: string;
  desired_generation: number;
  synced_generation: number;
  gateway_resource_id?: string | null;
  public_url?: string | null;
  sync_error?: string | null;
  last_sync_attempt?: string | null;
  last_sync_success?: string | null;
  policy_sync_status?: string | null;
  policy_sync_error?: string | null;
  sync_steps?: ApiLifecycleSyncStep[];
}

export interface ApiLifecyclePromotion {
  id: string;
  source_environment: string;
  target_environment: string;
  status: string;
  message: string;
  requested_by: string;
  approved_by?: string | null;
  completed_at?: string | null;
  source_deployment_id?: string | null;
  target_deployment_id?: string | null;
  target_gateway_ids?: string[];
}

export interface ApiLifecyclePortalPublication {
  environment: string;
  gateway_instance_id: string;
  deployment_id: string;
  publication_status: string;
  result: string;
  spec_hash: string;
  published_at: string;
}

export interface ApiLifecyclePortalState {
  published: boolean;
  status: string;
  publications: ApiLifecyclePortalPublication[];
  last_result?: string | null;
  last_environment?: string | null;
  last_gateway_instance_id?: string | null;
  last_deployment_id?: string | null;
  last_published_at?: string | null;
}

export interface ApiLifecycleState {
  catalog_id: string;
  tenant_id: string;
  api_id: string;
  api_name: string;
  display_name: string;
  version: string;
  description: string;
  backend_url: string;
  catalog_status: string;
  lifecycle_phase: string;
  portal_published: boolean;
  tags: string[];
  spec: ApiLifecycleSpecState;
  deployments: ApiLifecycleGatewayDeployment[];
  promotions: ApiLifecyclePromotion[];
  last_error?: string | null;
  portal: ApiLifecyclePortalState;
}

export interface ApiLifecycleValidateDraftRequest {
  reason?: string | null;
}

export interface ApiLifecycleValidateDraftResponse {
  tenant_id: string;
  api_id: string;
  status: string;
  validation: ApiLifecycleValidationResult;
  lifecycle: ApiLifecycleState;
}

export interface ApiLifecycleDeploymentRequest {
  environment: string;
  gateway_instance_id?: string | null;
  force?: boolean;
}

export interface ApiLifecycleDeployResponse {
  tenant_id: string;
  api_id: string;
  environment: string;
  gateway_instance_id: string;
  deployment_id: string;
  deployment_status: string;
  action: string;
  lifecycle: ApiLifecycleState;
}

export interface ApiLifecyclePublicationRequest {
  environment: string;
  gateway_instance_id?: string | null;
  force?: boolean;
}

export interface ApiLifecyclePublishResponse {
  tenant_id: string;
  api_id: string;
  environment: string;
  gateway_instance_id: string;
  deployment_id: string;
  publication_status: string;
  portal_published: boolean;
  result: string;
  lifecycle: ApiLifecycleState;
}

export interface ApiLifecyclePromotionRequest {
  source_environment: string;
  target_environment: string;
  source_gateway_instance_id?: string | null;
  target_gateway_instance_id?: string | null;
  force?: boolean;
}

export interface ApiLifecyclePromotionResponse {
  tenant_id: string;
  api_id: string;
  promotion_id: string;
  source_environment: string;
  target_environment: string;
  source_gateway_instance_id: string;
  target_gateway_instance_id: string;
  target_deployment_id: string;
  promotion_status: string;
  deployment_status: string;
  result: string;
  lifecycle: ApiLifecycleState;
}

export const apiLifecycleClient = {
  async createDraft(
    tenantId: string,
    request: ApiLifecycleCreateDraftRequest
  ): Promise<ApiLifecycleState> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'apis', 'lifecycle', 'drafts'),
      request
    );
    return data;
  },

  async getState(tenantId: string, apiId: string): Promise<ApiLifecycleState> {
    const { data } = await httpClient.get(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'lifecycle')
    );
    return data;
  },

  async validateDraft(
    tenantId: string,
    apiId: string,
    request: ApiLifecycleValidateDraftRequest = {}
  ): Promise<ApiLifecycleValidateDraftResponse> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'lifecycle', 'validate'),
      request
    );
    return data;
  },

  async deploy(
    tenantId: string,
    apiId: string,
    request: ApiLifecycleDeploymentRequest
  ): Promise<ApiLifecycleDeployResponse> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'lifecycle', 'deployments'),
      request
    );
    return data;
  },

  async publish(
    tenantId: string,
    apiId: string,
    request: ApiLifecyclePublicationRequest
  ): Promise<ApiLifecyclePublishResponse> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'lifecycle', 'publications'),
      request
    );
    return data;
  },

  async promote(
    tenantId: string,
    apiId: string,
    request: ApiLifecyclePromotionRequest
  ): Promise<ApiLifecyclePromotionResponse> {
    const { data } = await httpClient.post(
      path('v1', 'tenants', tenantId, 'apis', apiId, 'lifecycle', 'promotions'),
      request
    );
    return data;
  },
};
