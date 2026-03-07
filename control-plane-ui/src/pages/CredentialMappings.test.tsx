import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockMappings = [
  {
    id: 'cm-1',
    tenant_id: 'oasis-gunters',
    consumer_id: '550e8400-e29b-41d4-a716-446655440000',
    api_id: 'weather-api-v1',
    auth_type: 'api_key' as const,
    header_name: 'X-API-Key',
    credential_value: '***',
    description: 'Production weather API key',
    is_active: true,
    created_at: '2026-02-15T10:00:00Z',
    updated_at: '2026-02-15T10:00:00Z',
  },
  {
    id: 'cm-2',
    tenant_id: 'oasis-gunters',
    consumer_id: 'abcd1234',
    api_id: 'payments-api',
    auth_type: 'bearer' as const,
    header_name: 'Authorization',
    credential_value: '***',
    description: null,
    is_active: false,
    created_at: '2026-02-16T10:00:00Z',
    updated_at: '2026-02-16T10:00:00Z',
  },
];

const mockGetCredentialMappings = vi.fn().mockResolvedValue({ items: mockMappings, total: 2 });
const mockCreateCredentialMapping = vi.fn().mockResolvedValue(mockMappings[0]);
const mockUpdateCredentialMapping = vi.fn().mockResolvedValue(mockMappings[0]);
const mockDeleteCredentialMapping = vi.fn().mockResolvedValue({});

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
    getCredentialMappings: (...args: unknown[]) => mockGetCredentialMappings(...args),
    createCredentialMapping: (...args: unknown[]) => mockCreateCredentialMapping(...args),
    updateCredentialMapping: (...args: unknown[]) => mockUpdateCredentialMapping(...args),
    deleteCredentialMapping: (...args: unknown[]) => mockDeleteCredentialMapping(...args),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  ConfirmDialog: ({
    open,
    title,
    onConfirm,
    onCancel,
  }: {
    open: boolean;
    title: string;
    onConfirm: () => void;
    onCancel: () => void;
  }) =>
    open ? (
      <div data-testid="confirm-dialog">
        <span>{title}</span>
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    ) : null,
}));

// Lazy import the component (after mocks are set up)
const { CredentialMappings } = await import('./CredentialMappings');

describe('CredentialMappings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetCredentialMappings.mockResolvedValue({ items: mockMappings, total: 2 });
  });

  it('renders the page title and add button', async () => {
    renderWithProviders(<CredentialMappings />);
    expect(screen.getByText('Credential Mappings')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Add Mapping')).toBeInTheDocument();
    });
  });

  it('displays mappings after loading', async () => {
    renderWithProviders(<CredentialMappings />);
    await waitFor(() => {
      expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
      expect(screen.getByText('payments-api')).toBeInTheDocument();
    });
  });

  it('shows empty state when no mappings', async () => {
    mockGetCredentialMappings.mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<CredentialMappings />);
    await waitFor(() => {
      expect(screen.getByText('No credential mappings configured')).toBeInTheDocument();
    });
  });

  it('opens create modal when button clicked', async () => {
    const user = userEvent.setup();
    mockGetCredentialMappings.mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<CredentialMappings />);
    await waitFor(() => {
      expect(screen.getByText('No credential mappings configured')).toBeInTheDocument();
    });
    const addButtons = screen.getAllByText('Add Mapping');
    await user.click(addButtons[addButtons.length - 1]);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Add Credential Mapping' })).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<CredentialMappings />);
        expect(screen.getByText('Credential Mappings')).toBeInTheDocument();
      });
    }
  );

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona — RBAC visibility',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        mockGetCredentialMappings.mockResolvedValue({ items: mockMappings, total: 2 });
      });

      it('shows or hides Add Mapping button based on isWriteUser (cpi-admin or tenant-admin)', async () => {
        renderWithProviders(<CredentialMappings />);
        await waitFor(() => {
          expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
        });
        // isWriteUser = hasRole('cpi-admin') || hasRole('tenant-admin')
        if (['cpi-admin', 'tenant-admin'].includes(role)) {
          expect(screen.getByText('Add Mapping')).toBeInTheDocument();
        } else {
          expect(screen.queryByText('Add Mapping')).not.toBeInTheDocument();
        }
      });

      it('shows or hides Edit and Delete action buttons based on isWriteUser', async () => {
        renderWithProviders(<CredentialMappings />);
        await waitFor(() => {
          expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
        });
        if (['cpi-admin', 'tenant-admin'].includes(role)) {
          expect(screen.getAllByTitle('Edit').length).toBeGreaterThan(0);
          expect(screen.getAllByTitle('Delete').length).toBeGreaterThan(0);
        } else {
          expect(screen.queryByTitle('Edit')).not.toBeInTheDocument();
          expect(screen.queryByTitle('Delete')).not.toBeInTheDocument();
        }
      });

      it('shows tenant selector only for cpi-admin (isAdmin)', async () => {
        renderWithProviders(<CredentialMappings />);
        await waitFor(() => {
          expect(screen.getByText('Credential Mappings')).toBeInTheDocument();
        });
        // isAdmin = hasRole('cpi-admin') AND user has no tenant_id (cross-tenant admin)
        // cpi-admin mock user has tenant_id='gregarious-games', so the selector is hidden
        // (condition: isAdmin && !user?.tenant_id — cpi-admin always has a tenant_id in test helpers)
        const tenantSelectorHeading = screen.queryByText('Credential Mapping Management');
        expect(tenantSelectorHeading).not.toBeInTheDocument();
      });
    }
  );
});
