import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetGatewayDeployments = vi.fn().mockResolvedValue({ items: [], total: 0 });
const mockGetDeploymentStatusSummary = vi.fn().mockResolvedValue({
  synced: 3,
  pending: 1,
  drifted: 0,
  error: 0,
  syncing: 0,
  deleting: 0,
  total: 4,
});

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayDeployments: (...args: unknown[]) => mockGetGatewayDeployments(...args),
    getDeploymentStatusSummary: (...args: unknown[]) => mockGetDeploymentStatusSummary(...args),
    forceSyncDeployment: vi.fn().mockResolvedValue(undefined),
    undeployFromGateway: vi.fn().mockResolvedValue(undefined),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

vi.mock('./DeployAPIDialog', () => ({
  DeployAPIDialog: () => <div data-testid="deploy-dialog">Deploy Dialog</div>,
}));

vi.mock('../../components/SyncStatusBadge', () => ({
  SyncStatusBadge: ({ status }: { status: string }) => <span>{status}</span>,
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(false), () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title?: string }) => <div data-testid="empty-state">{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  TableSkeleton: () => <div data-testid="table-skeleton" />,
}));

import { GatewayDeploymentsDashboard } from './GatewayDeploymentsDashboard';

describe('GatewayDeploymentsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', async () => {
    renderWithProviders(<GatewayDeploymentsDashboard />);
    expect(await screen.findByRole('heading', { name: /Gateway Deployments/ })).toBeInTheDocument();
  });

  it('renders Deploy API button', async () => {
    renderWithProviders(<GatewayDeploymentsDashboard />);
    expect(await screen.findByText(/Deploy API/)).toBeInTheDocument();
  });

  it('renders status summary values', async () => {
    renderWithProviders(<GatewayDeploymentsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('3')).toBeInTheDocument();
    });
  });

  it('shows empty state when no deployments', async () => {
    renderWithProviders(<GatewayDeploymentsDashboard />);
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('renders deployment data in table', async () => {
    mockGetGatewayDeployments.mockResolvedValue({
      items: [
        {
          id: 'deploy-1',
          api_catalog_id: 'api-1',
          gateway_instance_id: 'gw-1',
          sync_status: 'synced',
          sync_attempts: 1,
          desired_state: { api_name: 'Payment API' },
          desired_at: '2026-02-01T00:00:00Z',
          created_at: '2026-01-15T00:00:00Z',
          updated_at: '2026-02-01T00:00:00Z',
        },
      ],
      total: 1,
    });
    renderWithProviders(<GatewayDeploymentsDashboard />);
    await waitFor(() => {
      expect(screen.getByText('synced')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<GatewayDeploymentsDashboard />);
        expect(
          await screen.findByRole('heading', { name: /Gateway Deployments/ })
        ).toBeInTheDocument();
      });
    }
  );
});
