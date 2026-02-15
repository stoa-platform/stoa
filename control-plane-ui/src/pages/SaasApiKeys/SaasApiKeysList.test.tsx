import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import {
  createAuthMock,
  mockSaasApiKey,
  mockBackendApi,
  renderWithProviders,
} from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock backendApisService
const mockListSaasKeys = vi.fn().mockResolvedValue({
  items: [
    mockSaasApiKey(),
    mockSaasApiKey({
      id: 'skey-2',
      name: 'ci-key',
      description: 'Key for CI pipelines',
      key_prefix: 'stoa_saas_c3d4',
      allowed_backend_api_ids: [],
      rate_limit_rpm: null,
      status: 'revoked',
      expires_at: null,
      last_used_at: null,
    }),
  ],
  total: 2,
  page: 1,
  page_size: 50,
});

const mockListBackendApis = vi.fn().mockResolvedValue({
  items: [mockBackendApi()],
  total: 1,
  page: 1,
  page_size: 50,
});

vi.mock('../../services/backendApisApi', () => ({
  backendApisService: {
    listSaasKeys: (...args: unknown[]) => mockListSaasKeys(...args),
    listBackendApis: (...args: unknown[]) => mockListBackendApis(...args),
    createSaasKey: vi.fn().mockResolvedValue({
      id: 'skey-new',
      name: 'new-key',
      key: 'stoa_saas_xxxx_full_secret_key_here',
      key_prefix: 'stoa_saas_xxxx',
    }),
    revokeSaasKey: vi.fn().mockResolvedValue(undefined),
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

// Mock CreateKeyModal
vi.mock('./CreateKeyModal', () => ({
  CreateKeyModal: () => <div data-testid="create-modal">Create Modal</div>,
}));

import { SaasApiKeysList } from './SaasApiKeysList';

function renderComponent() {
  return renderWithProviders(<SaasApiKeysList />);
}

describe('SaasApiKeysList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListSaasKeys.mockResolvedValue({
      items: [
        mockSaasApiKey(),
        mockSaasApiKey({
          id: 'skey-2',
          name: 'ci-key',
          description: 'Key for CI pipelines',
          key_prefix: 'stoa_saas_c3d4',
          allowed_backend_api_ids: [],
          rate_limit_rpm: null,
          status: 'revoked',
          expires_at: null,
          last_used_at: null,
        }),
      ],
      total: 2,
      page: 1,
      page_size: 50,
    });
    mockListBackendApis.mockResolvedValue({
      items: [mockBackendApi()],
      total: 1,
      page: 1,
      page_size: 50,
    });
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'API Keys' })).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(await screen.findByText(/Create scoped API keys/)).toBeInTheDocument();
  });

  it('shows key rows after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('my-agent-key')).toBeInTheDocument();
    });
    expect(screen.getByText('ci-key')).toBeInTheDocument();
  });

  it('shows key prefixes', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('stoa_saas_a1b2...')).toBeInTheDocument();
    });
    expect(screen.getByText('stoa_saas_c3d4...')).toBeInTheDocument();
  });

  it('shows status badges', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
    });
    expect(screen.getByText('Revoked')).toBeInTheDocument();
  });

  it('shows RPM limit', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('60')).toBeInTheDocument();
    });
  });

  it('shows Create Key button for admin', async () => {
    renderComponent();
    expect(await screen.findByText('Create Key')).toBeInTheDocument();
  });

  it('shows empty state when no keys', async () => {
    mockListSaasKeys.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  it('shows allowed APIs count', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('1 API')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(await screen.findByRole('heading', { name: 'API Keys' })).toBeInTheDocument();
      });

      if (role === 'viewer') {
        it('hides Create Key button', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          await waitFor(() => {
            expect(screen.getByText('my-agent-key')).toBeInTheDocument();
          });
          expect(screen.queryByText('Create Key')).not.toBeInTheDocument();
        });

        it('hides Revoke button', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          await waitFor(() => {
            expect(screen.getByText('my-agent-key')).toBeInTheDocument();
          });
          expect(screen.queryByText('Revoke')).not.toBeInTheDocument();
        });
      }
    }
  );
});
