import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetCatalogEntries = vi
  .fn()
  .mockResolvedValue([
    { id: 'cat-1', api_name: 'Payment API', tenant_id: 'oasis-gunters', version: '1.0.0' },
  ]);

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

vi.mock('../../services/api', () => ({
  apiService: {
    getCatalogEntries: (...args: unknown[]) => mockGetCatalogEntries(...args),
    getGatewayInstances: (...args: unknown[]) => mockGetGatewayInstances(...args),
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
  });

  it('renders the dialog title', async () => {
    render(<DeployAPIDialog onClose={onClose} onDeployed={onDeployed} />);
    expect(await screen.findByText(/Deploy API to Gateways/i)).toBeInTheDocument();
  });

  it('renders target gateways after loading', async () => {
    render(<DeployAPIDialog onClose={onClose} onDeployed={onDeployed} />);
    expect(await screen.findByText('STOA Edge MCP')).toBeInTheDocument();
  });

  it('renders cancel and deploy buttons', async () => {
    render(<DeployAPIDialog onClose={onClose} onDeployed={onDeployed} />);
    await screen.findByText(/Deploy API to Gateways/i);
    expect(screen.getByText('Cancel')).toBeInTheDocument();
    expect(screen.getByText('Deploy')).toBeInTheDocument();
  });

  it('shows error when API load fails', async () => {
    mockGetCatalogEntries.mockRejectedValue(new Error('Failed'));
    render(<DeployAPIDialog onClose={onClose} onDeployed={onDeployed} />);
    await waitFor(() => {
      expect(screen.getByText(/failed/i)).toBeInTheDocument();
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
