/**
 * Tests for Sidebar (CAB-1390, CAB-1764)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { Sidebar } from './Sidebar';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../test/helpers';

vi.mock('../../config', () => ({
  config: {
    features: {
      enableMarketplace: true,
      enableSubscriptions: true,
      enableGateways: false,
    },
    services: { console: { url: 'https://console.example.com' } },
    app: { version: '1.0.0' },
    baseDomain: 'example.com',
  },
}));

const mockUseAuth = vi.fn();

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../../contexts/EnvironmentContext', () => ({
  usePortalEnvironment: () => ({
    activeEnvironment: 'dev',
    activeConfig: { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
    environments: [
      { name: 'dev', label: 'Development', mode: 'full', color: 'green' },
      { name: 'staging', label: 'Staging', mode: 'full', color: 'amber' },
    ],
    endpoints: null,
    switchEnvironment: vi.fn(),
    loading: false,
    error: null,
  }),
}));

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'Sidebar — %s persona',
  (role) => {
    const onClose = vi.fn();

    beforeEach(() => {
      vi.clearAllMocks();
      mockUseAuth.mockReturnValue(createAuthMock(role));
    });

    it('renders flat navigation items', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.getByText('Marketplace')).toBeInTheDocument();
      expect(screen.getByText('Profile')).toBeInTheDocument();
    });

    it('renders My Workspace nav item', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.getByText('My Workspace')).toBeInTheDocument();
    });

    it('renders Analytics nav item when subscriptions enabled', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.getByText('Analytics')).toBeInTheDocument();
    });

    it('does not render removed nav items', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.queryByText('Compare APIs')).not.toBeInTheDocument();
      expect(screen.queryByText('Favorites')).not.toBeInTheDocument();
      expect(screen.queryByText('Notifications')).not.toBeInTheDocument();
      expect(screen.queryByText('Audit Log')).not.toBeInTheDocument();
      expect(screen.queryByText('Rate Limits')).not.toBeInTheDocument();
    });

    it('renders Console as external link', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.getByText('Console')).toBeInTheDocument();
    });

    it('shows mobile overlay when isOpen is true', () => {
      const { container } = renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);
      expect(container.querySelector('[class*="fixed inset-0"]')).toBeInTheDocument();
    });

    it('does not show mobile overlay when isOpen is false', () => {
      const { container } = renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(container.querySelector('[class*="fixed inset-0"]')).not.toBeInTheDocument();
    });

    it('calls onClose when overlay is clicked', () => {
      renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);
      const overlay = document.querySelector('[class*="fixed inset-0"]');
      if (overlay) {
        fireEvent.click(overlay);
        expect(onClose).toHaveBeenCalled();
      }
    });

    it('does not render section headers (flat navigation)', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.queryByText('Discover')).not.toBeInTheDocument();
      expect(screen.queryByText('Account')).not.toBeInTheDocument();
      expect(screen.queryByText('Operations')).not.toBeInTheDocument();
    });
  }
);
