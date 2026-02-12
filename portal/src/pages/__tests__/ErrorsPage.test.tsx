import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test/helpers';
import { ErrorsPage } from '../errors/ErrorsPage';

// Mock errorSnapshotsService
const mockListSnapshots = vi.fn();
const mockGetStats = vi.fn();
vi.mock('../../services/errorSnapshots', () => ({
  errorSnapshotsService: {
    listSnapshots: (...args: unknown[]) => mockListSnapshots(...args),
    getStats: (...args: unknown[]) => mockGetStats(...args),
    getSnapshot: vi.fn().mockResolvedValue(null),
  },
}));

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    user: { id: '1', roles: ['cpi-admin'], permissions: [], effective_scopes: [] },
    hasPermission: () => true,
    hasRole: () => true,
    hasScope: () => true,
    hasAnyPermission: () => true,
    hasAllPermissions: () => true,
  }),
}));

describe('ErrorsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetStats.mockResolvedValue(null);
  });

  it('renders table when snapshots exist', async () => {
    mockListSnapshots.mockResolvedValue({
      items: [
        {
          id: 'snap-1',
          timestamp: '2026-02-12T10:00:00Z',
          method: 'POST',
          path: '/v1/tools/invoke',
          status_code: 500,
          duration_ms: 1234,
          trigger: '5xx',
          source: 'gateway',
          resolution: 'unresolved',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mockGetStats.mockResolvedValue({
      total: 1,
      by_trigger: { '5xx': 1 },
      unresolved_count: 1,
    });

    renderWithProviders(<ErrorsPage />);

    await waitFor(() => {
      expect(screen.getByText('/v1/tools/invoke')).toBeInTheDocument();
    });
    expect(screen.getByText('500')).toBeInTheDocument();
  });

  it('renders empty state when no snapshots', async () => {
    mockListSnapshots.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });

    renderWithProviders(<ErrorsPage />);

    await waitFor(() => {
      expect(screen.getByText('No error snapshots')).toBeInTheDocument();
    });
  });
});
