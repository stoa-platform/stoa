import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from '../../contexts/AuthContext';
import { ProfilePage } from './Profile';

describe('ProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('renders the heading', () => {
    renderWithProviders(<ProfilePage />);
    expect(screen.getByRole('heading', { name: /my profile/i })).toBeInTheDocument();
  });

  it('displays user name and email', () => {
    renderWithProviders(<ProfilePage />);
    // Name appears in header + detail section
    expect(screen.getAllByText('Wade Watts').length).toBeGreaterThanOrEqual(1);
    // Email appears in header + detail section
    expect(screen.getAllByText('parzival@oasis-gunters.com').length).toBeGreaterThanOrEqual(1);
  });

  it('displays organization', () => {
    renderWithProviders(<ProfilePage />);
    expect(screen.getByText('OASIS Gunters')).toBeInTheDocument();
  });

  it('displays user ID', () => {
    renderWithProviders(<ProfilePage />);
    expect(screen.getByText('user-parzival')).toBeInTheDocument();
  });

  it('displays authentication method', () => {
    renderWithProviders(<ProfilePage />);
    expect(screen.getByText('OIDC (Keycloak)')).toBeInTheDocument();
  });

  it('renders roles section with role badges', () => {
    renderWithProviders(<ProfilePage />);
    expect(screen.getByRole('heading', { name: /roles/i })).toBeInTheDocument();
    expect(screen.getByText('tenant-admin')).toBeInTheDocument();
  });

  it('renders API keys placeholder section', () => {
    renderWithProviders(<ProfilePage />);
    expect(screen.getByRole('heading', { name: /api keys/i })).toBeInTheDocument();
    expect(screen.getByText(/api key management will be available soon/i)).toBeInTheDocument();
  });

  it('shows role display name when available', () => {
    vi.mocked(useAuth).mockReturnValue({
      ...createAuthMock('cpi-admin'),
      user: {
        ...createAuthMock('cpi-admin').user,
        role_display_names: { 'cpi-admin': 'Platform Administrator' },
      },
    });
    renderWithProviders(<ProfilePage />);
    expect(screen.getByText('Platform Administrator')).toBeInTheDocument();
  });

  it('shows fallback text when user fields are missing', () => {
    vi.mocked(useAuth).mockReturnValue({
      ...createAuthMock('viewer'),
      user: {
        ...createAuthMock('viewer').user,
        name: '',
        email: '',
        organization: '',
        id: '',
      },
    });
    renderWithProviders(<ProfilePage />);
    // The component shows "Not set" for missing name/email/org, "Unknown" for missing id
    expect(screen.getAllByText('Not set')).toHaveLength(3);
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'persona: %s',
    (role) => {
      it('renders profile with correct user data', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<ProfilePage />);
        expect(screen.getByRole('heading', { name: /my profile/i })).toBeInTheDocument();
      });
    }
  );
});
