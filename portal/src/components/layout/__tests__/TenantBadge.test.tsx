import { screen } from '@testing-library/react';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../../test/helpers';
import { TenantBadge } from '../TenantBadge';

const mockAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

describe('TenantBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'persona: %s',
    (role) => {
      it('renders tenant badge with organization name', () => {
        mockAuth.mockReturnValue(createAuthMock(role));
        renderWithProviders(<TenantBadge />);

        const badge = screen.getByTestId('tenant-badge');
        expect(badge).toBeInTheDocument();
        // All test personas have an organization set
        expect(badge).toHaveTextContent(/Games|Gunters/);
      });
    }
  );

  it('returns null when user is null', () => {
    mockAuth.mockReturnValue({ ...createAuthMock('viewer'), user: null });
    const { container } = renderWithProviders(<TenantBadge />);
    expect(container.firstChild).toBeNull();
  });

  it('returns null when user has no organization or tenant_id', () => {
    const auth = createAuthMock('viewer');
    auth.user = { ...auth.user, organization: undefined, tenant_id: undefined };
    mockAuth.mockReturnValue(auth);
    const { container } = renderWithProviders(<TenantBadge />);
    expect(container.firstChild).toBeNull();
  });

  it('falls back to tenant_id when organization is not set', () => {
    const auth = createAuthMock('viewer');
    auth.user = { ...auth.user, organization: undefined, tenant_id: 'acme-corp' };
    mockAuth.mockReturnValue(auth);
    renderWithProviders(<TenantBadge />);

    expect(screen.getByTestId('tenant-badge')).toHaveTextContent('acme-corp');
  });

  it('applies custom className', () => {
    renderWithProviders(<TenantBadge className="mt-2" />);
    expect(screen.getByTestId('tenant-badge').className).toContain('mt-2');
  });
});
