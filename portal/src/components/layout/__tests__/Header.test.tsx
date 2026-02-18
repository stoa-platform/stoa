import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { Header } from '../Header';
import { renderWithProviders, createAuthMock } from '../../../test/helpers';

const mockUseAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../../../config', () => ({
  config: {
    features: {
      enableI18n: false,
    },
    services: {
      console: { url: 'https://console.gostoa.dev' },
    },
  },
}));

// Mock shared components
vi.mock('@stoa/shared/components/StoaLogo', () => ({
  StoaLogo: () => <div data-testid="stoa-logo" />,
}));

vi.mock('@stoa/shared/components/ThemeToggle', () => ({
  ThemeToggle: () => <button data-testid="theme-toggle" />,
}));

vi.mock('../LanguageToggle', () => ({
  LanguageToggle: () => <button data-testid="language-toggle" />,
}));

describe('Header', () => {
  const mockOnMenuClick = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
    mockOnMenuClick.mockReset();
  });

  it('renders the STOA logo', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    expect(screen.getByTestId('stoa-logo')).toBeInTheDocument();
  });

  it('renders the user name in the user button', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    expect(screen.getByText('Wade Watts')).toBeInTheDocument();
  });

  it('renders menu button for mobile', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    const menuButton = screen.getByRole('button', { name: 'Open menu' });
    expect(menuButton).toBeInTheDocument();
  });

  it('calls onMenuClick when menu button is clicked', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
    expect(mockOnMenuClick).toHaveBeenCalledTimes(1);
  });

  it('renders notifications button', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
  });

  it('renders user menu button', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    expect(screen.getByRole('button', { name: 'User menu' })).toBeInTheDocument();
  });

  it('shows user dropdown when user menu button is clicked', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    fireEvent.click(screen.getByRole('button', { name: 'User menu' }));

    expect(screen.getByText('My Profile')).toBeInTheDocument();
    expect(screen.getByText('Sign out')).toBeInTheDocument();
  });

  it('shows user email in dropdown', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    fireEvent.click(screen.getByRole('button', { name: 'User menu' }));

    expect(screen.getByText('parzival@oasis-gunters.com')).toBeInTheDocument();
  });

  it('calls logout when Sign out is clicked', () => {
    const authMock = createAuthMock('tenant-admin');
    mockUseAuth.mockReturnValue(authMock);

    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    fireEvent.click(screen.getByRole('button', { name: 'User menu' }));
    fireEvent.click(screen.getByText('Sign out'));

    expect(authMock.logout).toHaveBeenCalledTimes(1);
  });

  it('renders console link', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    expect(screen.getByText('Console')).toBeInTheDocument();
  });

  it('renders theme toggle', () => {
    renderWithProviders(<Header onMenuClick={mockOnMenuClick} />);

    expect(screen.getByTestId('theme-toggle')).toBeInTheDocument();
  });
});
