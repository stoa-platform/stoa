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

vi.mock('../hooks/useAdminUsers', () => ({
  useAdminUsers: vi.fn(() => ({
    data: {
      data: [
        {
          id: 'u-1',
          email: 'admin@acme.com',
          name: 'Alice Admin',
          roles: ['cpi-admin'],
          tenant_id: null,
          tenant_name: null,
          status: 'active',
          last_login_at: '2024-06-15T10:00:00Z',
          created_at: '2024-01-01T00:00:00Z',
        },
        {
          id: 'u-2',
          email: 'dev@acme.com',
          name: 'Bob Dev',
          roles: ['devops', 'viewer'],
          tenant_id: 't-1',
          tenant_name: 'Acme Corp',
          status: 'suspended',
          last_login_at: null,
          created_at: '2024-03-10T00:00:00Z',
        },
      ],
      total: 2,
      page: 1,
      limit: 25,
    },
    isLoading: false,
    error: null,
  })),
}));

import { AdminUsers } from './AdminUsers';

function renderAdminUsers() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AdminUsers />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AdminUsers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the User Management heading', () => {
    renderAdminUsers();
    expect(screen.getByText('User Management')).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderAdminUsers();
    expect(
      screen.getByText('Manage platform users, roles, and account status')
    ).toBeInTheDocument();
  });

  it('renders user names in the table', () => {
    renderAdminUsers();
    expect(screen.getByText('Alice Admin')).toBeInTheDocument();
    expect(screen.getByText('Bob Dev')).toBeInTheDocument();
  });

  it('renders user emails', () => {
    renderAdminUsers();
    expect(screen.getByText('admin@acme.com')).toBeInTheDocument();
    expect(screen.getByText('dev@acme.com')).toBeInTheDocument();
  });

  it('renders user role badges', () => {
    renderAdminUsers();
    expect(screen.getByText('cpi-admin')).toBeInTheDocument();
    expect(screen.getByText('devops')).toBeInTheDocument();
    expect(screen.getByText('viewer')).toBeInTheDocument();
  });

  it('renders user status badges', () => {
    renderAdminUsers();
    expect(screen.getByText('active')).toBeInTheDocument();
    expect(screen.getByText('suspended')).toBeInTheDocument();
  });

  it('renders the search input', () => {
    renderAdminUsers();
    expect(screen.getByPlaceholderText('Search by name or email...')).toBeInTheDocument();
  });

  it('renders the total user count', () => {
    renderAdminUsers();
    expect(screen.getByText('2 users')).toBeInTheDocument();
  });

  it('renders tenant name for assigned users', () => {
    renderAdminUsers();
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page with correct access', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderAdminUsers();
        if (role === 'cpi-admin') {
          expect(screen.getByText('User Management')).toBeInTheDocument();
        } else {
          expect(screen.getByText('Access Denied')).toBeInTheDocument();
        }
      });
    }
  );
});
