import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

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
    ]),
    getApplications: vi.fn().mockResolvedValue([
      {
        id: 'app-1',
        tenant_id: 'oasis-gunters',
        name: 'mobile-app',
        display_name: 'Mobile App',
        description: 'iOS/Android mobile application',
        client_id: 'client-abc123',
        status: 'approved',
        api_subscriptions: ['api-1'],
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-15T00:00:00Z',
      },
      {
        id: 'app-2',
        tenant_id: 'oasis-gunters',
        name: 'web-app',
        display_name: 'Web Application',
        description: 'Main web application',
        client_id: 'client-def456',
        status: 'pending',
        api_subscriptions: [],
        created_at: '2024-01-10T00:00:00Z',
        updated_at: '2024-01-10T00:00:00Z',
      },
    ]),
    createApplication: vi.fn(),
    updateApplication: vi.fn(),
    deleteApplication: vi.fn(),
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
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { Applications } from './Applications';

function renderApplications() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Applications />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Applications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the page heading', async () => {
    renderApplications();
    expect(
      await screen.findByText('Manage consumer applications and API subscriptions')
    ).toBeInTheDocument();
  });

  it('renders the Create Application button', async () => {
    renderApplications();
    expect(await screen.findByText('Create Application')).toBeInTheDocument();
  });

  it('renders the search input label', async () => {
    renderApplications();
    expect(await screen.findByText('Search')).toBeInTheDocument();
  });

  it('renders application display names', async () => {
    renderApplications();
    expect(await screen.findByText('Mobile App')).toBeInTheDocument();
    expect(screen.getByText('Web Application')).toBeInTheDocument();
  });

  it('renders application descriptions', async () => {
    renderApplications();
    expect(await screen.findByText('iOS/Android mobile application')).toBeInTheDocument();
    expect(screen.getByText('Main web application')).toBeInTheDocument();
  });

  it('renders application status badges', async () => {
    renderApplications();
    expect(await screen.findByText('approved')).toBeInTheDocument();
    expect(screen.getByText('pending')).toBeInTheDocument();
  });

  it('renders the tenant selector', async () => {
    renderApplications();
    await waitFor(() => {
      const select = screen.getByDisplayValue('Oasis Gunters');
      expect(select).toBeInTheDocument();
    });
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderApplications();
        expect(
          await screen.findByText('Manage consumer applications and API subscriptions')
        ).toBeInTheDocument();
      });
    }
  );
});
