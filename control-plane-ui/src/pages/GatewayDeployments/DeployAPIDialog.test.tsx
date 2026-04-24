import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetCatalogEntries = vi
  .fn()
  .mockResolvedValue([
    { id: 'cat-1', api_name: 'Payment API', tenant_id: 'oasis-gunters', version: '1.0.0' },
  ]);

const mockGetTenants = vi.fn().mockResolvedValue([{ id: 'oasis-gunters', name: 'Oasis Gunters' }]);

const mockGetGatewayInstances = vi.fn().mockResolvedValue({
  items: [
    {
      id: 'gw-1',
      name: 'stoa-edge',
      display_name: 'STOA Edge MCP',
      gateway_type: 'stoa_edge_mcp',
      environment: 'dev',
    },
  ],
});
const mockGetApis = vi.fn().mockResolvedValue([]);
const mockGetGatewayDeployments = vi.fn().mockResolvedValue({ items: [] });
const mockGetDeployableEnvironments = vi.fn().mockResolvedValue({
  environments: [{ environment: 'dev', deployable: true, promotion_status: 'not_required' }],
});
const mockDeployApiToEnv = vi.fn().mockResolvedValue({
  deployed: 1,
  environment: 'dev',
  deployment_ids: ['dep-1'],
});

vi.mock('../../services/api', () => ({
  apiService: {
    getCatalogEntries: (...args: unknown[]) => mockGetCatalogEntries(...args),
    getTenants: (...args: unknown[]) => mockGetTenants(...args),
    getGatewayInstances: (...args: unknown[]) => mockGetGatewayInstances(...args),
    getApis: (...args: unknown[]) => mockGetApis(...args),
    getGatewayDeployments: (...args: unknown[]) => mockGetGatewayDeployments(...args),
    getDeployableEnvironments: (...args: unknown[]) => mockGetDeployableEnvironments(...args),
    deployApiToEnv: (...args: unknown[]) => mockDeployApiToEnv(...args),
    deployApiToGateways: vi.fn().mockResolvedValue(undefined),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

import { DeployAPIDialog } from './DeployAPIDialog';

describe('DeployAPIDialog', () => {
  const onClose = vi.fn();
  const onDeployed = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetCatalogEntries.mockResolvedValue([
      { id: 'cat-1', api_name: 'Payment API', tenant_id: 'oasis-gunters', version: '1.0.0' },
    ]);
    mockGetTenants.mockResolvedValue([{ id: 'oasis-gunters', name: 'Oasis Gunters' }]);
    mockGetGatewayInstances.mockResolvedValue({
      items: [
        {
          id: 'gw-1',
          name: 'stoa-edge',
          display_name: 'STOA Edge MCP',
          gateway_type: 'stoa_edge_mcp',
          environment: 'dev',
        },
      ],
    });
    mockGetApis.mockResolvedValue([]);
    mockGetGatewayDeployments.mockResolvedValue({ items: [] });
    mockGetDeployableEnvironments.mockResolvedValue({
      environments: [{ environment: 'dev', deployable: true, promotion_status: 'not_required' }],
    });
    mockDeployApiToEnv.mockResolvedValue({
      deployed: 1,
      environment: 'dev',
      deployment_ids: ['dep-1'],
    });
  });

  it('renders the dialog title', async () => {
    render(<DeployAPIDialog onClose={onClose} onDeployed={onDeployed} />);
    expect(await screen.findByText(/Deploy API to Gateways/i)).toBeInTheDocument();
  });

  it('renders cancel button', async () => {
    render(<DeployAPIDialog onClose={onClose} onDeployed={onDeployed} />);
    await screen.findByText(/Deploy API to Gateways/i);
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('shows error when every initial load endpoint fails (allSettled)', async () => {
    // After P1-1 (allSettled), a single-endpoint failure no longer
    // short-circuits the dialog. The error banner only renders when every
    // init endpoint rejects.
    mockGetCatalogEntries.mockRejectedValue(new Error('Failed'));
    mockGetTenants.mockRejectedValue(new Error('Failed'));
    mockGetGatewayInstances.mockRejectedValue(new Error('Failed'));
    render(<DeployAPIDialog onClose={onClose} onDeployed={onDeployed} />);
    await waitFor(() => {
      expect(screen.getByText(/failed/i)).toBeInTheDocument();
    });
  });

  it('clears selected gateways when environment changes and accepts prod/production aliases', async () => {
    mockGetApis.mockResolvedValue([
      { id: 'api-1', name: 'payments', version: '1.0.0', tenant_id: 'oasis-gunters' },
    ]);
    mockGetGatewayInstances.mockResolvedValue({
      items: [
        {
          id: 'gw-dev',
          name: 'stoa-dev',
          display_name: 'STOA Dev',
          gateway_type: 'stoa_edge_mcp',
          environment: 'dev',
        },
        {
          id: 'gw-prod',
          name: 'stoa-prod',
          display_name: 'STOA Prod',
          gateway_type: 'stoa_edge_mcp',
          environment: 'prod',
        },
      ],
    });
    mockGetDeployableEnvironments.mockResolvedValue({
      environments: [
        { environment: 'dev', deployable: true, promotion_status: 'not_required' },
        { environment: 'production', deployable: true, promotion_status: 'promoted' },
      ],
    });

    render(<DeployAPIDialog onClose={onClose} onDeployed={onDeployed} />);

    const apiSelect = (await screen.findAllByRole('combobox'))[0];
    fireEvent.change(apiSelect, { target: { value: 'payments' } });

    expect(await screen.findByText('STOA Dev')).toBeInTheDocument();
    const devInput = screen.getByText('STOA Dev').closest('label')?.querySelector('input');
    expect(devInput).toBeTruthy();
    fireEvent.click(devInput as HTMLInputElement);
    expect(screen.getByRole('button', { name: /Deploy to 1 gateway/ })).toBeEnabled();

    const environmentSelect = (await screen.findAllByRole('combobox'))[1];
    fireEvent.change(environmentSelect, {
      target: { value: 'production' },
    });

    expect(await screen.findByText('STOA Prod')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Deploy to 0 gateways/ })).toBeDisabled();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the dialog', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<DeployAPIDialog onClose={onClose} onDeployed={onDeployed} />);
        expect(await screen.findByText(/Deploy API to Gateways/i)).toBeInTheDocument();
      });
    }
  );
});
