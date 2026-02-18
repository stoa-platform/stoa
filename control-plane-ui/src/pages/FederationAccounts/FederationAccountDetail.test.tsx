import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import {
  createAuthMock,
  renderWithProviders,
  mockMasterAccount,
  mockSubAccount,
} from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock useParams to return { id: 'master-1' }
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useParams: vi.fn().mockReturnValue({ id: 'master-1' }),
  };
});

// Mock federation service
const mockGetMasterAccount = vi.fn();
const mockListSubAccounts = vi.fn();

vi.mock('../../services/federationApi', () => ({
  federationService: {
    getMasterAccount: (...args: unknown[]) => mockGetMasterAccount(...args),
    listSubAccounts: (...args: unknown[]) => mockListSubAccounts(...args),
    updateMasterAccount: vi.fn().mockResolvedValue({}),
    deleteMasterAccount: vi.fn().mockResolvedValue({}),
    revokeSubAccount: vi.fn().mockResolvedValue({}),
    createSubAccount: vi.fn().mockResolvedValue({}),
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

// Mock modals
vi.mock('./SubAccountModal', () => ({
  SubAccountModal: () => <div data-testid="sub-account-modal">Sub-Account Modal</div>,
}));

vi.mock('./ApiKeyRevealDialog', () => ({
  ApiKeyRevealDialog: () => <div data-testid="api-key-dialog">API Key Dialog</div>,
}));

import { FederationAccountDetail } from './FederationAccountDetail';
import { useParams } from 'react-router-dom';

const defaultAccount = mockMasterAccount();
const defaultSubAccounts = {
  items: [
    mockSubAccount(),
    mockSubAccount({
      id: 'sub-2',
      name: 'Internal Bot',
      status: 'revoked',
      api_key_prefix: 'stoa_fed_c3d4',
      allowed_tools: ['tool-3'],
      last_used_at: null,
    }),
  ],
  total: 2,
  page: 1,
  page_size: 20,
};

function renderComponent() {
  return renderWithProviders(<FederationAccountDetail />, {
    route: '/federation/accounts/master-1',
  });
}

describe('FederationAccountDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useParams).mockReturnValue({ id: 'master-1' });
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetMasterAccount.mockResolvedValue(defaultAccount);
    mockListSubAccounts.mockResolvedValue(defaultSubAccounts);
  });

  it('renders the account name', async () => {
    renderComponent();
    expect(await screen.findByText('Partner Federation')).toBeInTheDocument();
  });

  it('renders the status badge', async () => {
    renderComponent();
    const badges = await screen.findAllByText('Active');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('renders sub-account count', async () => {
    renderComponent();
    expect(await screen.findByText('3 / 10')).toBeInTheDocument();
  });

  it('renders sub-accounts table', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Partner Agent')).toBeInTheDocument();
    });
    expect(screen.getByText('Internal Bot')).toBeInTheDocument();
  });

  it('shows API key prefix', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('stoa_fed_a1b2...')).toBeInTheDocument();
    });
  });

  it('shows tools count', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('2')).toBeInTheDocument();
    });
  });

  it('shows empty state when no sub-accounts', async () => {
    mockListSubAccounts.mockResolvedValue({
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

  it('shows account not found', async () => {
    mockGetMasterAccount.mockResolvedValue(null);
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Account not found')).toBeInTheDocument();
    });
  });

  it('shows back link', async () => {
    renderComponent();
    expect(await screen.findByText('Back to Federation')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(await screen.findByText('Partner Federation')).toBeInTheDocument();
      });

      if (role === 'cpi-admin' || role === 'tenant-admin') {
        it('shows admin actions', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          await waitFor(() => {
            expect(screen.getByText('Suspend')).toBeInTheDocument();
          });
          expect(screen.getByText('Delete')).toBeInTheDocument();
          expect(screen.getByText('Add Sub-Account')).toBeInTheDocument();
        });
      }

      if (role === 'devops' || role === 'viewer') {
        it('hides admin actions', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          await waitFor(() => {
            expect(screen.getByText('Partner Federation')).toBeInTheDocument();
          });
          expect(screen.queryByText('Suspend')).not.toBeInTheDocument();
          expect(screen.queryByText('Delete')).not.toBeInTheDocument();
          expect(screen.queryByText('Add Sub-Account')).not.toBeInTheDocument();
        });
      }
    }
  );
});
