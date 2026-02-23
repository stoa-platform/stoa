/**
 * Credential Mappings Page Tests (CAB-1432)
 *
 * Persona-based tests covering RBAC, CRUD states, and modal interactions.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  createAuthMock,
  createMockUser,
  renderWithProviders,
  type PersonaRole,
} from '../../test/helpers';
import { CredentialMappingsPage } from '../credential-mappings/CredentialMappingsPage';

// ============ Mocks ============

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../services/credentialMappings', () => ({
  credentialMappingsService: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    listByConsumer: vi.fn(),
  },
}));

import { useAuth } from '../../contexts/AuthContext';
import { credentialMappingsService } from '../../services/credentialMappings';

const mockUseAuth = vi.mocked(useAuth);
const mockService = vi.mocked(credentialMappingsService);

// ============ Test Data ============

function mockMapping(overrides: Record<string, unknown> = {}) {
  return {
    id: 'cm-1',
    consumer_id: '550e8400-e29b-41d4-a716-446655440000',
    api_id: 'weather-api-v1',
    tenant_id: 'oasis-gunters',
    auth_type: 'api_key' as const,
    header_name: 'X-API-Key',
    has_credential: true,
    description: 'ACME production key',
    is_active: true,
    created_at: '2026-02-23T10:00:00Z',
    updated_at: '2026-02-23T10:00:00Z',
    created_by: 'user-parzival',
    ...overrides,
  };
}

const defaultListResponse = {
  items: [
    mockMapping(),
    mockMapping({
      id: 'cm-2',
      api_id: 'payments-api-v2',
      auth_type: 'bearer',
      header_name: 'Authorization',
      description: 'Stripe bearer token',
    }),
  ],
  total: 2,
  page: 1,
  page_size: 20,
};

// ============ Setup ============

beforeEach(() => {
  vi.clearAllMocks();
  mockService.list.mockResolvedValue(defaultListResponse);
  mockService.create.mockResolvedValue(mockMapping());
  mockService.update.mockResolvedValue(mockMapping());
  mockService.delete.mockResolvedValue(undefined);
});

// ============ Persona Tests ============

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'CredentialMappingsPage — %s',
  (role) => {
    beforeEach(() => {
      mockUseAuth.mockReturnValue(createAuthMock(role));
    });

    it('renders page title and description', async () => {
      renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

      expect(screen.getByText('Credential Mappings')).toBeInTheDocument();
      expect(screen.getByText(/Map backend API credentials to consumers/)).toBeInTheDocument();
    });

    it('renders mapping list after loading', async () => {
      renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

      await waitFor(() => {
        expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
        expect(screen.getByText('payments-api-v2')).toBeInTheDocument();
      });
    });

    it('shows search input', () => {
      renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });
      expect(
        screen.getByPlaceholderText('Search by API, consumer, or header...')
      ).toBeInTheDocument();
    });

    if (role === 'cpi-admin' || role === 'tenant-admin') {
      it('shows Add Mapping button for write users', async () => {
        renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

        await waitFor(() => {
          expect(screen.getByText('Add Mapping')).toBeInTheDocument();
        });
      });

      it('shows edit and delete action buttons', async () => {
        renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

        await waitFor(() => {
          const editButtons = screen.getAllByTitle('Edit');
          const deleteButtons = screen.getAllByTitle('Delete');
          expect(editButtons.length).toBe(2);
          expect(deleteButtons.length).toBe(2);
        });
      });

      it('opens create modal when Add Mapping is clicked', async () => {
        const user = userEvent.setup();
        renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

        await waitFor(() => {
          expect(screen.getByText('Add Mapping')).toBeInTheDocument();
        });

        await user.click(screen.getByText('Add Mapping'));

        expect(screen.getByText('Add Credential Mapping')).toBeInTheDocument();
        expect(screen.getByLabelText('Consumer ID *')).toBeInTheDocument();
        expect(screen.getByLabelText('API ID *')).toBeInTheDocument();
        expect(screen.getByLabelText('Auth Type *')).toBeInTheDocument();
        expect(screen.getByLabelText('Header Name *')).toBeInTheDocument();
      });

      it('opens edit modal when edit button is clicked', async () => {
        const user = userEvent.setup();
        renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

        await waitFor(() => {
          expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
        });

        const editButtons = screen.getAllByTitle('Edit');
        await user.click(editButtons[0]);

        expect(screen.getByText('Edit Credential Mapping')).toBeInTheDocument();
        // Consumer ID and API ID should not be shown in edit mode
        expect(screen.queryByLabelText('Consumer ID *')).not.toBeInTheDocument();
        expect(screen.queryByLabelText('API ID *')).not.toBeInTheDocument();
      });

      it('submits create form with correct data', async () => {
        const expectedTenantId = createMockUser(role).tenant_id;
        const user = userEvent.setup();
        renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

        await waitFor(() => {
          expect(screen.getByText('Add Mapping')).toBeInTheDocument();
        });

        await user.click(screen.getByText('Add Mapping'));

        await user.type(screen.getByLabelText('Consumer ID *'), 'consumer-uuid');
        await user.type(screen.getByLabelText('API ID *'), 'test-api');
        await user.clear(screen.getByLabelText('Header Name *'));
        await user.type(screen.getByLabelText('Header Name *'), 'X-Custom-Key');
        await user.type(screen.getByLabelText(/Credential Value/), 'secret-key-123');
        await user.type(screen.getByLabelText('Description'), 'Test credential');

        await user.click(screen.getByText('Create Mapping'));

        await waitFor(() => {
          expect(mockService.create).toHaveBeenCalledWith(expectedTenantId, {
            consumer_id: 'consumer-uuid',
            api_id: 'test-api',
            auth_type: 'api_key',
            header_name: 'X-Custom-Key',
            credential_value: 'secret-key-123',
            description: 'Test credential',
          });
        });
      });

      it('calls delete service with confirmation', async () => {
        const expectedTenantId = createMockUser(role).tenant_id;
        const user = userEvent.setup();
        vi.spyOn(window, 'confirm').mockReturnValue(true);

        renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

        await waitFor(() => {
          expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
        });

        const deleteButtons = screen.getAllByTitle('Delete');
        await user.click(deleteButtons[0]);

        expect(window.confirm).toHaveBeenCalled();
        expect(mockService.delete).toHaveBeenCalledWith(expectedTenantId, 'cm-1');
      });
    } else {
      it('does NOT show Add Mapping button for read-only users', async () => {
        renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

        await waitFor(() => {
          expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
        });

        expect(screen.queryByText('Add Mapping')).not.toBeInTheDocument();
      });

      it('does NOT show edit/delete action buttons', async () => {
        renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

        await waitFor(() => {
          expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
        });

        expect(screen.queryByTitle('Edit')).not.toBeInTheDocument();
        expect(screen.queryByTitle('Delete')).not.toBeInTheDocument();
      });
    }
  }
);

// ============ State Tests ============

describe('CredentialMappingsPage — states', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('shows loading skeleton', () => {
    mockService.list.mockImplementation(() => new Promise(() => {}));

    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    const skeletons = document.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows error state with retry', async () => {
    mockService.list.mockRejectedValue(new Error('Network error'));

    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
      expect(screen.getByText('Try again')).toBeInTheDocument();
    });
  });

  it('shows empty state when no mappings', async () => {
    mockService.list.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });

    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    await waitFor(() => {
      expect(screen.getByText('No credential mappings yet')).toBeInTheDocument();
    });
  });

  it('shows empty state with search hint when search has no results', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    await waitFor(() => {
      expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
    });

    await user.type(
      screen.getByPlaceholderText('Search by API, consumer, or header...'),
      'nonexistent'
    );

    await waitFor(() => {
      expect(screen.getByText('No matching credentials')).toBeInTheDocument();
    });
  });

  it('filters by search query', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    await waitFor(() => {
      expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
      expect(screen.getByText('payments-api-v2')).toBeInTheDocument();
    });

    await user.type(
      screen.getByPlaceholderText('Search by API, consumer, or header...'),
      'weather'
    );

    await waitFor(() => {
      expect(screen.getByText('weather-api-v1')).toBeInTheDocument();
      expect(screen.queryByText('payments-api-v2')).not.toBeInTheDocument();
    });
  });

  it('displays auth type badges correctly', async () => {
    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    await waitFor(() => {
      expect(screen.getByText('API Key')).toBeInTheDocument();
      expect(screen.getByText('Bearer Token')).toBeInTheDocument();
    });
  });

  it('displays active/inactive status', async () => {
    mockService.list.mockResolvedValue({
      items: [mockMapping(), mockMapping({ id: 'cm-3', api_id: 'inactive-api', is_active: false })],
      total: 2,
      page: 1,
      page_size: 20,
    });

    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    await waitFor(() => {
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText('Inactive')).toBeInTheDocument();
    });
  });
});

// ============ Modal Tests ============

describe('CredentialMappingsPage — modal', () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('closes modal when Cancel is clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    await waitFor(() => {
      expect(screen.getByText('Add Mapping')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Add Mapping'));
    expect(screen.getByText('Add Credential Mapping')).toBeInTheDocument();

    await user.click(screen.getByText('Cancel'));

    await waitFor(() => {
      expect(screen.queryByText('Add Credential Mapping')).not.toBeInTheDocument();
    });
  });

  it('changes default header when auth type changes', async () => {
    const user = userEvent.setup();
    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    await waitFor(() => {
      expect(screen.getByText('Add Mapping')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Add Mapping'));

    // Default should be X-API-Key
    const headerInput = screen.getByLabelText('Header Name *') as HTMLInputElement;
    expect(headerInput.value).toBe('X-API-Key');

    // Change auth type to bearer
    await user.selectOptions(screen.getByLabelText('Auth Type *'), 'bearer');

    expect(headerInput.value).toBe('Authorization');
  });

  it('shows form error on create failure', async () => {
    mockService.create.mockRejectedValue(new Error('Duplicate mapping'));
    const user = userEvent.setup();

    renderWithProviders(<CredentialMappingsPage />, { route: '/credentials' });

    await waitFor(() => {
      expect(screen.getByText('Add Mapping')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Add Mapping'));
    await user.type(screen.getByLabelText('Consumer ID *'), 'c-id');
    await user.type(screen.getByLabelText('API ID *'), 'a-id');
    await user.type(screen.getByLabelText(/Credential Value/), 'secret');

    await user.click(screen.getByText('Create Mapping'));

    await waitFor(() => {
      expect(screen.getByText('Duplicate mapping')).toBeInTheDocument();
    });
  });
});
