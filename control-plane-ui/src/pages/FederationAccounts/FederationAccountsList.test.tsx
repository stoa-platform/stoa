import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, renderWithProviders, mockMasterAccount } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock federation service
const mockListMasterAccounts = vi.fn().mockResolvedValue({
  items: [
    mockMasterAccount(),
    mockMasterAccount({
      id: 'master-2',
      name: 'Secondary Federation',
      status: 'suspended',
      sub_account_count: 0,
    }),
  ],
  total: 2,
  page: 1,
  page_size: 20,
});

vi.mock('../../services/federationApi', () => ({
  federationService: {
    listMasterAccounts: (...args: unknown[]) => mockListMasterAccounts(...args),
    createMasterAccount: vi.fn().mockResolvedValue({}),
    deleteMasterAccount: vi.fn().mockResolvedValue({}),
  },
}));

// Mock shared components
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(false), () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title?: string }) => <div data-testid="empty-state">{title}</div>,
}));

// Mock modal
vi.mock('./MasterAccountModal', () => ({
  MasterAccountModal: () => <div data-testid="create-modal">Create Modal</div>,
}));

import { FederationAccountsList } from './FederationAccountsList';

function renderComponent() {
  return renderWithProviders(<FederationAccountsList />, { route: '/federation/accounts' });
}

describe('FederationAccountsList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockListMasterAccounts.mockResolvedValue({
      items: [
        mockMasterAccount(),
        mockMasterAccount({
          id: 'master-2',
          name: 'Secondary Federation',
          status: 'suspended',
          sub_account_count: 0,
        }),
      ],
      total: 2,
      page: 1,
      page_size: 20,
    });
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'Federation' })).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(
      await screen.findByText(/Manage master accounts and delegated sub-accounts/)
    ).toBeInTheDocument();
  });

  it('shows accounts after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Partner Federation')).toBeInTheDocument();
    });
    expect(screen.getByText('Secondary Federation')).toBeInTheDocument();
  });

  it('shows status badges', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
    });
    expect(screen.getByText('Suspended')).toBeInTheDocument();
  });

  it('shows sub-account counts', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('3 / 10')).toBeInTheDocument();
    });
    expect(screen.getByText('0 / 10')).toBeInTheDocument();
  });

  it('shows empty state when no accounts', async () => {
    mockListMasterAccounts.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('shows error message on failure', async () => {
    mockListMasterAccounts.mockRejectedValue(new Error('Network error'));
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(await screen.findByRole('heading', { name: 'Federation' })).toBeInTheDocument();
      });

      if (role === 'cpi-admin' || role === 'tenant-admin') {
        it('shows Create Account button', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          expect(await screen.findByText('Create Account')).toBeInTheDocument();
        });
      }

      if (role === 'devops' || role === 'viewer') {
        it('hides Create Account button', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          await waitFor(() => {
            expect(screen.getByText('Partner Federation')).toBeInTheDocument();
          });
          expect(screen.queryByText('Create Account')).not.toBeInTheDocument();
        });
      }
    }
  );
});
