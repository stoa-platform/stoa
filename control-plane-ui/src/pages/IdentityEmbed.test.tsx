import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import type { PersonaRole } from '../test/helpers';
import { IdentityEmbed } from './IdentityEmbed';

vi.mock('../config', () => ({
  config: {
    keycloak: {
      url: 'https://auth.gostoa.dev',
      realm: 'stoa',
      clientId: 'control-plane-ui',
    },
  },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

describe('IdentityEmbed', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    vi.spyOn(window, 'open').mockImplementation(() => null);
  });

  it('renders title heading', () => {
    render(<IdentityEmbed />);
    expect(screen.getByRole('heading', { name: 'Identity Management' })).toBeInTheDocument();
  });

  it('displays user name and email', () => {
    render(<IdentityEmbed />);
    expect(screen.getByText('James Halliday')).toBeInTheDocument();
    // Email appears in both profile card and account details
    expect(screen.getAllByText('halliday@gregarious-games.com')).toHaveLength(2);
  });

  it('displays role badge', () => {
    render(<IdentityEmbed />);
    expect(screen.getByText('Platform Administrator')).toBeInTheDocument();
  });

  it('displays tenant and access level', () => {
    render(<IdentityEmbed />);
    expect(screen.getByText('gregarious-games')).toBeInTheDocument();
    expect(screen.getByText('Full Platform Access')).toBeInTheDocument();
  });

  it('displays permission count', () => {
    render(<IdentityEmbed />);
    expect(screen.getByText(/\d+ active permissions/)).toBeInTheDocument();
  });

  it('manage in keycloak button calls window.open', () => {
    render(<IdentityEmbed />);
    const button = screen.getByText('Manage in Keycloak');
    fireEvent.click(button);
    expect(window.open).toHaveBeenCalledWith(
      'https://auth.gostoa.dev/realms/stoa/account',
      '_blank',
      'noopener,noreferrer'
    );
  });

  it('change password button opens correct keycloak URL', () => {
    render(<IdentityEmbed />);
    const button = screen.getByText('Change Password');
    fireEvent.click(button);
    expect(window.open).toHaveBeenCalledWith(
      'https://auth.gostoa.dev/realms/stoa/account/#/security/signingin',
      '_blank',
      'noopener,noreferrer'
    );
  });

  it('active sessions button opens correct keycloak URL', () => {
    render(<IdentityEmbed />);
    const button = screen.getByText('Active Sessions');
    fireEvent.click(button);
    expect(window.open).toHaveBeenCalledWith(
      'https://auth.gostoa.dev/realms/stoa/account/#/security/device-activity',
      '_blank',
      'noopener,noreferrer'
    );
  });

  it('displays authentication provider info', () => {
    render(<IdentityEmbed />);
    expect(screen.getByText('Keycloak OIDC (stoa realm)')).toBeInTheDocument();
    expect(screen.getByText('control-plane-ui')).toBeInTheDocument();
  });

  // 4-persona coverage
  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<IdentityEmbed />);
        expect(screen.getByRole('heading', { name: 'Identity Management' })).toBeInTheDocument();
      });
    }
  );
});
