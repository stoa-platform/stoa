import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetGatewayHealthSummary = vi
  .fn()
  .mockResolvedValue({ online: 3, offline: 0, degraded: 0 });
const mockGetGatewayInstances = vi.fn().mockResolvedValue({
  items: [
    {
      id: '1',
      name: 'gw-1',
      display_name: 'STOA Gateway (edge-mcp)',
      gateway_type: 'stoa',
      mode: 'edge-mcp',
      status: 'online',
      capabilities: ['oidc', 'mtls'],
    },
    {
      id: '2',
      name: 'gw-2',
      display_name: 'STOA Gateway (sidecar)',
      gateway_type: 'stoa',
      mode: 'sidecar',
      status: 'online',
      capabilities: ['oidc'],
    },
  ],
});

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayHealthSummary: (...args: unknown[]) => mockGetGatewayHealthSummary(...args),
    getGatewayInstances: (...args: unknown[]) => mockGetGatewayInstances(...args),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

import { GatewaySecurityDashboard } from './GatewaySecurityDashboard';

describe('GatewaySecurityDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetGatewayHealthSummary.mockResolvedValue({ online: 3, offline: 0, degraded: 0 });
    mockGetGatewayInstances.mockResolvedValue({
      items: [
        {
          id: '1',
          name: 'gw-1',
          display_name: 'STOA Gateway',
          gateway_type: 'stoa',
          mode: 'edge-mcp',
          status: 'online',
          capabilities: ['oidc'],
        },
      ],
    });
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', async () => {
    renderWithProviders(<GatewaySecurityDashboard />);
    expect(await screen.findByRole('heading', { name: /Gateway Security/i })).toBeInTheDocument();
  });

  it('renders security cards', async () => {
    renderWithProviders(<GatewaySecurityDashboard />);
    expect(await screen.findByText('Gateway Health')).toBeInTheDocument();
    expect(screen.getByText('OAuth/OIDC')).toBeInTheDocument();
    expect(screen.getByText('mTLS Capable')).toBeInTheDocument();
    expect(screen.getByText('RBAC')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<GatewaySecurityDashboard />);
        expect(
          await screen.findByRole('heading', { name: /Gateway Security/i })
        ).toBeInTheDocument();
      });
    }
  );
});
