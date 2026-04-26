import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const envMock = vi.hoisted(() => ({
  activeEnvironment: 'prod',
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

vi.mock('../GatewayDeployments/DeployAPIDialog', () => ({
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

import { ApiDeploymentsDashboard } from './ApiDeploymentsDashboard';

describe('ApiDeploymentsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    envMock.activeEnvironment = 'prod';
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
    mockDeployDialog.mockClear();
  });

  it('uses the global environment as the default runtime filter', async () => {
    renderWithProviders(<ApiDeploymentsDashboard />);

    await waitFor(() => {
      expect(mockGetGatewayDeployments).toHaveBeenCalledWith({
        page: 1,
        page_size: 20,
        environment: 'production',
      });
    });
  });

  it('keeps the page filter and global environment selector in sync', async () => {
    renderWithProviders(<ApiDeploymentsDashboard />);

    fireEvent.change(await screen.findByDisplayValue('Production'), {
      target: { value: 'staging' },
    });

    expect(envMock.switchEnvironment).toHaveBeenCalledWith('staging');
    await waitFor(() => {
      expect(mockGetGatewayDeployments).toHaveBeenCalledWith({
        page: 1,
        page_size: 20,
        environment: 'staging',
      });
    });
  });

  it('opens the deployment workflow prefilled from /apis query params', async () => {
    renderWithProviders(<ApiDeploymentsDashboard />, {
      route:
        '/api-deployments?api_id=api-1&api_name=payment-api&environment=staging&open_deploy=true&tenant_id=oasis-gunters',
    });

    expect(await screen.findByTestId('deploy-dialog')).toBeInTheDocument();
    expect(screen.getByText(/Deployment workflow loaded for/)).toBeInTheDocument();
    expect(mockDeployDialog).toHaveBeenCalledWith(
      expect.objectContaining({
        preselectedApiKey: 'oasis-gunters:payment-api',
        preselectedEnvironment: 'staging',
      })
    );
    expect(envMock.switchEnvironment).toHaveBeenCalledWith('staging');
    await waitFor(() => {
      expect(mockGetGatewayDeployments).toHaveBeenCalledWith({
        page: 1,
        page_size: 20,
        environment: 'staging',
      });
    });
  });

  it('renders runtime sync status and last sync from GatewayDeployment fields', async () => {
    mockGetGatewayDeployments.mockResolvedValue({
      items: [
        {
          id: 'dep-1',
          api_catalog_id: 'api-1',
          gateway_instance_id: 'gw-1',
          desired_state: { api_name: 'Payments' },
          desired_source: 'db_shortcut',
          git_sync_status: 'missing_commit',
          desired_commit_sha: undefined,
          desired_git_path: 'tenants/oasis-gunters/apis/Payments',
          desired_at: '2026-04-25T10:00:00Z',
          actual_state: { api_name: 'Payments' },
          sync_status: 'synced',
          last_sync_success: '2026-04-25T10:01:00Z',
          sync_attempts: 1,
          created_at: '2026-04-25T10:00:00Z',
          updated_at: '2026-04-25T10:01:00Z',
          gateway_name: 'stoa-prod',
          gateway_environment: 'production',
        },
      ],
      total: 1,
    });

    renderWithProviders(<ApiDeploymentsDashboard />);

    expect(await screen.findByText('Payments')).toBeInTheDocument();
    expect(screen.getByText('synced')).toBeInTheDocument();
    expect(screen.getByText('db_shortcut/missing_commit')).toBeInTheDocument();
    expect(screen.getByText('No Git commit')).toBeInTheDocument();
    expect(screen.getByText(/2026/)).toBeInTheDocument();
  });
});
