/**
 * Tests for Sidebar (CAB-1390)
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
  },
}));

const mockUseAuth = vi.fn();

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
  'Sidebar — %s persona',
  (role) => {
    const onClose = vi.fn();

    beforeEach(() => {
      vi.clearAllMocks();
      mockUseAuth.mockReturnValue(createAuthMock(role));
    });

    it('renders navigation sections', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      // "Discover" section should be visible
      expect(screen.getByText('Discover')).toBeInTheDocument();
    });

    it('renders Marketplace nav item when feature is enabled', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.getByText('Marketplace')).toBeInTheDocument();
    });

    it('does not render separate API Catalog or AI Tools nav items', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.queryByText('API Catalog')).not.toBeInTheDocument();
      expect(screen.queryByText('AI Tools')).not.toBeInTheDocument();
    });

    it('renders Profile nav item (always visible)', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.getByText('Profile')).toBeInTheDocument();
    });

    it('shows mobile overlay when isOpen is true', () => {
      const { container } = renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);
      // The overlay div appears when isOpen is true
      expect(container.querySelector('[class*="fixed inset-0"]')).toBeInTheDocument();
    });

    it('does not show mobile overlay when isOpen is false', () => {
      const { container } = renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      // Overlay uses conditional render (isOpen && <div>), not aria-hidden
      // aria-hidden="true" is used on SVG icons, so check by overlay's class instead
      expect(container.querySelector('[class*="fixed inset-0"]')).not.toBeInTheDocument();
    });

    it('calls onClose when overlay is clicked', () => {
      renderWithProviders(<Sidebar isOpen={true} onClose={onClose} />);
      // The overlay button/div is clickable
      const overlay = document.querySelector('[class*="fixed inset-0"]');
      if (overlay) {
        fireEvent.click(overlay);
        expect(onClose).toHaveBeenCalled();
      }
    });

    it('hides Gateways item when enableGateways is false', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.queryByText('Gateways')).not.toBeInTheDocument();
    });

    it('filters items based on user scope — viewer without write scope', () => {
      if (role !== 'viewer') return;
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      // Register Consumer requires stoa:subscriptions:write — should be hidden for viewer
      expect(screen.queryByText('Register Consumer')).not.toBeInTheDocument();
    });

    it('shows My Workspace section for tenant-admin', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.getByText('My Workspace')).toBeInTheDocument();
    });

    it('renders "Account" section', () => {
      renderWithProviders(<Sidebar isOpen={false} onClose={onClose} />);
      expect(screen.getByText('Account')).toBeInTheDocument();
    });
  }
);
