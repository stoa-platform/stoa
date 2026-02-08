import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

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
    get: vi.fn().mockRejectedValue(new Error('Use demo data')),
  },
}));

vi.mock('../config', () => ({
  config: {
    services: {
      grafana: { url: '/grafana/' },
    },
  },
}));

vi.mock('../utils/navigation', () => ({
  observabilityPath: (url: string) => url,
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

import { APIMonitoring } from './APIMonitoring';

function renderAPIMonitoring() {
  return render(
    <MemoryRouter>
      <APIMonitoring />
    </MemoryRouter>
  );
}

describe('APIMonitoring', () => {
  it('renders the page heading', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('API Monitoring')).toBeInTheDocument();
  });

  it('renders the subtitle', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText(/Real-time E2E transaction tracing/)).toBeInTheDocument();
  });

  it('renders the search input placeholder', async () => {
    renderAPIMonitoring();
    expect(
      await screen.findByPlaceholderText('Search by trace ID, API, or path...')
    ).toBeInTheDocument();
  });

  it('renders the auto-refresh toggle button (Live by default)', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Live')).toBeInTheDocument();
  });

  it('renders the Refresh button', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Refresh')).toBeInTheDocument();
  });

  it('renders stats cards when demo data loads', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Total Requests')).toBeInTheDocument();
    expect(screen.getByText('Success Rate')).toBeInTheDocument();
    expect(screen.getByText('Avg Latency')).toBeInTheDocument();
    expect(screen.getByText('APDEX')).toBeInTheDocument();
    expect(screen.getByText('Errors')).toBeInTheDocument();
  });

  it('renders transaction table column headers', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Trace ID')).toBeInTheDocument();
    expect(screen.getByText('Method')).toBeInTheDocument();
    expect(screen.getByText('API / Path')).toBeInTheDocument();
    expect(screen.getByText('Duration')).toBeInTheDocument();
  });

  it('renders the Open in Grafana button', async () => {
    renderAPIMonitoring();
    expect(await screen.findByText('Open in Grafana')).toBeInTheDocument();
  });
});
