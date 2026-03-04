/**
 * WorkspacePage Tests (CAB-1133)
 *
 * Page-level functional tests for the Workspace page with tabs.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders } from '../../test/helpers';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

// Mock i18n — disable to use fallback strings
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../i18n', () => ({
  loadNamespace: vi.fn(),
  LANGUAGE_KEY: 'stoa:language',
}));

vi.mock('../../config', () => ({
  config: {
    features: { enableI18n: false },
  },
}));

// Mock lazy-loaded components
vi.mock('../apps', () => ({
  MyApplications: () => <div data-testid="my-applications">My Applications Content</div>,
}));

vi.mock('../subscriptions/MySubscriptions', () => ({
  MySubscriptions: () => <div data-testid="my-subscriptions">My Subscriptions Content</div>,
}));

vi.mock('../contracts', () => ({
  ContractListPage: () => <div data-testid="contract-list">Contract List Content</div>,
}));

vi.mock('../../components/consumers/ApprovalQueue', () => ({
  ApprovalQueue: () => <div data-testid="approval-queue">Approval Queue Content</div>,
}));

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'WorkspacePage — %s persona',
  (role) => {
  let WorkspacePage: React.ComponentType;

  beforeEach(async () => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock(role));

    const pageModule = await import('../workspace/WorkspacePage');
    WorkspacePage = pageModule.WorkspacePage;
  });

  it('renders "My Workspace" heading', () => {
    renderWithProviders(<WorkspacePage />);

    expect(screen.getByText('My Workspace')).toBeInTheDocument();
    expect(screen.getByText('Manage your apps, subscriptions, and contracts')).toBeInTheDocument();
  });

  it('default tab is "apps"', async () => {
    renderWithProviders(<WorkspacePage />);

    await waitFor(() => {
      expect(screen.getByTestId('my-applications')).toBeInTheDocument();
    });
  });

  it('shows correct tabs based on role', () => {
    const hasApprovals = role === 'cpi-admin' || role === 'tenant-admin';

    renderWithProviders(<WorkspacePage />);

    expect(screen.getByRole('button', { name: /Apps/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Subscriptions/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Contracts/i })).toBeInTheDocument();
    if (hasApprovals) {
      expect(screen.getByRole('button', { name: /Approvals/i })).toBeInTheDocument();
    } else {
      expect(screen.queryByRole('button', { name: /Approvals/i })).not.toBeInTheDocument();
    }
  });

  it('clicking Subscriptions tab renders subscriptions content', async () => {
    const user = userEvent.setup();

    renderWithProviders(<WorkspacePage />);

    const subscriptionsTab = screen.getByRole('button', { name: /Subscriptions/i });
    await user.click(subscriptionsTab);

    await waitFor(() => {
      expect(screen.getByTestId('my-subscriptions')).toBeInTheDocument();
    });
  });

  it('clicking Contracts tab renders contracts content', async () => {
    const user = userEvent.setup();

    renderWithProviders(<WorkspacePage />);

    const contractsTab = screen.getByRole('button', { name: /Contracts/i });
    await user.click(contractsTab);

    await waitFor(() => {
      expect(screen.getByTestId('contract-list')).toBeInTheDocument();
    });
  });

  it('clicking Approvals tab renders approvals content (admin only)', async () => {
    const hasApprovals = role === 'cpi-admin' || role === 'tenant-admin';
    if (!hasApprovals) return;

    const user = userEvent.setup();

    renderWithProviders(<WorkspacePage />);

    const approvalsTab = screen.getByRole('button', { name: /Approvals/i });
    await user.click(approvalsTab);

    await waitFor(() => {
      expect(screen.getByTestId('approval-queue')).toBeInTheDocument();
    });
  });

  it('URL ?tab=subscriptions activates subscriptions tab', async () => {
    renderWithProviders(<WorkspacePage />, { route: '/?tab=subscriptions' });

    await waitFor(() => {
      expect(screen.getByTestId('my-subscriptions')).toBeInTheDocument();
    });
  });

  it('URL ?tab=contracts activates contracts tab', async () => {
    renderWithProviders(<WorkspacePage />, { route: '/?tab=contracts' });

    await waitFor(() => {
      expect(screen.getByTestId('contract-list')).toBeInTheDocument();
    });
  });

  it('URL ?tab=approvals activates approvals tab (admin only)', async () => {
    const hasApprovals = role === 'cpi-admin' || role === 'tenant-admin';
    if (!hasApprovals) return;

    renderWithProviders(<WorkspacePage />, { route: '/?tab=approvals' });

    await waitFor(() => {
      expect(screen.getByTestId('approval-queue')).toBeInTheDocument();
    });
  });

  it('active tab has highlighted styling', () => {
    renderWithProviders(<WorkspacePage />);

    const appsTab = screen.getByRole('button', { name: /Apps/i });
    expect(appsTab).toHaveClass('border-primary-600');
  });

  it('inactive tabs do not have highlighted styling', () => {
    renderWithProviders(<WorkspacePage />);

    const subscriptionsTab = screen.getByRole('button', { name: /Subscriptions/i });
    expect(subscriptionsTab).toHaveClass('border-transparent');
  });
});
