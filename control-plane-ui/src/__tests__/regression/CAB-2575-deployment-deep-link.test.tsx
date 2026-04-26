import { describe, expect, it, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { ApiDeploymentsDashboard } from '../../pages/ApiDeployments/ApiDeploymentsDashboard';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const envMock = vi.hoisted(() => ({
  activeEnvironment: 'dev',
  switchEnvironment: vi.fn(),
}));

vi.mock('../../contexts/EnvironmentContext', () => ({
  useEnvironment: () => ({
    activeEnvironment: envMock.activeEnvironment,
    switchEnvironment: envMock.switchEnvironment,
    environments: [
      { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
      { name: 'staging', label: 'Staging', mode: 'full', color: 'amber' },
      { name: 'prod', label: 'Production', mode: 'read-only', color: 'red' },
    ],
  }),
}));

const mockGetGatewayDeployments = vi.fn().mockResolvedValue({ items: [], total: 0 });
const mockGetDeploymentStatusSummary = vi.fn().mockResolvedValue({
  synced: 0,
  pending: 0,
  drifted: 0,
  error: 0,
  syncing: 0,
  deleting: 0,
  total: 0,
});
const mockDeployDialog = vi.hoisted(() => vi.fn());

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

vi.mock('../../pages/GatewayDeployments/DeployAPIDialog', () => ({
  DeployAPIDialog: (props: { preselectedApiKey?: string; preselectedEnvironment?: string }) => {
    mockDeployDialog(props);
    return <div data-testid="deploy-dialog">Deploy Dialog</div>;
  },
}));

vi.mock('../../components/SubNav', () => ({
  SubNav: () => <nav data-testid="sub-nav" />,
}));

vi.mock('../../components/SyncStatusBadge', () => ({
  SyncStatusBadge: ({ status }: { status: string }) => <span>{status}</span>,
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(false), null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title?: string }) => <div data-testid="empty-state">{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  TableSkeleton: () => <div data-testid="table-skeleton" />,
}));

vi.mock('@stoa/shared/components/StatCard', () => ({
  StatCard: ({ label, value }: { label: string; value: number }) => (
    <div>
      {label}: {value}
    </div>
  ),
}));

describe('regression/CAB-2575', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    envMock.activeEnvironment = 'dev';
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetGatewayDeployments.mockResolvedValue({ items: [], total: 0 });
    mockGetDeploymentStatusSummary.mockResolvedValue({
      synced: 0,
      pending: 0,
      drifted: 0,
      error: 0,
      syncing: 0,
      deleting: 0,
      total: 0,
    });
  });

  it('opens /api-deployments as a prefilled deployment workflow from the API catalog', async () => {
    renderWithProviders(<ApiDeploymentsDashboard />, {
      route:
        '/api-deployments?api_id=api-1&api_name=payment-api&environment=staging&open_deploy=true&tenant_id=oasis-gunters',
    });

    expect(await screen.findByTestId('deploy-dialog')).toBeInTheDocument();
    expect(mockDeployDialog).toHaveBeenCalledWith(
      expect.objectContaining({
        preselectedApiKey: 'oasis-gunters:payment-api',
        preselectedEnvironment: 'staging',
      })
    );
    expect(envMock.switchEnvironment).toHaveBeenCalledWith('staging');
    await waitFor(() => {
      expect(mockGetGatewayDeployments).toHaveBeenCalledWith(
        expect.objectContaining({ environment: 'staging' })
      );
    });
  });
});
