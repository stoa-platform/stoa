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

vi.mock('../hooks/usePlatformSettings', () => ({
  usePlatformSettings: vi.fn(() => ({
    data: {
      settings: [
        {
          key: 'platform.name',
          value: 'STOA Platform',
          category: 'general',
          description: 'Platform display name',
          editable: true,
          updated_at: '2024-06-10T12:00:00Z',
        },
        {
          key: 'security.mfa_required',
          value: 'true',
          category: 'security',
          description: 'Require MFA for all users',
          editable: false,
          updated_at: '2024-05-01T08:00:00Z',
        },
      ],
      total: 2,
    },
    isLoading: false,
    error: null,
  })),
  useUpdatePlatformSetting: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
}));

import { AdminSettings } from './AdminSettings';

function renderAdminSettings() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AdminSettings />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AdminSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the Platform Settings heading', () => {
    renderAdminSettings();
    expect(screen.getByText('Platform Settings')).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderAdminSettings();
    expect(screen.getByText('Configure platform-wide settings and parameters')).toBeInTheDocument();
  });

  it('renders setting keys in the table', () => {
    renderAdminSettings();
    expect(screen.getByText('platform.name')).toBeInTheDocument();
    expect(screen.getByText('security.mfa_required')).toBeInTheDocument();
  });

  it('renders setting values', () => {
    renderAdminSettings();
    expect(screen.getByText('STOA Platform')).toBeInTheDocument();
    expect(screen.getByText('true')).toBeInTheDocument();
  });

  it('renders setting descriptions', () => {
    renderAdminSettings();
    expect(screen.getByText('Platform display name')).toBeInTheDocument();
    expect(screen.getByText('Require MFA for all users')).toBeInTheDocument();
  });

  it('renders category badges', () => {
    renderAdminSettings();
    const generals = screen.getAllByText('General');
    expect(generals.length).toBeGreaterThanOrEqual(1);
    const securities = screen.getAllByText('Security');
    expect(securities.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the total settings count', () => {
    renderAdminSettings();
    expect(screen.getByText('2 settings')).toBeInTheDocument();
  });

  it('renders Edit button for editable settings only', () => {
    renderAdminSettings();
    const editButtons = screen.getAllByText('Edit');
    expect(editButtons).toHaveLength(1);
  });

  it('renders the category filter', () => {
    renderAdminSettings();
    expect(screen.getByText('All categories')).toBeInTheDocument();
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page with correct access', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderAdminSettings();
        if (role === 'cpi-admin') {
          expect(screen.getByText('Platform Settings')).toBeInTheDocument();
        } else {
          expect(screen.getByText('Access Denied')).toBeInTheDocument();
        }
      });
    }
  );
});
