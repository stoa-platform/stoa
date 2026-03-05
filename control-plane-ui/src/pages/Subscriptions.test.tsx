import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../contexts/EnvironmentContext', () => ({
  useEnvironment: vi.fn(() => ({
    activeEnvironment: null,
    activeConfig: null,
    environments: [],
    switchEnvironment: vi.fn(),
  })),
}));

const mockGetSubscriptions = vi.fn().mockResolvedValue({
  items: [
    {
      id: 'sub-1',
      application_id: 'app-1',
      application_name: 'Mobile App',
      subscriber_id: 'user-1',
      subscriber_email: 'dev@example.com',
      api_id: 'api-1',
      api_name: 'Weather API',
      api_version: '1.0',
      tenant_id: 'oasis-gunters',
      plan_id: 'basic',
      plan_name: 'Basic Plan',
      status: 'pending',
      status_reason: null,
      created_at: '2026-02-15T10:00:00Z',
      updated_at: '2026-02-15T10:00:00Z',
      approved_at: null,
      approved_by: null,
      rejected_at: null,
      rejected_by: null,
      revoked_at: null,
      revoked_by: null,
      expires_at: null,
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
});

const mockGetSubscriptionStats = vi.fn().mockResolvedValue({
  total: 42,
  by_status: { pending: 5, active: 30, suspended: 3, revoked: 2, rejected: 2 },
  recent_24h: 3,
  avg_approval_time_hours: 2.5,
});

vi.mock('../services/api', () => ({
  apiService: {
    getTenants: vi.fn().mockResolvedValue([
      {
        id: 'oasis-gunters',
        name: 'oasis-gunters',
        display_name: 'Oasis Gunters',
        status: 'active',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ]),
    getSubscriptions: (...args: unknown[]) => mockGetSubscriptions(...args),
    getSubscriptionStats: (...args: unknown[]) => mockGetSubscriptionStats(...args),
    approveSubscription: vi.fn().mockResolvedValue({}),
    rejectSubscription: vi.fn().mockResolvedValue({}),
    bulkSubscriptionAction: vi.fn().mockResolvedValue({ succeeded: 1, failed: [] }),
  },
}));

vi.mock('../hooks/useDebounce', () => ({
  useDebounce: (val: string) => val,
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  TableSkeleton: () => <div data-testid="table-skeleton" />,
  StatCardSkeletonRow: () => <div data-testid="stat-skeleton" />,
}));

vi.mock('@stoa/shared/components/Button', () => ({
  Button: ({ children, ...props }: { children: React.ReactNode; [key: string]: unknown }) => (
    <button {...props}>{children}</button>
  ),
}));

import { Subscriptions } from './Subscriptions';

function renderSubscriptions() {
  return renderWithProviders(<Subscriptions />, { route: '/subscriptions' });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Subscriptions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetSubscriptions.mockResolvedValue({
      items: [
        {
          id: 'sub-1',
          application_id: 'app-1',
          application_name: 'Mobile App',
          subscriber_id: 'user-1',
          subscriber_email: 'dev@example.com',
          api_id: 'api-1',
          api_name: 'Weather API',
          api_version: '1.0',
          tenant_id: 'oasis-gunters',
          plan_id: 'basic',
          plan_name: 'Basic Plan',
          status: 'pending',
          status_reason: null,
          created_at: '2026-02-15T10:00:00Z',
          updated_at: '2026-02-15T10:00:00Z',
          approved_at: null,
          approved_by: null,
          rejected_at: null,
          rejected_by: null,
          revoked_at: null,
          revoked_by: null,
          expires_at: null,
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mockGetSubscriptionStats.mockResolvedValue({
      total: 42,
      by_status: { pending: 5, active: 30, suspended: 3, revoked: 2, rejected: 2 },
      recent_24h: 3,
      avg_approval_time_hours: 2.5,
    });
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the page title', async () => {
    renderSubscriptions();
    expect(await screen.findByText('Subscriptions')).toBeInTheDocument();
  });

  it('renders status tabs', async () => {
    renderSubscriptions();
    await waitFor(() => {
      expect(screen.getByText('Pending')).toBeInTheDocument();
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText('Rejected')).toBeInTheDocument();
    });
  });

  it('renders the tenant selector', async () => {
    renderSubscriptions();
    await waitFor(() => {
      const select = screen.getByDisplayValue('Oasis Gunters');
      expect(select).toBeInTheDocument();
    });
  });

  it('renders subscription data in table', async () => {
    renderSubscriptions();
    expect(await screen.findByText('Mobile App')).toBeInTheDocument();
    expect(screen.getByText('Weather API')).toBeInTheDocument();
    expect(screen.getByText('dev@example.com')).toBeInTheDocument();
    expect(screen.getByText('Basic Plan')).toBeInTheDocument();
  });

  it('renders stats cards', async () => {
    renderSubscriptions();
    await waitFor(() => {
      expect(screen.getByText('Total Subscribers')).toBeInTheDocument();
      expect(screen.getByText('Pending Requests')).toBeInTheDocument();
      expect(screen.getByText('Approval Rate')).toBeInTheDocument();
    });
  });

  it('renders action buttons for pending subscriptions', async () => {
    renderSubscriptions();
    const approveButtons = await screen.findAllByText('Approve');
    expect(approveButtons.length).toBeGreaterThan(0);
    const rejectButtons = screen.getAllByText('Reject');
    expect(rejectButtons.length).toBeGreaterThan(0);
  });

  it('shows empty state when no subscriptions', async () => {
    mockGetSubscriptions.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    renderSubscriptions();
    expect(await screen.findByText('No subscriptions')).toBeInTheDocument();
  });

  it('renders search input', async () => {
    renderSubscriptions();
    await waitFor(() => {
      const searchInput = screen.getByPlaceholderText('Search by application, email, or API...');
      expect(searchInput).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // 4-persona RBAC coverage
  // ---------------------------------------------------------------------------

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      });

      it('renders the page without errors', async () => {
        renderSubscriptions();
        expect(await screen.findByText('Subscriptions')).toBeInTheDocument();
      });

      it('renders the subscription table', async () => {
        renderSubscriptions();
        expect(await screen.findByText('Mobile App')).toBeInTheDocument();
      });

      if (role === 'cpi-admin' || role === 'tenant-admin') {
        it('shows approve/reject action buttons', async () => {
          renderSubscriptions();
          const approveButtons = await screen.findAllByText('Approve');
          expect(approveButtons.length).toBeGreaterThan(0);
          const rejectButtons = screen.getAllByText('Reject');
          expect(rejectButtons.length).toBeGreaterThan(0);
        });
      }
    }
  );

  // CAB-1673: Structural snapshot guards
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'snapshot: %s persona',
    (role) => {
      it('matches structural snapshot', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        const { container } = renderSubscriptions();
        await screen.findByText('Subscriptions');
        const buttons = [...container.querySelectorAll('button')].map(
          (b) => b.textContent?.trim() || ''
        );
        const headings = [...container.querySelectorAll('h1, h2, h3')].map(
          (h) => h.textContent?.trim() || ''
        );
        const links = [...container.querySelectorAll('a[href]')].map((a) => ({
          text: a.textContent?.trim() || '',
          href: a.getAttribute('href'),
        }));
        expect({ buttons, headings, links }).toMatchSnapshot();
      });
    }
  );
});
