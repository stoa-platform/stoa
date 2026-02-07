import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

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
      { id: 'oasis-gunters', name: 'oasis-gunters', display_name: 'Oasis Gunters', status: 'active', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:00:00Z' },
      { id: 'ioi-sixers', name: 'ioi-sixers', display_name: 'IOI Sixers', status: 'active', created_at: '2024-01-02T00:00:00Z', updated_at: '2024-01-02T00:00:00Z' },
    ]),
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

vi.mock('@stoa/shared/components/EmptyState', () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { Tenants } from './Tenants';

function renderTenants() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Tenants />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Tenants', () => {
  it('renders the page heading', async () => {
    renderTenants();
    expect(await screen.findByText('Tenants')).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderTenants();
    expect(await screen.findByText('View tenant organizations')).toBeInTheDocument();
  });

  it('renders the GitOps phase 2 notice', async () => {
    renderTenants();
    expect(await screen.findByText('Tenant management via GitOps (Phase 2)')).toBeInTheDocument();
  });

  it('renders tenant display names from API', async () => {
    renderTenants();
    expect(await screen.findByText('Oasis Gunters')).toBeInTheDocument();
    expect(screen.getByText('IOI Sixers')).toBeInTheDocument();
  });

  it('renders tenant slug names', async () => {
    renderTenants();
    // Wait for data to load first
    await screen.findByText('Oasis Gunters');
    // Slug name may appear in multiple elements (name + ID)
    const slugElements = screen.getAllByText('oasis-gunters');
    expect(slugElements.length).toBeGreaterThanOrEqual(1);
  });

  it('renders tenant status badges', async () => {
    renderTenants();
    const badges = await screen.findAllByText('active');
    expect(badges.length).toBeGreaterThanOrEqual(2);
  });

  it('shows empty state when no tenants', async () => {
    const { apiService } = await import('../services/api');
    (apiService.getTenants as ReturnType<typeof vi.fn>).mockResolvedValueOnce([]);
    renderTenants();
    expect(await screen.findByText('No tenants found')).toBeInTheDocument();
  });
});
