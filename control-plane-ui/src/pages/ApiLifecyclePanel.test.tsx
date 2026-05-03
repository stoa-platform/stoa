import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../test/helpers';
import { ApiLifecyclePanel } from './ApiLifecyclePanel';

vi.mock('../services/api', () => ({
  apiService: {
    getApiLifecycleState: vi.fn(),
    validateLifecycleDraft: vi.fn(),
    deployLifecycleApi: vi.fn(),
    publishLifecycleApi: vi.fn(),
    promoteLifecycleApi: vi.fn(),
  },
}));

const { apiService } = await import('../services/api');

const baseLifecycleState = {
  catalog_id: 'api-1',
  tenant_id: 'tenant-1',
  api_id: 'payments-api',
  api_name: 'payments-api',
  display_name: 'Payments API',
  version: '1.0.0',
  description: 'Payments',
  backend_url: 'https://payments.internal',
  catalog_status: 'draft',
  lifecycle_phase: 'draft',
  portal_published: false,
  tags: [],
  spec: {
    source: 'inline',
    has_openapi_spec: true,
  },
  deployments: [],
  promotions: [],
  last_error: null,
  portal: {
    published: false,
    status: 'not_published',
    publications: [],
    last_result: null,
    last_environment: null,
    last_gateway_instance_id: null,
    last_deployment_id: null,
    last_published_at: null,
  },
};

function renderPanel(canManage = true, canDeploy = true) {
  return renderWithProviders(
    <ApiLifecyclePanel
      tenantId="tenant-1"
      apiId="payments-api"
      canManage={canManage}
      canDeploy={canDeploy}
    />
  );
}

describe('ApiLifecyclePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiService.getApiLifecycleState).mockResolvedValue(baseLifecycleState);
  });

  it('renders draft lifecycle state', async () => {
    renderPanel();

    expect(await screen.findByTestId('api-lifecycle-panel')).toBeInTheDocument();
    expect(await screen.findByText('No gateway deployment')).toBeInTheDocument();
    expect(screen.getByTestId('api-lifecycle-catalog-status')).toHaveTextContent('draft');
  });

  it('validates a draft and refreshes state', async () => {
    const readyState = { ...baseLifecycleState, catalog_status: 'ready', lifecycle_phase: 'ready' };
    vi.mocked(apiService.validateLifecycleDraft).mockResolvedValue({
      tenant_id: 'tenant-1',
      api_id: 'payments-api',
      status: 'ready',
      validation: {
        valid: true,
        code: 'validated',
        message: 'OpenAPI spec is valid',
        spec_source: 'inline',
        path_count: 1,
        operation_count: 1,
      },
      lifecycle: readyState,
    });
    vi.mocked(apiService.getApiLifecycleState).mockResolvedValueOnce(baseLifecycleState);
    vi.mocked(apiService.getApiLifecycleState).mockResolvedValueOnce(readyState);

    renderPanel();

    await userEvent.click(await screen.findByTestId('api-lifecycle-validate'));

    await waitFor(() => {
      expect(apiService.validateLifecycleDraft).toHaveBeenCalledWith('tenant-1', 'payments-api');
    });
    expect(await screen.findByTestId('api-lifecycle-action-message')).toHaveTextContent(
      'validated'
    );
  });

  it('shows backend deployment errors clearly', async () => {
    vi.mocked(apiService.getApiLifecycleState).mockResolvedValue({
      ...baseLifecycleState,
      catalog_status: 'ready',
      lifecycle_phase: 'ready',
    });
    vi.mocked(apiService.deployLifecycleApi).mockRejectedValue({
      response: { data: { detail: 'gateway target is ambiguous' } },
    });

    renderPanel();

    await userEvent.click(await screen.findByTestId('api-lifecycle-deploy'));

    expect(await screen.findByTestId('api-lifecycle-action-error')).toHaveTextContent(
      'gateway target is ambiguous'
    );
  });

  it('sends publication and promotion requests through lifecycle actions', async () => {
    const readyState = { ...baseLifecycleState, catalog_status: 'ready', lifecycle_phase: 'ready' };
    vi.mocked(apiService.getApiLifecycleState).mockResolvedValue(readyState);
    vi.mocked(apiService.publishLifecycleApi).mockResolvedValue({
      tenant_id: 'tenant-1',
      api_id: 'payments-api',
      environment: 'dev',
      gateway_instance_id: 'gw-1',
      deployment_id: 'dep-1',
      publication_status: 'published',
      portal_published: true,
      result: 'published',
      lifecycle: readyState,
    });
    vi.mocked(apiService.promoteLifecycleApi).mockResolvedValue({
      tenant_id: 'tenant-1',
      api_id: 'payments-api',
      promotion_id: 'promo-1',
      source_environment: 'dev',
      target_environment: 'staging',
      source_gateway_instance_id: 'gw-1',
      target_gateway_instance_id: 'gw-2',
      target_deployment_id: 'dep-2',
      promotion_status: 'promoting',
      deployment_status: 'pending',
      result: 'requested',
      lifecycle: readyState,
    });

    renderPanel();

    await userEvent.click(await screen.findByTestId('api-lifecycle-publish'));
    await waitFor(() => {
      expect(apiService.publishLifecycleApi).toHaveBeenCalledWith('tenant-1', 'payments-api', {
        environment: 'dev',
        gateway_instance_id: null,
        force: false,
      });
    });

    await userEvent.click(screen.getByTestId('api-lifecycle-promote'));
    await waitFor(() => {
      expect(apiService.promoteLifecycleApi).toHaveBeenCalledWith('tenant-1', 'payments-api', {
        source_environment: 'dev',
        target_environment: 'staging',
        source_gateway_instance_id: null,
        target_gateway_instance_id: null,
        force: false,
      });
    });
  });
});
