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

vi.mock('../hooks/useAdminRoles', () => ({
  useAdminRoles: vi.fn(() => ({
    data: {
      roles: [
        {
          name: 'cpi-admin',
          display_name: 'Platform Admin',
          description: 'Full platform access',
          permissions: [
            { name: 'stoa:admin', description: 'Full admin access' },
            { name: 'stoa:write', description: 'Write access' },
          ],
          user_count: 3,
        },
        {
          name: 'viewer',
          display_name: 'Viewer',
          description: 'Read-only access',
          permissions: [{ name: 'stoa:read', description: 'Read access' }],
          user_count: 12,
        },
      ],
      total: 2,
    },
    isLoading: false,
    error: null,
  })),
}));

import { AdminRoles } from './AdminRoles';

function renderAdminRoles() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AdminRoles />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AdminRoles', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the Roles & Permissions heading', () => {
    renderAdminRoles();
    expect(screen.getByText('Roles & Permissions')).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    renderAdminRoles();
    expect(
      screen.getByText('Platform RBAC role definitions and their associated permissions')
    ).toBeInTheDocument();
  });

  it('renders role display names', () => {
    renderAdminRoles();
    expect(screen.getByText('Platform Admin')).toBeInTheDocument();
    expect(screen.getByText('Viewer')).toBeInTheDocument();
  });

  it('renders role descriptions', () => {
    renderAdminRoles();
    expect(screen.getByText('Full platform access')).toBeInTheDocument();
    expect(screen.getByText('Read-only access')).toBeInTheDocument();
  });

  it('renders permission names', () => {
    renderAdminRoles();
    expect(screen.getByText('stoa:admin')).toBeInTheDocument();
    expect(screen.getByText('stoa:write')).toBeInTheDocument();
    expect(screen.getByText('stoa:read')).toBeInTheDocument();
  });

  it('renders user counts', () => {
    renderAdminRoles();
    expect(screen.getByText('3 users')).toBeInTheDocument();
    expect(screen.getByText('12 users')).toBeInTheDocument();
  });

  it('renders Permissions section headers', () => {
    renderAdminRoles();
    const permHeaders = screen.getAllByText('Permissions');
    expect(permHeaders.length).toBeGreaterThanOrEqual(2);
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page with correct access', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderAdminRoles();
        if (role === 'cpi-admin') {
          expect(screen.getByText('Roles & Permissions')).toBeInTheDocument();
        } else {
          expect(screen.getByText('Access Denied')).toBeInTheDocument();
        }
      });
    }
  );
});
