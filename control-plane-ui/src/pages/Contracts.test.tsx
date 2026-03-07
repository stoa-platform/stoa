import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createAuthMock, renderWithProviders } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

const mockContracts = [
  {
    id: 'ctr-1',
    tenant_id: 'oasis-gunters',
    name: 'weather-api',
    display_name: 'Weather API',
    description: 'Weather data contract',
    version: '1.0.0',
    status: 'published' as const,
    openapi_spec_url: 'https://api.example.com/openapi.json',
    bindings: [
      {
        protocol: 'rest' as const,
        enabled: true,
        endpoint: 'https://api.example.com/v1/weather',
        playground_url: null,
        tool_name: null,
        operations: ['GET /forecast'],
        proto_file_url: null,
        topic_name: null,
        traffic_24h: 1250,
      },
      {
        protocol: 'mcp' as const,
        enabled: true,
        endpoint: 'https://mcp.example.com/weather',
        playground_url: null,
        tool_name: 'get_weather',
        operations: [],
        proto_file_url: null,
        topic_name: null,
        traffic_24h: 340,
      },
      {
        protocol: 'graphql' as const,
        enabled: false,
        endpoint: null,
        playground_url: null,
        tool_name: null,
        operations: [],
        proto_file_url: null,
        topic_name: null,
        traffic_24h: null,
      },
    ],
    created_at: '2026-02-15T10:00:00Z',
    updated_at: '2026-02-15T10:00:00Z',
  },
  {
    id: 'ctr-2',
    tenant_id: 'oasis-gunters',
    name: 'payments-api',
    display_name: 'Payments API',
    description: null,
    version: '2.1.0',
    status: 'draft' as const,
    openapi_spec_url: null,
    bindings: [],
    created_at: '2026-02-16T10:00:00Z',
    updated_at: '2026-02-16T10:00:00Z',
  },
];

const mockGetContracts = vi.fn().mockResolvedValue({ items: mockContracts, total: 2 });
const mockGetContract = vi.fn().mockResolvedValue(mockContracts[0]);
const mockCreateContract = vi.fn().mockResolvedValue(mockContracts[0]);
const mockUpdateContract = vi.fn().mockResolvedValue({
  ...mockContracts[0],
  display_name: 'Updated Weather API',
});
const mockDeleteContract = vi.fn().mockResolvedValue({});
const mockPublishContract = vi.fn().mockResolvedValue({
  contract: { ...mockContracts[0], status: 'published' as const },
  bindings_generated: [
    { protocol: 'rest', endpoint: 'https://api.example.com/v1/weather', tool_name: null },
    { protocol: 'mcp', endpoint: 'https://mcp.example.com/weather', tool_name: 'get_weather' },
  ],
});
const mockEnableBinding = vi.fn().mockResolvedValue({});
const mockDisableBinding = vi.fn().mockResolvedValue({});

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
    getContracts: (...args: unknown[]) => mockGetContracts(...args),
    getContract: (...args: unknown[]) => mockGetContract(...args),
    createContract: (...args: unknown[]) => mockCreateContract(...args),
    updateContract: (...args: unknown[]) => mockUpdateContract(...args),
    deleteContract: (...args: unknown[]) => mockDeleteContract(...args),
    publishContract: (...args: unknown[]) => mockPublishContract(...args),
    enableBinding: (...args: unknown[]) => mockEnableBinding(...args),
    disableBinding: (...args: unknown[]) => mockDisableBinding(...args),
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
const { Contracts } = await import('./Contracts');

describe('Contracts', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    mockGetContracts.mockResolvedValue({ items: mockContracts, total: 2 });
  });

  it('renders the page title and create button', async () => {
    renderWithProviders(<Contracts />);
    expect(screen.getByText('Contracts')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Create Contract')).toBeInTheDocument();
    });
  });

  it('displays contracts after loading', async () => {
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('Weather API')).toBeInTheDocument();
      expect(screen.getByText('Payments API')).toBeInTheDocument();
    });
  });

  it('shows empty state when no contracts', async () => {
    mockGetContracts.mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('No contracts configured')).toBeInTheDocument();
    });
  });

  it('shows protocol binding badges on contract cards', async () => {
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
    // Protocol badges are rendered for each contract
    const restBadges = screen.getAllByText('REST');
    expect(restBadges.length).toBeGreaterThan(0);
    const mcpBadges = screen.getAllByText('MCP');
    expect(mcpBadges.length).toBeGreaterThan(0);
  });

  it('shows contract status badge', async () => {
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('published')).toBeInTheDocument();
      expect(screen.getByText('draft')).toBeInTheDocument();
    });
  });

  it('opens create view when button clicked', async () => {
    const user = userEvent.setup();
    mockGetContracts.mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('No contracts configured')).toBeInTheDocument();
    });
    const createButtons = screen.getAllByText('Create Contract');
    await user.click(createButtons[createButtons.length - 1]);
    await waitFor(() => {
      expect(screen.getByText('Create New Contract')).toBeInTheDocument();
    });
  });

  it('shows confirm dialog when delete clicked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
    // Click delete button (trash icon)
    const deleteButtons = screen.getAllByTitle('Delete');
    await user.click(deleteButtons[0]);
    await waitFor(() => {
      expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
    });
  });

  it('deletes a contract when confirm dialog is confirmed', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
    const deleteButtons = screen.getAllByTitle('Delete');
    await user.click(deleteButtons[0]);
    await waitFor(() => {
      expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Confirm'));
    await waitFor(() => {
      expect(mockDeleteContract).toHaveBeenCalledWith('gregarious-games', 'ctr-1');
    });
  });

  it('cancels delete when dialog is dismissed', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Contracts />);
    await waitFor(() => {
      expect(screen.getByText('Weather API')).toBeInTheDocument();
    });
    const deleteButtons = screen.getAllByTitle('Delete');
    await user.click(deleteButtons[0]);
    await waitFor(() => {
      expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
    });
    await user.click(screen.getByText('Cancel'));
    expect(mockDeleteContract).not.toHaveBeenCalled();
  });

  describe('CreateContractView', () => {
    it('submits form as draft', async () => {
      const user = userEvent.setup();
      mockGetContracts.mockResolvedValue({ items: [], total: 0 });
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('No contracts configured')).toBeInTheDocument();
      });

      // Navigate to create view
      const createButtons = screen.getAllByText('Create Contract');
      await user.click(createButtons[createButtons.length - 1]);
      await waitFor(() => {
        expect(screen.getByText('Create New Contract')).toBeInTheDocument();
      });

      // Fill form
      await user.type(screen.getByPlaceholderText('my-api-contract'), 'test-contract');
      await user.type(screen.getByPlaceholderText('My API Contract'), 'Test Contract');

      // Submit as draft
      await user.click(screen.getByText('Save as Draft'));
      await waitFor(() => {
        expect(mockCreateContract).toHaveBeenCalledWith(
          'gregarious-games',
          expect.objectContaining({
            name: 'test-contract',
            display_name: 'Test Contract',
            status: 'draft',
          })
        );
      });
    });

    it('submits form and publishes, showing generated bindings', async () => {
      const user = userEvent.setup();
      mockGetContracts.mockResolvedValue({ items: [], total: 0 });
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('No contracts configured')).toBeInTheDocument();
      });

      const createButtons = screen.getAllByText('Create Contract');
      await user.click(createButtons[createButtons.length - 1]);
      await waitFor(() => {
        expect(screen.getByText('Create New Contract')).toBeInTheDocument();
      });

      await user.type(screen.getByPlaceholderText('my-api-contract'), 'test-contract');
      await user.type(screen.getByPlaceholderText('My API Contract'), 'Test Contract');

      // Submit and publish
      await user.click(screen.getByText('Create & Publish'));
      await waitFor(() => {
        expect(mockPublishContract).toHaveBeenCalled();
        expect(screen.getByText('Contract Published Successfully')).toBeInTheDocument();
      });
    });

    it('fills all form fields including description, version, and spec URL', async () => {
      const user = userEvent.setup();
      mockGetContracts.mockResolvedValue({ items: [], total: 0 });
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('No contracts configured')).toBeInTheDocument();
      });

      const createButtons = screen.getAllByText('Create Contract');
      await user.click(createButtons[createButtons.length - 1]);
      await waitFor(() => {
        expect(screen.getByText('Create New Contract')).toBeInTheDocument();
      });

      // Fill all fields to exercise all onChange handlers
      await user.type(screen.getByPlaceholderText('my-api-contract'), 'full-contract');
      await user.type(screen.getByPlaceholderText('My API Contract'), 'Full Contract');
      const versionInput = screen.getByPlaceholderText('1.0.0');
      await user.clear(versionInput);
      await user.type(versionInput, '2.0.0');
      await user.type(screen.getByPlaceholderText('https://...'), 'https://spec.example.com');

      // Find and type into the description textarea
      const textareas = document.querySelectorAll('textarea');
      if (textareas.length > 0) {
        await user.type(textareas[0], 'A detailed contract description');
      }

      await user.click(screen.getByText('Save as Draft'));
      await waitFor(() => {
        expect(mockCreateContract).toHaveBeenCalledWith(
          'gregarious-games',
          expect.objectContaining({
            name: 'full-contract',
            display_name: 'Full Contract',
            version: '2.0.0',
            openapi_spec_url: 'https://spec.example.com',
            status: 'draft',
          })
        );
      });
    });

    it('handles error when creating contract fails', async () => {
      const user = userEvent.setup();
      mockCreateContract.mockRejectedValueOnce(new Error('Server error'));
      mockGetContracts.mockResolvedValue({ items: [], total: 0 });
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('No contracts configured')).toBeInTheDocument();
      });

      const createButtons = screen.getAllByText('Create Contract');
      await user.click(createButtons[createButtons.length - 1]);
      await waitFor(() => {
        expect(screen.getByText('Create New Contract')).toBeInTheDocument();
      });

      await user.type(screen.getByPlaceholderText('my-api-contract'), 'fail-contract');
      await user.type(screen.getByPlaceholderText('My API Contract'), 'Fail Contract');

      await user.click(screen.getByText('Save as Draft'));
      await waitFor(() => {
        expect(mockCreateContract).toHaveBeenCalled();
      });
    });
  });

  describe('ContractDetailView', () => {
    it('opens detail view when clicking a contract card', async () => {
      const user = userEvent.setup();
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('Weather API')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Weather API'));
      await waitFor(() => {
        expect(screen.getByText('Protocol Bindings')).toBeInTheDocument();
      });
    });

    it('toggles a binding off', async () => {
      const user = userEvent.setup();
      mockGetContract.mockResolvedValue(mockContracts[0]);
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('Weather API')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Weather API'));
      await waitFor(() => {
        expect(screen.getByText('Protocol Bindings')).toBeInTheDocument();
      });

      // Click the first "Disable" toggle (REST is enabled)
      const disableButtons = screen.getAllByTitle('Disable');
      await user.click(disableButtons[0]);
      await waitFor(() => {
        expect(mockDisableBinding).toHaveBeenCalledWith('gregarious-games', 'ctr-1', 'rest');
      });
    });

    it('toggles a binding on', async () => {
      const user = userEvent.setup();
      mockGetContract.mockResolvedValue(mockContracts[0]);
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('Weather API')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Weather API'));
      await waitFor(() => {
        expect(screen.getByText('Protocol Bindings')).toBeInTheDocument();
      });

      // Click an "Enable" toggle (GraphQL is disabled)
      const enableButtons = screen.getAllByTitle('Enable');
      await user.click(enableButtons[0]);
      await waitFor(() => {
        expect(mockEnableBinding).toHaveBeenCalled();
      });
    });

    it('publishes a draft contract from detail view', async () => {
      const user = userEvent.setup();
      // Use the draft contract (ctr-2)
      mockGetContracts.mockResolvedValue({ items: [mockContracts[1]], total: 1 });
      mockGetContract.mockResolvedValue(mockContracts[1]);
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('Payments API')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Payments API'));
      await waitFor(() => {
        expect(screen.getByText('Publish')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Publish'));
      await waitFor(() => {
        expect(mockPublishContract).toHaveBeenCalledWith('gregarious-games', 'ctr-2');
      });
    });

    it('opens edit form and saves changes', async () => {
      const user = userEvent.setup();
      mockGetContract.mockResolvedValue(mockContracts[0]);
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('Weather API')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Weather API'));
      await waitFor(() => {
        expect(screen.getByText('Protocol Bindings')).toBeInTheDocument();
      });

      // Click edit button
      await user.click(screen.getByTitle('Edit'));
      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument();
      });

      // Modify all form fields to exercise onChange handlers
      const displayNameInput = screen.getByDisplayValue('Weather API');
      await user.clear(displayNameInput);
      await user.type(displayNameInput, 'Updated Weather API');

      const descInput = screen.getByDisplayValue('Weather data contract');
      await user.clear(descInput);
      await user.type(descInput, 'Updated desc');

      const versionInput = screen.getByDisplayValue('1.0.0');
      await user.clear(versionInput);
      await user.type(versionInput, '2.0.0');

      // Save edit
      await user.click(screen.getByText('Save'));
      await waitFor(() => {
        expect(mockUpdateContract).toHaveBeenCalledWith(
          'gregarious-games',
          'ctr-1',
          expect.objectContaining({ display_name: 'Updated Weather API' })
        );
      });
    });

    it('cancels editing', async () => {
      const user = userEvent.setup();
      mockGetContract.mockResolvedValue(mockContracts[0]);
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('Weather API')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Weather API'));
      await waitFor(() => {
        expect(screen.getByText('Protocol Bindings')).toBeInTheDocument();
      });

      await user.click(screen.getByTitle('Edit'));
      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument();
      });

      // Cancel editing
      const cancelButtons = screen.getAllByText('Cancel');
      await user.click(cancelButtons[cancelButtons.length - 1]);
      await waitFor(() => {
        expect(screen.queryByText('Save')).not.toBeInTheDocument();
      });
    });

    it('handles error when publishing fails', async () => {
      const user = userEvent.setup();
      mockGetContracts.mockResolvedValue({ items: [mockContracts[1]], total: 1 });
      mockGetContract.mockResolvedValue(mockContracts[1]);
      mockPublishContract.mockRejectedValueOnce(new Error('Network error'));
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('Payments API')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Payments API'));
      await waitFor(() => {
        expect(screen.getByText('Publish')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Publish'));
      await waitFor(() => {
        expect(mockPublishContract).toHaveBeenCalled();
      });
    });

    it('handles error when toggling binding fails', async () => {
      const user = userEvent.setup();
      mockGetContract.mockResolvedValue(mockContracts[0]);
      mockDisableBinding.mockRejectedValueOnce(new Error('Network error'));
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('Weather API')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Weather API'));
      await waitFor(() => {
        expect(screen.getByText('Protocol Bindings')).toBeInTheDocument();
      });

      const disableButtons = screen.getAllByTitle('Disable');
      await user.click(disableButtons[0]);
      await waitFor(() => {
        expect(mockDisableBinding).toHaveBeenCalled();
      });
    });

    it('handles error when saving edit fails', async () => {
      const user = userEvent.setup();
      mockGetContract.mockResolvedValue(mockContracts[0]);
      mockUpdateContract.mockRejectedValueOnce(new Error('Network error'));
      renderWithProviders(<Contracts />);
      await waitFor(() => {
        expect(screen.getByText('Weather API')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Weather API'));
      await waitFor(() => {
        expect(screen.getByText('Protocol Bindings')).toBeInTheDocument();
      });

      await user.click(screen.getByTitle('Edit'));
      await waitFor(() => {
        expect(screen.getByText('Save')).toBeInTheDocument();
      });

      await user.click(screen.getByText('Save'));
      await waitFor(() => {
        expect(mockUpdateContract).toHaveBeenCalled();
      });
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<Contracts />);
        expect(screen.getByText('Contracts')).toBeInTheDocument();
      });
    }
  );

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona — RBAC visibility',
    (role) => {
      beforeEach(() => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        mockGetContracts.mockResolvedValue({ items: mockContracts, total: 2 });
      });

      it('shows or hides Create Contract button based on apis:update permission', async () => {
        renderWithProviders(<Contracts />);
        await waitFor(() => {
          expect(screen.getByText('Weather API')).toBeInTheDocument();
        });
        // cpi-admin, tenant-admin, devops all have apis:update — viewer does not
        if (role === 'viewer') {
          expect(screen.queryByText('Create Contract')).not.toBeInTheDocument();
        } else {
          expect(screen.getByText('Create Contract')).toBeInTheDocument();
        }
      });

      it('shows or hides Delete button on contract cards based on apis:update permission', async () => {
        renderWithProviders(<Contracts />);
        await waitFor(() => {
          expect(screen.getByText('Weather API')).toBeInTheDocument();
        });
        if (role === 'viewer') {
          expect(screen.queryByTitle('Delete')).not.toBeInTheDocument();
        } else {
          expect(screen.getAllByTitle('Delete').length).toBeGreaterThan(0);
        }
      });

      it('shows tenant selector only for cpi-admin', async () => {
        renderWithProviders(<Contracts />);
        await waitFor(() => {
          expect(screen.getByText('Weather API')).toBeInTheDocument();
        });
        // isAdmin = hasRole('cpi-admin') — only cpi-admin sees the tenant selector
        const selects = document.querySelectorAll('select');
        if (role === 'cpi-admin') {
          expect(selects.length).toBeGreaterThan(0);
        } else {
          expect(selects.length).toBe(0);
        }
      });
    }
  );
});
