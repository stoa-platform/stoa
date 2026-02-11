import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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
  useAuth: vi.fn(() => ({
    user: {
      id: 'user-admin',
      email: 'parzival@oasis.gg',
      name: 'Parzival',
      roles: ['cpi-admin'],
      tenant_id: 'oasis-gunters',
      permissions: ['tenants:read', 'apis:read', 'apps:read', 'audit:read', 'admin:servers'],
    },
    isAuthenticated: true,
    isLoading: false,
    isReady: true,
    login: vi.fn(),
    logout: vi.fn(),
    hasPermission: vi.fn(() => true),
    hasRole: vi.fn(() => true),
  })),
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

import { APIs } from './APIs';

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
});
