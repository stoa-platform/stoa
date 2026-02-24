import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ApprovalQueue } from './ApprovalQueue';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';

const mockListPending = vi.fn();
const mockApproveSubscription = vi.fn();

vi.mock('../../services/apiSubscriptions', () => ({
  apiSubscriptionsService: {
    listPendingForTenant: (...args: unknown[]) => mockListPending(...args),
    approveSubscription: (...args: unknown[]) => mockApproveSubscription(...args),
  },
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({
    success: vi.fn(),
    error: vi.fn(),
  }),
}));

import { useAuth } from '../../contexts/AuthContext';

const mockPendingItems = [
  {
    id: 'sub-1',
    api_name: 'Payment API',
    api_version: '2.0',
    subscriber_email: 'dev@acme.com',
    application_name: 'Acme App',
    plan_name: 'Premium',
    created_at: '2026-02-20T10:00:00Z',
  },
  {
    id: 'sub-2',
    api_name: 'Orders API',
    api_version: null,
    subscriber_email: 'bob@corp.com',
    application_name: 'Corp App',
    plan_name: null,
    created_at: '2026-02-21T10:00:00Z',
  },
];

describe('ApprovalQueue', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
    mockListPending.mockResolvedValue({ items: mockPendingItems });
    mockApproveSubscription.mockResolvedValue(undefined);
  });

  it('should show loading state', () => {
    mockListPending.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<ApprovalQueue />);
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('should show empty state when no pending requests', async () => {
    mockListPending.mockResolvedValue({ items: [] });
    renderWithProviders(<ApprovalQueue />);
    await waitFor(() => {
      expect(screen.getByText('No pending requests')).toBeInTheDocument();
    });
    expect(screen.getByText('All subscription requests have been processed.')).toBeInTheDocument();
  });

  it('should render pending subscription items', async () => {
    renderWithProviders(<ApprovalQueue />);
    await waitFor(() => {
      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });
    expect(screen.getByText('Orders API')).toBeInTheDocument();
    expect(screen.getByText('dev@acme.com')).toBeInTheDocument();
    expect(screen.getByText('Acme App')).toBeInTheDocument();
    expect(screen.getByText('Premium')).toBeInTheDocument();
  });

  it('should show version badge when api_version is set', async () => {
    renderWithProviders(<ApprovalQueue />);
    await waitFor(() => {
      expect(screen.getByText('v2.0')).toBeInTheDocument();
    });
  });

  it('should display pending count in header', async () => {
    renderWithProviders(<ApprovalQueue />);
    await waitFor(() => {
      expect(screen.getByText('Pending Requests (2)')).toBeInTheDocument();
    });
  });

  it('should call approve mutation on button click', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ApprovalQueue />);

    await waitFor(() => {
      expect(screen.getByText('Payment API')).toBeInTheDocument();
    });

    const approveButtons = screen.getAllByText('Approve');
    await user.click(approveButtons[0]);

    expect(mockApproveSubscription).toHaveBeenCalledWith('sub-1');
  });

  it('should show error state on fetch failure', async () => {
    mockListPending.mockRejectedValue(new Error('Forbidden'));
    renderWithProviders(<ApprovalQueue />);
    await waitFor(() => {
      expect(screen.getByText(/Failed to load pending requests/)).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'persona: %s',
    (role) => {
      it('should render when user has tenant_id', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<ApprovalQueue />);
        await waitFor(() => {
          expect(mockListPending).toHaveBeenCalled();
        });
      });
    }
  );
});
