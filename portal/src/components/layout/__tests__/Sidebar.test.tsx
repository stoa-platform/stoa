import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders, createAuthMock } from '../../../test/helpers';
import { Sidebar } from '../Sidebar';

const mockAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

vi.mock('../../../config', () => ({
  config: {
    features: {
      enableAPICatalog: true,
      enableMCPTools: true,
      enableSubscriptions: true,
      enableGateways: true,
      enableI18n: false,
    },
    services: { console: { url: 'https://console.example.com' } },
    baseDomain: 'example.com',
    app: { version: '1.0.0' },
  },
}));

vi.mock('../TenantBadge', () => ({
  TenantBadge: ({ className }: { className?: string }) => (
    <div data-testid="tenant-badge" className={className} />
  ),
}));

describe('Sidebar', () => {
  const onClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth.mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders Discover section with API Catalog and AI Tools for cpi-admin', () => {
    renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);

    expect(screen.getByText('Discover')).toBeInTheDocument();
    expect(screen.getByText('API Catalog')).toBeInTheDocument();
    expect(screen.getByText('AI Tools')).toBeInTheDocument();
  });

  it('renders My Workspace section', () => {
    renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);

    expect(screen.getByText('My Workspace')).toBeInTheDocument();
    expect(screen.getByText('My Apps & Credentials')).toBeInTheDocument();
  });

  it('renders Account section with Profile and Console', () => {
    renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);

    expect(screen.getByText('Account')).toBeInTheDocument();
    expect(screen.getByText('Profile')).toBeInTheDocument();
    expect(screen.getByText('Console')).toBeInTheDocument();
  });

  it('renders version number in footer', () => {
    renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);

    expect(screen.getByText('v1.0.0')).toBeInTheDocument();
  });

  it('renders close button on mobile', () => {
    renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);

    const closeButton = screen.getByRole('button', { name: 'Close menu' });
    expect(closeButton).toBeInTheDocument();
    fireEvent.click(closeButton);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('hides admin items for viewer role', () => {
    mockAuth.mockReturnValue(createAuthMock('viewer'));
    renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);

    expect(screen.queryByText('Gateways')).not.toBeInTheDocument();
  });
});
