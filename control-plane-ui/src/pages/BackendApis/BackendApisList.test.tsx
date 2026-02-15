import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { createAuthMock, mockBackendApi, renderWithProviders } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock backendApisService
const mockListBackendApis = vi.fn().mockResolvedValue({
  items: [
    mockBackendApi(),
    mockBackendApi({
      id: 'bapi-2',
      name: 'weather-api',
      display_name: 'Weather API',
      backend_url: 'https://api.weather.dev/v1',
      auth_type: 'bearer',
      has_credentials: true,
      status: 'draft',
      tool_count: 3,
    }),
  ],
  total: 2,
  page: 1,
  page_size: 50,
});

vi.mock('../../services/backendApisApi', () => ({
  backendApisService: {
    listBackendApis: (...args: unknown[]) => mockListBackendApis(...args),
    createBackendApi: vi.fn().mockResolvedValue({}),
    updateBackendApi: vi.fn().mockResolvedValue({}),
    deleteBackendApi: vi.fn().mockResolvedValue(undefined),
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

// Mock RegisterApiModal
vi.mock('./RegisterApiModal', () => ({
  RegisterApiModal: () => <div data-testid="register-modal">Register Modal</div>,
}));

import { BackendApisList } from './BackendApisList';

function renderComponent() {
  return renderWithProviders(<BackendApisList />);
}

describe('BackendApisList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListBackendApis.mockResolvedValue({
      items: [
        mockBackendApi(),
        mockBackendApi({
          id: 'bapi-2',
          name: 'weather-api',
          display_name: 'Weather API',
          backend_url: 'https://api.weather.dev/v1',
          auth_type: 'bearer',
          has_credentials: true,
          status: 'draft',
          tool_count: 3,
        }),
      ],
      total: 2,
      page: 1,
      page_size: 50,
    });
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'Backend APIs' })).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderComponent();
    expect(await screen.findByText(/Register backend APIs/)).toBeInTheDocument();
  });

  it('shows API rows after loading', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Petstore API')).toBeInTheDocument();
    });
    expect(screen.getByText('Weather API')).toBeInTheDocument();
  });

  it('shows API slugs in mono font', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('petstore-api')).toBeInTheDocument();
    });
    expect(screen.getByText('weather-api')).toBeInTheDocument();
  });

  it('shows status badges', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getAllByText('Active').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText('Draft').length).toBeGreaterThanOrEqual(1);
  });

  it('shows auth type labels', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('API Key')).toBeInTheDocument();
    });
    expect(screen.getByText('Bearer')).toBeInTheDocument();
  });

  it('shows tool count', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('5')).toBeInTheDocument();
    });
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('shows Register API button for admin', async () => {
    renderComponent();
    expect(await screen.findByText('Register API')).toBeInTheDocument();
  });

  it('shows empty state when no APIs', async () => {
    mockListBackendApis.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 50 });
    renderComponent();
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(await screen.findByRole('heading', { name: 'Backend APIs' })).toBeInTheDocument();
      });

      if (role === 'viewer') {
        it('hides Register API button', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          await waitFor(() => {
            expect(screen.getByText('Petstore API')).toBeInTheDocument();
          });
          expect(screen.queryByText('Register API')).not.toBeInTheDocument();
        });

        it('hides Delete button', async () => {
          vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
          renderComponent();
          await waitFor(() => {
            expect(screen.getByText('Petstore API')).toBeInTheDocument();
          });
          expect(screen.queryByText('Delete')).not.toBeInTheDocument();
        });
      }
    }
  );
});
