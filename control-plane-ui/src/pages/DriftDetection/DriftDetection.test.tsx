import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders, mockGatewayInstance } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetGatewayInstances = vi.fn().mockResolvedValue({ items: [], total: 0 });
const mockGetGatewayDeployments = vi.fn().mockResolvedValue({ items: [], total: 0 });
const mockGetDeploymentStatusSummary = vi.fn().mockResolvedValue({
  synced: 5,
  pending: 1,
  drifted: 2,
  error: 1,
  syncing: 0,
  deleting: 0,
  total: 9,
});
const mockCheckGatewayHealth = vi.fn().mockResolvedValue({ status: 'healthy' });
const mockForceSyncDeployment = vi.fn().mockResolvedValue(undefined);

vi.mock('../../services/api', () => ({
  apiService: {
    getGatewayInstances: (...args: unknown[]) => mockGetGatewayInstances(...args),
    getGatewayDeployments: (...args: unknown[]) => mockGetGatewayDeployments(...args),
    getDeploymentStatusSummary: (...args: unknown[]) => mockGetDeploymentStatusSummary(...args),
    checkGatewayHealth: (...args: unknown[]) => mockCheckGatewayHealth(...args),
    forceSyncDeployment: (...args: unknown[]) => mockForceSyncDeployment(...args),
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
  },
}));

vi.mock('../../components/SyncStatusBadge', () => ({
  SyncStatusBadge: ({ status }: { status: string }) => <span>{status}</span>,
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title?: string }) => <div data-testid="empty-state">{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  TableSkeleton: () => <div data-testid="table-skeleton" />,
}));

import { DriftDetection } from './DriftDetection';

describe('DriftDetection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetGatewayInstances.mockResolvedValue({ items: [], total: 0 });
    mockGetGatewayDeployments.mockResolvedValue({ items: [], total: 0 });
    mockGetDeploymentStatusSummary.mockResolvedValue({
      synced: 5,
      pending: 1,
      drifted: 2,
      error: 1,
      syncing: 0,
      deleting: 0,
      total: 9,
    });
  });

  it('renders the heading', async () => {
    renderWithProviders(<DriftDetection />);
    expect(await screen.findByRole('heading', { name: /Drift Detection/ })).toBeInTheDocument();
  });

  it('renders summary cards with correct counts', async () => {
    mockGetGatewayInstances.mockResolvedValue({
      items: [
        mockGatewayInstance({ id: 'gw-1', status: 'online' }),
        mockGatewayInstance({ id: 'gw-2', status: 'online' }),
        mockGatewayInstance({ id: 'gw-3', status: 'online' }),
        mockGatewayInstance({ id: 'gw-4', status: 'offline' }),
      ],
      total: 4,
    });
    mockGetDeploymentStatusSummary.mockResolvedValue({
      synced: 5,
      pending: 0,
      drifted: 2,
      error: 0,
      syncing: 0,
      deleting: 0,
      total: 7,
    });

    renderWithProviders(<DriftDetection />);
    await waitFor(() => {
      expect(screen.getByText('4')).toBeInTheDocument(); // Total Gateways
      expect(screen.getByText('3')).toBeInTheDocument(); // Healthy (3 online)
      expect(screen.getByText('2')).toBeInTheDocument(); // Drifted
    });
  });

  it('renders gateway health grid with gateway names', async () => {
    mockGetGatewayInstances.mockResolvedValue({
      items: [
        mockGatewayInstance({ id: 'gw-1', display_name: 'STOA Gateway', status: 'online' }),
        mockGatewayInstance({ id: 'gw-2', display_name: 'Kong Gateway', status: 'degraded' }),
      ],
      total: 2,
    });

    renderWithProviders(<DriftDetection />);
    expect(await screen.findByText('STOA Gateway')).toBeInTheDocument();
    expect(screen.getByText('Kong Gateway')).toBeInTheDocument();
    expect(screen.getByText('Online')).toBeInTheDocument();
    expect(screen.getByText('Degraded')).toBeInTheDocument();
  });

  it('shows All Clear when no drift', async () => {
    renderWithProviders(<DriftDetection />);
    expect(await screen.findByText('All Clear')).toBeInTheDocument();
  });

  it('renders drifted deployments table', async () => {
    mockGetGatewayDeployments.mockImplementation((params: { sync_status?: string }) => {
      if (params?.sync_status === 'drifted') {
        return Promise.resolve({
          items: [
            {
              id: 'dep-1',
              api_catalog_id: 'api-1',
              gateway_instance_id: 'gw-1',
              sync_status: 'drifted',
              sync_error: 'Config mismatch',
              desired_state: { api_name: 'Payment API' },
              desired_at: '2026-02-01T00:00:00Z',
              sync_attempts: 3,
              last_sync_attempt: '2026-02-15T10:00:00Z',
              created_at: '2026-01-15T00:00:00Z',
              updated_at: '2026-02-15T10:00:00Z',
            },
          ],
          total: 1,
        });
      }
      return Promise.resolve({ items: [], total: 0 });
    });

    renderWithProviders(<DriftDetection />);
    expect(await screen.findByText('Payment API')).toBeInTheDocument();
    expect(screen.getByText('drifted')).toBeInTheDocument();
    expect(screen.getByText('Config mismatch')).toBeInTheDocument();
  });

  it('calls forceSyncDeployment when Force Sync is clicked', async () => {
    const user = userEvent.setup();

    mockGetGatewayDeployments.mockImplementation((params: { sync_status?: string }) => {
      if (params?.sync_status === 'drifted') {
        return Promise.resolve({
          items: [
            {
              id: 'dep-1',
              api_catalog_id: 'api-1',
              gateway_instance_id: 'gw-1',
              sync_status: 'drifted',
              desired_state: {},
              desired_at: '2026-02-01T00:00:00Z',
              sync_attempts: 1,
              created_at: '2026-01-15T00:00:00Z',
              updated_at: '2026-02-15T10:00:00Z',
            },
          ],
          total: 1,
        });
      }
      return Promise.resolve({ items: [], total: 0 });
    });

    renderWithProviders(<DriftDetection />);
    const syncBtn = await screen.findByText('Force Sync');
    await user.click(syncBtn);

    await waitFor(() => {
      expect(mockForceSyncDeployment).toHaveBeenCalledWith('dep-1');
    });
  });

  it('calls checkGatewayHealth when Check Health is clicked', async () => {
    const user = userEvent.setup();

    mockGetGatewayInstances.mockResolvedValue({
      items: [mockGatewayInstance({ id: 'gw-1', display_name: 'Test GW', status: 'online' })],
      total: 1,
    });

    renderWithProviders(<DriftDetection />);
    const healthBtn = await screen.findByText('Check Health');
    await user.click(healthBtn);

    await waitFor(() => {
      expect(mockCheckGatewayHealth).toHaveBeenCalledWith('gw-1');
    });
  });

  it('hides action buttons for non-admin users', async () => {
    vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));

    mockGetGatewayInstances.mockResolvedValue({
      items: [mockGatewayInstance({ id: 'gw-1', status: 'online' })],
      total: 1,
    });

    mockGetGatewayDeployments.mockImplementation((params: { sync_status?: string }) => {
      if (params?.sync_status === 'drifted') {
        return Promise.resolve({
          items: [
            {
              id: 'dep-1',
              api_catalog_id: 'api-1',
              gateway_instance_id: 'gw-1',
              sync_status: 'drifted',
              desired_state: {},
              desired_at: '2026-02-01T00:00:00Z',
              sync_attempts: 1,
              created_at: '2026-01-15T00:00:00Z',
              updated_at: '2026-02-15T10:00:00Z',
            },
          ],
          total: 1,
        });
      }
      return Promise.resolve({ items: [], total: 0 });
    });

    renderWithProviders(<DriftDetection />);
    await screen.findByRole('heading', { name: /Drift Detection/ });

    expect(screen.queryByText('Check Health')).not.toBeInTheDocument();
    expect(screen.queryByText('Force Sync')).not.toBeInTheDocument();
  });

  it('shows error state with retry button', async () => {
    const networkError = { response: { data: { detail: 'Service unavailable' } } };
    mockGetGatewayInstances.mockRejectedValue(networkError);
    mockGetGatewayDeployments.mockRejectedValue(networkError);
    mockGetDeploymentStatusSummary.mockRejectedValue(networkError);

    renderWithProviders(<DriftDetection />);
    expect(await screen.findByRole('button', { name: /Retry/ })).toBeInTheDocument();
    expect(screen.getByText('Service unavailable')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<DriftDetection />);
        expect(await screen.findByRole('heading', { name: /Drift Detection/ })).toBeInTheDocument();
      });
    }
  );
});
