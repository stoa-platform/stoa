/**
 * MySubscriptions Tests - CAB-1167
 *
 * Tests for the subscriptions management page with server and tool subscriptions.
 */

import { screen, waitFor } from '@testing-library/react';
import {
  renderWithProviders,
  createAuthMock,
  mockServerSubscription,
  type PersonaRole,
} from '../../test/helpers';
import { MySubscriptions } from '../subscriptions/MySubscriptions';

// Mock AuthContext at module level
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock services
const mockGetMyServerSubscriptions = vi.fn();
vi.mock('../../services/mcpServers', () => ({
  mcpServersService: {
    getMyServerSubscriptions: () => mockGetMyServerSubscriptions(),
  },
}));

// Mock hooks
const mockSubscriptionsData = vi.fn();
const mockRevokeMutation = vi.fn();
const mockRotateKeyMutation = vi.fn();

vi.mock('../../hooks/useSubscriptions', () => ({
  useSubscriptions: () => ({
    data: mockSubscriptionsData(),
    isLoading: false,
    isError: false,
    error: null,
  }),
  useRevokeSubscription: () => ({
    mutateAsync: mockRevokeMutation,
  }),
  useRotateApiKey: () => ({
    mutateAsync: mockRotateKeyMutation,
    isPending: false,
  }),
}));

// Mock shared components
vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  ConfirmDialog: ({ open, onCancel }: { open: boolean; onCancel: () => void }) =>
    open ? (
      <div data-testid="confirm-dialog">
        <button onClick={onCancel}>Cancel</button>
      </div>
    ) : null,
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

// Mock subscription components
vi.mock('../../components/subscriptions/RevealKeyModal', () => ({
  RevealKeyModal: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? (
      <div data-testid="reveal-key-modal">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

vi.mock('../../components/subscriptions/RotateKeyModal', () => ({
  RotateKeyModal: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? (
      <div data-testid="rotate-key-modal">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

vi.mock('../../components/subscriptions/ExportConfigModal', () => ({
  ExportConfigModal: ({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) =>
    isOpen ? (
      <div data-testid="export-config-modal">
        <button onClick={onClose}>Close</button>
      </div>
    ) : null,
}));

// Mock skeletons
vi.mock('../../components/skeletons', () => ({
  StatCardWithIconSkeleton: () => <div data-testid="stat-skeleton">Loading...</div>,
  ServerCardSkeletonGrid: () => <div data-testid="card-skeleton-grid">Loading...</div>,
}));

describe('MySubscriptions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockGetMyServerSubscriptions.mockResolvedValue([]);
    mockSubscriptionsData.mockReturnValue({ subscriptions: [] });
  });

  it('renders the page heading', async () => {
    renderWithProviders(<MySubscriptions />);
    await waitFor(() => {
      expect(screen.getByText('My Subscriptions')).toBeInTheDocument();
    });
  });

  it('renders tabs for servers and tools', async () => {
    renderWithProviders(<MySubscriptions />);
    await waitFor(() => {
      expect(screen.getByText('MCP Servers')).toBeInTheDocument();
      expect(screen.getByText('Individual Tools')).toBeInTheDocument();
    });
  });

  it('renders stats cards', async () => {
    renderWithProviders(<MySubscriptions />);
    await waitFor(() => {
      expect(screen.getAllByText('Active Subscriptions')[0]).toBeInTheDocument();
      expect(screen.getByText('Server Subscriptions')).toBeInTheDocument();
      expect(screen.getByText('Total API Calls')).toBeInTheDocument();
    });
  });

  it('shows empty state when no server subscriptions', async () => {
    renderWithProviders(<MySubscriptions />);
    await waitFor(() => {
      expect(screen.getByText('No Server Subscriptions')).toBeInTheDocument();
      expect(screen.getByText('Browse MCP Servers')).toBeInTheDocument();
    });
  });

  it('renders server subscriptions when data exists', async () => {
    const mockSub = mockServerSubscription({ id: 'sub-1' });
    mockGetMyServerSubscriptions.mockResolvedValue([mockSub]);

    renderWithProviders(<MySubscriptions />);

    await waitFor(() => {
      expect(screen.getByText(mockSub.server.displayName)).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.clearAllMocks();
        mockAuth.mockReturnValue(createAuthMock(role));
        mockGetMyServerSubscriptions.mockResolvedValue([]);
        mockSubscriptionsData.mockReturnValue({ subscriptions: [] });
      });

      it('renders the page without error', async () => {
        renderWithProviders(<MySubscriptions />);
        await waitFor(() => {
          expect(screen.getByText('My Subscriptions')).toBeInTheDocument();
        });
      });

      it('shows stats cards', async () => {
        renderWithProviders(<MySubscriptions />);
        await waitFor(() => {
          expect(screen.getAllByText('Active Subscriptions')[0]).toBeInTheDocument();
        });
      });
    }
  );
});
