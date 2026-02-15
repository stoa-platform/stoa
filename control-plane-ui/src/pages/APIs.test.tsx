import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../contexts/EnvironmentContext', () => ({
  useEnvironment: vi.fn(() => ({
    activeEnvironment: 'dev',
    activeConfig: { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
    environments: [
      { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
      { name: 'staging', label: 'Staging', mode: 'full', color: 'amber' },
      { name: 'prod', label: 'Production', mode: 'read-only', color: 'red' },
    ],
    switchEnvironment: vi.fn(),
  })),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../services/api', () => ({
  apiService: {
    getTenants: vi.fn().mockResolvedValue([
      {
        id: 'oasis-gunters',
        name: 'oasis-gunters',
        display_name: 'Oasis Gunters',
        status: 'active',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:00:00Z',
      },
    ]),
    getApis: vi.fn().mockResolvedValue([
      {
        id: 'api-1',
        tenant_id: 'oasis-gunters',
        name: 'payment-api',
        display_name: 'Payment API',
        version: '1.0.0',
        description: 'Handles all payment processing',
        backend_url: 'https://payments.example.com',
        status: 'published',
        deployed_dev: true,
        deployed_staging: false,
        tags: ['payments'],
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-15T00:00:00Z',
      },
      {
        id: 'api-2',
        tenant_id: 'oasis-gunters',
        name: 'user-api',
        display_name: 'User API',
        version: '2.0.0',
        description: 'User management service',
        backend_url: 'https://users.example.com',
        status: 'draft',
        deployed_dev: false,
        deployed_staging: false,
        tags: ['users'],
        created_at: '2024-01-05T00:00:00Z',
        updated_at: '2024-01-10T00:00:00Z',
      },
    ]),
    createApi: vi.fn(),
    updateApi: vi.fn(),
    deleteApi: vi.fn(),
    deployApi: vi.fn(),
  },
}));

vi.mock('@stoa/shared/components/Toast', () => ({
  ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useToast: () => ({ addToast: vi.fn() }),
  useToastActions: () => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }),
}));

vi.mock('@stoa/shared/components/CommandPalette', () => ({
  CommandPaletteProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useCommandPalette: () => ({ setOpen: vi.fn(), setItems: vi.fn() }),
}));

vi.mock('@stoa/shared/contexts', () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useTheme: () => ({ resolvedTheme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('@stoa/shared/hooks', () => ({
  useSequenceShortcuts: vi.fn(),
}));

vi.mock('@stoa/shared/components/ConfirmDialog', () => ({
  useConfirm: () => [vi.fn().mockResolvedValue(true), () => null],
}));

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  TableSkeleton: () => <div data-testid="table-skeleton" />,
}));

vi.mock('@stoa/shared/components/Celebration', () => ({
  useCelebration: () => ({ celebrate: vi.fn() }),
}));

vi.mock('@stoa/shared/components/Collapsible', () => ({
  Collapsible: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const mockUseEnvironmentMode = vi.fn(() => ({
  canCreate: true,
  canEdit: true,
  canDelete: true,
  canDeploy: true,
  isReadOnly: false,
}));

vi.mock('../hooks/useEnvironmentMode', () => ({
  useEnvironmentMode: () => mockUseEnvironmentMode(),
}));

import { APIs } from './APIs';

const READ_ONLY_MODE = {
  canCreate: false,
  canEdit: false,
  canDelete: false,
  canDeploy: false,
  isReadOnly: true,
};

function renderAPIs() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <APIs />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('APIs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  afterEach(() => {
    mockUseEnvironmentMode.mockReturnValue({
      canCreate: true,
      canEdit: true,
      canDelete: true,
      canDeploy: true,
      isReadOnly: false,
    });
  });

  it('renders the page heading', async () => {
    renderAPIs();
    expect(await screen.findByText('Manage API definitions and deployments')).toBeInTheDocument();
  });

  it('renders the Create API button', async () => {
    renderAPIs();
    expect(await screen.findByText('Create API')).toBeInTheDocument();
  });

  it('renders the search input label', async () => {
    renderAPIs();
    expect(await screen.findByText('Search')).toBeInTheDocument();
  });

  it('renders API display names from data', async () => {
    renderAPIs();
    expect(await screen.findByText('Payment API')).toBeInTheDocument();
    expect(screen.getByText('User API')).toBeInTheDocument();
  });

  it('renders the tenant selector with first tenant auto-selected', async () => {
    renderAPIs();
    await waitFor(() => {
      const select = screen.getByDisplayValue('Oasis Gunters');
      expect(select).toBeInTheDocument();
    });
  });

  it('renders status filter dropdown', async () => {
    renderAPIs();
    expect(await screen.findByText('All Status')).toBeInTheDocument();
  });

  it('renders API status badges', async () => {
    renderAPIs();
    expect(await screen.findByText('published')).toBeInTheDocument();
    expect(screen.getByText('draft')).toBeInTheDocument();
  });

  it('renders API backend URLs', async () => {
    renderAPIs();
    expect(await screen.findByText('https://payments.example.com')).toBeInTheDocument();
    expect(screen.getByText('https://users.example.com')).toBeInTheDocument();
  });

  it('hides Create API button in read-only mode', async () => {
    mockUseEnvironmentMode.mockReturnValue(READ_ONLY_MODE);
    renderAPIs();
    await screen.findByText('Payment API');
    expect(screen.queryByText('Create API')).not.toBeInTheDocument();
  });

  it('shows read-only banner in read-only mode', async () => {
    mockUseEnvironmentMode.mockReturnValue(READ_ONLY_MODE);
    renderAPIs();
    expect(await screen.findByText(/Production environment — read-only/)).toBeInTheDocument();
  });

  it('hides Edit and Delete buttons in read-only mode', async () => {
    mockUseEnvironmentMode.mockReturnValue(READ_ONLY_MODE);
    renderAPIs();
    await screen.findByText('Payment API');
    expect(screen.queryByText('Edit')).not.toBeInTheDocument();
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
  });

  it('hides Deploy buttons in read-only mode', async () => {
    mockUseEnvironmentMode.mockReturnValue(READ_ONLY_MODE);
    renderAPIs();
    await screen.findByText('Payment API');
    expect(screen.queryByText('Deploy DEV')).not.toBeInTheDocument();
    expect(screen.queryByText('Deploy STG')).not.toBeInTheDocument();
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderAPIs();
        expect(
          await screen.findByText('Manage API definitions and deployments')
        ).toBeInTheDocument();
      });
    }
  );
});
