import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
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
    getProspects: vi.fn().mockResolvedValue({
      data: [
        {
          id: 'p-1',
          email: 'ceo@acme.com',
          company: 'Acme Corp',
          status: 'converted',
          source: 'website',
          created_at: '2024-01-01T00:00:00Z',
          opened_at: '2024-01-02T00:00:00Z',
          last_activity_at: '2024-01-10T00:00:00Z',
          time_to_first_tool_seconds: 120,
          nps_score: 9,
          nps_category: 'promoter',
          total_events: 15,
        },
        {
          id: 'p-2',
          email: 'dev@startup.io',
          company: 'Startup IO',
          status: 'opened',
          source: 'referral',
          created_at: '2024-01-05T00:00:00Z',
          opened_at: '2024-01-06T00:00:00Z',
          total_events: 5,
        },
      ],
      meta: { total: 2, page: 1, limit: 25 },
    }),
    getProspectsMetrics: vi.fn().mockResolvedValue({
      total_invited: 50,
      total_active: 20,
      avg_time_to_tool: 95,
      avg_nps: 8.2,
      by_status: { total_invites: 50, pending: 10, opened: 15, converted: 20, expired: 5 },
      nps: {
        promoters: 12,
        passives: 5,
        detractors: 3,
        no_response: 30,
        nps_score: 45,
        avg_score: 8.2,
      },
      timing: { avg_time_to_open_seconds: 3600, avg_time_to_first_tool_seconds: 7200 },
      top_companies: [{ company: 'Acme Corp', invite_count: 5, converted_count: 3 }],
    }),
    exportProspectsCSV: vi.fn(),
    refreshProspects: vi.fn(),
  },
}));

// Mock the custom hooks that AdminProspects uses
vi.mock('../hooks/useProspects', () => ({
  useProspects: vi.fn(() => ({
    data: {
      data: [
        {
          id: 'p-1',
          email: 'ceo@acme.com',
          company: 'Acme Corp',
          status: 'converted',
          source: 'website',
          created_at: '2024-01-01T00:00:00Z',
          opened_at: '2024-01-02T00:00:00Z',
          last_activity_at: '2024-01-10T00:00:00Z',
          time_to_first_tool_seconds: 120,
          nps_score: 9,
          nps_category: 'promoter',
          total_events: 15,
        },
        {
          id: 'p-2',
          email: 'dev@startup.io',
          company: 'Startup IO',
          status: 'opened',
          source: 'referral',
          created_at: '2024-01-05T00:00:00Z',
          opened_at: '2024-01-06T00:00:00Z',
          total_events: 5,
        },
      ],
      meta: { total: 2, page: 1, limit: 25 },
    },
    isLoading: false,
    error: null,
  })),
  useProspectsMetrics: vi.fn(() => ({
    data: {
      total_invited: 50,
      total_active: 20,
      avg_time_to_tool: 95,
      avg_nps: 8.2,
      by_status: { total_invites: 50, pending: 10, opened: 15, converted: 20, expired: 5 },
      nps: {
        promoters: 12,
        passives: 5,
        detractors: 3,
        no_response: 30,
        nps_score: 45,
        avg_score: 8.2,
      },
      timing: { avg_time_to_open_seconds: 3600, avg_time_to_first_tool_seconds: 7200 },
      top_companies: [{ company: 'Acme Corp', invite_count: 5, converted_count: 3 }],
    },
    isLoading: false,
  })),
  useProspectDetail: vi.fn(() => ({
    data: undefined,
    isLoading: false,
  })),
  useExportProspectsCSV: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
  useRefreshProspects: vi.fn(() => ({
    refresh: vi.fn(),
  })),
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

import { AdminProspects } from './AdminProspects';

function renderAdminProspects() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AdminProspects />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AdminProspects', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the Prospects Dashboard heading', () => {
    renderAdminProspects();
    expect(screen.getByText('Prospects Dashboard')).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderAdminProspects();
    expect(screen.getByText('Conversion tracking for demo prospects')).toBeInTheDocument();
  });

  it('renders the Invites metric card', () => {
    renderAdminProspects();
    expect(screen.getByText('Invites')).toBeInTheDocument();
  });

  it('renders the Active metric card', () => {
    renderAdminProspects();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders prospect company names in the table', () => {
    renderAdminProspects();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('Startup IO')).toBeInTheDocument();
  });

  it('renders the search input with company placeholder', () => {
    renderAdminProspects();
    expect(screen.getByPlaceholderText('Search by company...')).toBeInTheDocument();
  });

  it('renders prospect email addresses', () => {
    renderAdminProspects();
    expect(screen.getByText('ceo@acme.com')).toBeInTheDocument();
    expect(screen.getByText('dev@startup.io')).toBeInTheDocument();
  });

  it('renders prospect status badges', () => {
    renderAdminProspects();
    expect(screen.getByText('converted')).toBeInTheDocument();
    expect(screen.getByText('opened')).toBeInTheDocument();
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page with correct access', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderAdminProspects();
        if (role === 'cpi-admin') {
          expect(screen.getByText('Prospects Dashboard')).toBeInTheDocument();
        } else {
          expect(screen.getByText('Access Denied')).toBeInTheDocument();
        }
      });
    }
  );
});
