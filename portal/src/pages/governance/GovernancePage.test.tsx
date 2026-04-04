/**
 * Governance Page Tests (CAB-1525)
 *
 * 4-persona RBAC tests: cpi-admin, tenant-admin, devops, viewer.
 * Tests approval queue rendering, permission gates, and tab navigation.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';
import { GovernancePage } from './GovernancePage';

// Mock auth context
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

// Mock governance hooks
vi.mock('../../hooks/useGovernance', () => ({
  useGovernanceStats: vi.fn(),
  usePendingApprovals: vi.fn(),
  useApproveRequest: vi.fn(),
  useRejectRequest: vi.fn(),
}));

import { useAuth } from '../../contexts/AuthContext';
import {
  useGovernanceStats,
  usePendingApprovals,
  useApproveRequest,
  useRejectRequest,
} from '../../hooks/useGovernance';

const mockStats = {
  pending_approvals: 3,
  apis_by_status: { draft: 2, published: 5, deprecated: 1 },
  total_subscriptions: 10,
  active_subscriptions: 8,
};

const mockApprovals = {
  items: [
    {
      id: 'approval-1',
      type: 'subscription' as const,
      requester_name: 'Test App',
      requester_email: 'dev@test.com',
      resource_name: 'Payment API',
      resource_id: 'api-1',
      details: 'Test App \u2192 Payment API v1.0',
      status: 'pending' as const,
      created_at: '2026-03-01T00:00:00Z',
    },
  ],
  total: 1,
};

function setupMocks() {
  vi.mocked(useGovernanceStats).mockReturnValue({
    data: mockStats,
    isLoading: false,
    error: null,
  } as ReturnType<typeof useGovernanceStats>);

  vi.mocked(usePendingApprovals).mockReturnValue({
    data: mockApprovals,
    isLoading: false,
    error: null,
  } as ReturnType<typeof usePendingApprovals>);

  vi.mocked(useApproveRequest).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useApproveRequest>);

  vi.mocked(useRejectRequest).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useRejectRequest>);
}

describe('GovernancePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMocks();
  });

  // ============ 4-Persona RBAC Tests ============

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin'])('%s can access governance', (role) => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
    });

    it('renders the governance page', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByText('Governance')).toBeInTheDocument();
    });

    it('shows stat cards with pending approvals', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByText('Pending Approvals')).toBeInTheDocument();
      expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(1);
    });

    it('shows published APIs count', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByText('Published APIs')).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
    });

    it('renders approval queue with pending items', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByText(/Test App \u2192 Payment API/)).toBeInTheDocument();
    });

    it('has approve and reject buttons', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByLabelText('Approve Payment API')).toBeInTheDocument();
      expect(screen.getByLabelText('Reject Payment API')).toBeInTheDocument();
    });
  });

  describe('viewer cannot access governance', () => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
    });

    it('shows permission denied message', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByText(/don't have permission to access governance/)).toBeInTheDocument();
    });

    it('does not render approval queue', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.queryByText('Pending Approvals')).not.toBeInTheDocument();
    });
  });

  describe('devops can access governance (has apis:update)', () => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('devops'));
    });

    it('renders governance page for devops', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByText('Governance')).toBeInTheDocument();
    });
  });

  // ============ Tab Navigation ============

  describe('tab navigation', () => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    });

    it('defaults to approvals tab', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByText('Pending Approvals (1)')).toBeInTheDocument();
    });

    it('switches to lifecycle tab', async () => {
      const user = userEvent.setup();
      renderWithProviders(<GovernancePage />, { route: '/governance' });

      await user.click(screen.getByText('API Lifecycle'));
      expect(screen.getByText('API Lifecycle Distribution')).toBeInTheDocument();
    });

    it('switches to overview tab', async () => {
      const user = userEvent.setup();
      renderWithProviders(<GovernancePage />, { route: '/governance' });

      await user.click(screen.getByText('Overview'));
      expect(screen.getByText('Governance Overview')).toBeInTheDocument();
    });

    it('shows pending count badge on approvals tab', () => {
      renderWithProviders(<GovernancePage />, { route: '/governance' });
      // The badge shows the count from stats (may appear in stat card + tab badge)
      expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(1);
    });
  });

  // ============ Approve/Reject Actions ============

  describe('approval actions', () => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
    });

    it('calls approve mutation on click', async () => {
      const mockApprove = vi.fn();
      vi.mocked(useApproveRequest).mockReturnValue({
        mutate: mockApprove,
        isPending: false,
      } as unknown as ReturnType<typeof useApproveRequest>);

      const user = userEvent.setup();
      renderWithProviders(<GovernancePage />, { route: '/governance' });

      await user.click(screen.getByLabelText('Approve Payment API'));
      expect(mockApprove).toHaveBeenCalledWith({ id: 'approval-1' });
    });

    it('calls reject mutation on click', async () => {
      const mockReject = vi.fn();
      vi.mocked(useRejectRequest).mockReturnValue({
        mutate: mockReject,
        isPending: false,
      } as unknown as ReturnType<typeof useRejectRequest>);

      const user = userEvent.setup();
      renderWithProviders(<GovernancePage />, { route: '/governance' });

      await user.click(screen.getByLabelText('Reject Payment API'));
      expect(mockReject).toHaveBeenCalledWith({ id: 'approval-1' });
    });

    it('disables buttons while processing', () => {
      vi.mocked(useApproveRequest).mockReturnValue({
        mutate: vi.fn(),
        isPending: true,
      } as unknown as ReturnType<typeof useApproveRequest>);

      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByLabelText('Approve Payment API')).toBeDisabled();
      expect(screen.getByLabelText('Reject Payment API')).toBeDisabled();
    });
  });

  // ============ Empty & Loading States ============

  describe('empty state', () => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    });

    it('shows empty state when no approvals', () => {
      vi.mocked(usePendingApprovals).mockReturnValue({
        data: { items: [], total: 0 },
        isLoading: false,
        error: null,
      } as ReturnType<typeof usePendingApprovals>);

      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByText('All caught up!')).toBeInTheDocument();
    });

    it('shows loading skeleton', () => {
      vi.mocked(usePendingApprovals).mockReturnValue({
        data: undefined,
        isLoading: true,
        error: null,
      } as ReturnType<typeof usePendingApprovals>);

      renderWithProviders(<GovernancePage />, { route: '/governance' });
      // Loading skeletons are rendered
      const skeletons = document.querySelectorAll('.animate-pulse');
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it('shows error message on failure', () => {
      vi.mocked(usePendingApprovals).mockReturnValue({
        data: undefined,
        isLoading: false,
        error: new Error('Network error'),
      } as ReturnType<typeof usePendingApprovals>);

      renderWithProviders(<GovernancePage />, { route: '/governance' });
      expect(screen.getByText(/Failed to load approvals/)).toBeInTheDocument();
    });
  });

  // ============ Lifecycle Overview ============

  describe('lifecycle overview', () => {
    beforeEach(() => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    });

    it('shows lifecycle distribution bar', async () => {
      const user = userEvent.setup();
      renderWithProviders(<GovernancePage />, { route: '/governance' });

      await user.click(screen.getByText('API Lifecycle'));

      await waitFor(() => {
        expect(screen.getByText(/Draft: 2/)).toBeInTheDocument();
        expect(screen.getByText(/Published: 5/)).toBeInTheDocument();
        expect(screen.getByText(/Deprecated: 1/)).toBeInTheDocument();
      });
    });

    it('shows lifecycle rules', async () => {
      const user = userEvent.setup();
      renderWithProviders(<GovernancePage />, { route: '/governance' });

      await user.click(screen.getByText('API Lifecycle'));

      await waitFor(() => {
        expect(screen.getByText('Lifecycle Rules')).toBeInTheDocument();
        expect(screen.getAllByText('Requires approval').length).toBeGreaterThanOrEqual(1);
      });
    });
  });
});
