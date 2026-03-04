/**
 * Tests for Header (CAB-1390)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { Header } from './Header';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';

vi.mock('../../config', () => ({
  config: {
    services: { console: { url: 'https://console.example.com' } },
    features: { enableI18n: false, enableNotifications: true },
  },
}));

vi.mock('@stoa/shared/components/StoaLogo', () => ({
  StoaLogo: () => <div data-testid="stoa-logo">Logo</div>,
}));

vi.mock('@stoa/shared/components/ThemeToggle', () => ({
  ThemeToggle: () => <button>Theme</button>,
}));

const mockAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuth(),
}));

vi.mock('../../hooks/useNotifications', () => ({
  useUnreadCount: () => ({ data: 0 }),
}));

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'Header — %s persona',
  (role) => {
    const onMenuClick = vi.fn();

    beforeEach(() => {
      vi.clearAllMocks();
      mockAuth.mockReturnValue(createAuthMock(role));
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
      const auth = createAuthMock(role);
      const userName = auth.user?.name ?? '';
      expect(screen.getAllByText(new RegExp(userName, 'i')).length).toBeGreaterThan(0);
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
  }
);
