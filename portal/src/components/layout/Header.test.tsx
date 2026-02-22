/**
 * Tests for Header (CAB-1390)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { Header } from './Header';
import { renderWithProviders, createAuthMock } from '../../test/helpers';

vi.mock('../../config', () => ({
  config: {
    services: { console: { url: 'https://console.example.com' } },
    features: { enableI18n: false },
  },
}));

vi.mock('@stoa/shared/components/StoaLogo', () => ({
  StoaLogo: () => <div data-testid="stoa-logo">Logo</div>,
}));

vi.mock('@stoa/shared/components/ThemeToggle', () => ({
  ThemeToggle: () => <button>Theme</button>,
}));

const mockLogout = vi.fn();

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => createAuthMock('tenant-admin'),
}));

describe('Header', () => {
  const onMenuClick = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the header element', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    expect(screen.getByRole('banner')).toBeInTheDocument();
  });

  it('renders the Open menu button', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    expect(screen.getByRole('button', { name: 'Open menu' })).toBeInTheDocument();
  });

  it('calls onMenuClick when the menu button is clicked', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open menu' }));
    expect(onMenuClick).toHaveBeenCalledOnce();
  });

  it('renders the STOA logo', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    expect(screen.getByTestId('stoa-logo')).toBeInTheDocument();
  });

  it('renders user menu button', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    expect(screen.getByRole('button', { name: 'User menu' })).toBeInTheDocument();
  });

  it('opens dropdown menu when user menu button is clicked', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    fireEvent.click(screen.getByRole('button', { name: 'User menu' }));
    expect(screen.getByText('Sign out')).toBeInTheDocument();
    expect(screen.getByText('My Profile')).toBeInTheDocument();
  });

  it('shows user name in dropdown', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    fireEvent.click(screen.getByRole('button', { name: 'User menu' }));
    // createAuthMock('tenant-admin') returns user with name: 'Wade Watts'
    // The dropdown renders {user?.name} in the header section
    expect(screen.getAllByText(/wade watts/i).length).toBeGreaterThan(0);
  });

  it('dropdown is not shown by default', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    expect(screen.queryByText('Sign out')).not.toBeInTheDocument();
  });

  it('renders Console link', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    expect(screen.getByText('Console')).toBeInTheDocument();
  });

  it('renders Notifications button', () => {
    renderWithProviders(<Header onMenuClick={onMenuClick} />);
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument();
  });
});
