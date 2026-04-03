import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock, createMockUser, mockBackendApi } from '../../test/helpers';
import type { PersonaRole } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import { BackendApiDetail } from './BackendApiDetail';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockGetBackendApi = vi.fn();
const mockUpdateBackendApi = vi.fn();
const mockDeleteBackendApi = vi.fn();

vi.mock('../../services/backendApisApi', () => ({
  backendApisService: {
    getBackendApi: (...args: unknown[]) => mockGetBackendApi(...args),
    updateBackendApi: (...args: unknown[]) => mockUpdateBackendApi(...args),
    deleteBackendApi: (...args: unknown[]) => mockDeleteBackendApi(...args),
  },
}));

const mockToast = { success: vi.fn(), error: vi.fn(), info: vi.fn() };
vi.mock('@stoa/shared/components/Toast', () => ({
  useToastActions: () => mockToast,
}));

const mockConfirm = vi.fn();
vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [mockConfirm, null],
}));

const testApi = mockBackendApi();

function createTestQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
}

function renderDetail(apiId = 'bapi-1') {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/backend-apis/${apiId}`]}>
        <Routes>
          <Route path="/backend-apis/:id" element={<BackendApiDetail />} />
          <Route path="/apis" element={<div>APIs List</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function getTenantId(role: PersonaRole): string {
  return createMockUser(role).tenant_id;
}

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  '%s persona',
  (role) => {
    beforeEach(() => {
      vi.clearAllMocks();
      vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
      mockGetBackendApi.mockResolvedValue(testApi);
      mockUpdateBackendApi.mockResolvedValue(testApi);
      mockConfirm.mockResolvedValue(true);
    });

    it('renders API detail with metadata', async () => {
      renderDetail();

      await waitFor(() => {
        expect(screen.getByText('Petstore API')).toBeInTheDocument();
      });

      expect(screen.getByText('petstore-api')).toBeInTheDocument();
      expect(screen.getByText('https://petstore.swagger.io/v2')).toBeInTheDocument();
      expect(screen.getByText('API Key')).toBeInTheDocument();
      expect(screen.getByText('Active')).toBeInTheDocument();
      expect(screen.getByText(/5 tools generated/)).toBeInTheDocument();
    });

    it('shows description when available', async () => {
      renderDetail();

      await waitFor(() => {
        expect(screen.getByText('Sample Petstore backend')).toBeInTheDocument();
      });
    });

    it('shows openapi spec url when available', async () => {
      renderDetail();

      await waitFor(() => {
        expect(screen.getByText('https://petstore.swagger.io/v2/swagger.json')).toBeInTheDocument();
      });
    });

    it('shows credentials status', async () => {
      renderDetail();

      await waitFor(() => {
        expect(screen.getByText('credentials configured')).toBeInTheDocument();
      });
    });

    it('shows error state when API not found', async () => {
      mockGetBackendApi.mockRejectedValue(new Error('Not found'));
      renderDetail();

      await waitFor(() => {
        expect(screen.getByText('Not found')).toBeInTheDocument();
      });
      expect(screen.getByText('Back to Backend APIs')).toBeInTheDocument();
    });

    // cpi-admin, tenant-admin, devops all have apis:update
    if (role !== 'viewer') {
      it('shows edit button', async () => {
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Edit')).toBeInTheDocument();
        });
      });

      it('enters edit mode and shows form fields', async () => {
        const user = userEvent.setup();
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Edit')).toBeInTheDocument();
        });

        await user.click(screen.getByText('Edit'));

        expect(screen.getByText('Edit Configuration')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Petstore API')).toBeInTheDocument();
        expect(screen.getByDisplayValue('Sample Petstore backend')).toBeInTheDocument();
        expect(screen.getByDisplayValue('https://petstore.swagger.io/v2')).toBeInTheDocument();
      });

      it('saves changes on edit', async () => {
        const user = userEvent.setup();
        const tenantId = getTenantId(role);
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Edit')).toBeInTheDocument();
        });

        await user.click(screen.getByText('Edit'));
        const nameInput = screen.getByDisplayValue('Petstore API');
        await user.clear(nameInput);
        await user.type(nameInput, 'Updated API');
        await user.click(screen.getByText('Save Changes'));

        await waitFor(() => {
          expect(mockUpdateBackendApi).toHaveBeenCalledWith(
            tenantId,
            'bapi-1',
            expect.objectContaining({
              display_name: 'Updated API',
            })
          );
        });
      });

      it('cancels edit mode', async () => {
        const user = userEvent.setup();
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Edit')).toBeInTheDocument();
        });

        await user.click(screen.getByText('Edit'));
        expect(screen.getByText('Edit Configuration')).toBeInTheDocument();

        await user.click(screen.getByText('Cancel'));
        expect(screen.queryByText('Edit Configuration')).not.toBeInTheDocument();
      });

      it('shows toggle status button for non-draft APIs', async () => {
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Disable')).toBeInTheDocument();
        });
      });

      it('toggles status on click', async () => {
        const user = userEvent.setup();
        const tenantId = getTenantId(role);
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Disable')).toBeInTheDocument();
        });

        await user.click(screen.getByText('Disable'));

        await waitFor(() => {
          expect(mockUpdateBackendApi).toHaveBeenCalledWith(tenantId, 'bapi-1', {
            status: 'disabled',
          });
        });
      });

      it('does not show toggle for draft APIs', async () => {
        mockGetBackendApi.mockResolvedValue(mockBackendApi({ status: 'draft' }));
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Petstore API')).toBeInTheDocument();
        });

        expect(screen.queryByText('Disable')).not.toBeInTheDocument();
        expect(screen.queryByText('Enable')).not.toBeInTheDocument();
      });
    }

    // Only cpi-admin and tenant-admin have apis:delete
    if (role === 'cpi-admin' || role === 'tenant-admin') {
      it('shows delete button', async () => {
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Delete')).toBeInTheDocument();
        });
      });

      it('deletes API after confirmation', async () => {
        const user = userEvent.setup();
        const tenantId = getTenantId(role);
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Delete')).toBeInTheDocument();
        });

        await user.click(screen.getByText('Delete'));

        await waitFor(() => {
          expect(mockConfirm).toHaveBeenCalled();
          expect(mockDeleteBackendApi).toHaveBeenCalledWith(tenantId, 'bapi-1');
        });
      });
    }

    if (role === 'devops') {
      it('does not show delete button', async () => {
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Petstore API')).toBeInTheDocument();
        });

        expect(screen.queryByText('Delete')).not.toBeInTheDocument();
      });
    }

    if (role === 'viewer') {
      it('does not show edit button', async () => {
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Petstore API')).toBeInTheDocument();
        });

        expect(screen.queryByText('Edit')).not.toBeInTheDocument();
      });

      it('does not show delete button', async () => {
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Petstore API')).toBeInTheDocument();
        });

        expect(screen.queryByText('Delete')).not.toBeInTheDocument();
      });

      it('does not show status toggle', async () => {
        renderDetail();

        await waitFor(() => {
          expect(screen.getByText('Petstore API')).toBeInTheDocument();
        });

        expect(screen.queryByText('Disable')).not.toBeInTheDocument();
        expect(screen.queryByText('Enable')).not.toBeInTheDocument();
      });
    }
  }
);
