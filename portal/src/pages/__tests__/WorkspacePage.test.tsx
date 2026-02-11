/**
 * WorkspacePage Tests (CAB-1133)
 *
 * Page-level functional tests for the Workspace page with tabs.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders } from '../../test/helpers';

// Mock AuthContext
const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
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

describe('WorkspacePage', () => {
  let WorkspacePage: React.ComponentType;

  beforeEach(async () => {
    vi.clearAllMocks();

    const pageModule = await import('../workspace/WorkspacePage');
    WorkspacePage = pageModule.WorkspacePage;
  });

  it('renders "My Workspace" heading', () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />);

    expect(screen.getByText('My Workspace')).toBeInTheDocument();
    expect(screen.getByText('Manage your apps, subscriptions, and contracts')).toBeInTheDocument();
  });

  it('default tab is "apps"', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />);

    await waitFor(() => {
      expect(screen.getByTestId('my-applications')).toBeInTheDocument();
    });
  });

  it('cpi-admin sees 4 tabs: Apps, Subscriptions, Contracts, Approvals', () => {
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));

    renderWithProviders(<WorkspacePage />);

    expect(screen.getByRole('button', { name: /Apps/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Subscriptions/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Contracts/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Approvals/i })).toBeInTheDocument();
  });

  it('tenant-admin sees 4 tabs: Apps, Subscriptions, Contracts, Approvals', () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />);

    expect(screen.getByRole('button', { name: /Apps/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Subscriptions/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Contracts/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Approvals/i })).toBeInTheDocument();
  });

  it('devops sees 3 tabs: Apps, Subscriptions, Contracts (NO Approvals)', () => {
    mockAuth.mockReturnValue(createAuthMock('devops'));

    renderWithProviders(<WorkspacePage />);

    expect(screen.getByRole('button', { name: /Apps/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Subscriptions/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Contracts/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approvals/i })).not.toBeInTheDocument();
  });

  it('viewer sees 3 tabs: Apps, Subscriptions, Contracts (NO Approvals)', () => {
    mockAuth.mockReturnValue(createAuthMock('viewer'));

    renderWithProviders(<WorkspacePage />);

    expect(screen.getByRole('button', { name: /Apps/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Subscriptions/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Contracts/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Approvals/i })).not.toBeInTheDocument();
  });

  it('clicking Subscriptions tab renders subscriptions content', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />);

    const subscriptionsTab = screen.getByRole('button', { name: /Subscriptions/i });
    await user.click(subscriptionsTab);

    await waitFor(() => {
      expect(screen.getByTestId('my-subscriptions')).toBeInTheDocument();
    });
  });

  it('clicking Contracts tab renders contracts content', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />);

    const contractsTab = screen.getByRole('button', { name: /Contracts/i });
    await user.click(contractsTab);

    await waitFor(() => {
      expect(screen.getByTestId('contract-list')).toBeInTheDocument();
    });
  });

  it('clicking Approvals tab renders approvals content (admin only)', async () => {
    const user = userEvent.setup();
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />);

    const approvalsTab = screen.getByRole('button', { name: /Approvals/i });
    await user.click(approvalsTab);

    await waitFor(() => {
      expect(screen.getByTestId('approval-queue')).toBeInTheDocument();
    });
  });

  it('URL ?tab=subscriptions activates subscriptions tab', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />, { route: '/?tab=subscriptions' });

    await waitFor(() => {
      expect(screen.getByTestId('my-subscriptions')).toBeInTheDocument();
    });
  });

  it('URL ?tab=contracts activates contracts tab', async () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />, { route: '/?tab=contracts' });

    await waitFor(() => {
      expect(screen.getByTestId('contract-list')).toBeInTheDocument();
    });
  });

  it('URL ?tab=approvals activates approvals tab (admin only)', async () => {
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));

    renderWithProviders(<WorkspacePage />, { route: '/?tab=approvals' });

    await waitFor(() => {
      expect(screen.getByTestId('approval-queue')).toBeInTheDocument();
    });
  });

  it('active tab has highlighted styling', () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />);

    const appsTab = screen.getByRole('button', { name: /Apps/i });
    expect(appsTab).toHaveClass('border-primary-600');
  });

  it('inactive tabs do not have highlighted styling', () => {
    mockAuth.mockReturnValue(createAuthMock('tenant-admin'));

    renderWithProviders(<WorkspacePage />);

    const subscriptionsTab = screen.getByRole('button', { name: /Subscriptions/i });
    expect(subscriptionsTab).toHaveClass('border-transparent');
  });
});
