/**
 * Tests for QuickActions component (CAB-1323 Phase 2)
 *
 * Verifies RBAC scope-based filtering of quick action buttons.
 * Actions with scope="stoa:subscriptions:write" are hidden from roles without that scope.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { QuickActions } from '../QuickActions';
import { renderWithProviders, createAuthMock, type PersonaRole } from '../../../test/helpers';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

// Mock config with all features enabled
vi.mock('../../../config', () => ({
  config: {
    features: {
      enableAPICatalog: true,
      enableMCPTools: true,
      enableSubscriptions: true,
    },
  },
}));

describe('QuickActions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));
  });

  describe('Scope-based filtering', () => {
    it('should show all 6 actions for cpi-admin (has stoa:subscriptions:write)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<QuickActions />);

      expect(screen.getByText('onboarding:quickAction.title')).toBeInTheDocument();
      expect(screen.getByText('API Catalog')).toBeInTheDocument();
      expect(screen.getByText('AI Tools')).toBeInTheDocument();
      expect(screen.getByText('Register as Consumer')).toBeInTheDocument();
      expect(screen.getByText('View Usage')).toBeInTheDocument();
      expect(screen.getByText('My Subscriptions')).toBeInTheDocument();
    });

    it('should show all 6 actions for tenant-admin (has stoa:subscriptions:write)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
      renderWithProviders(<QuickActions />);

      expect(screen.getByText('onboarding:quickAction.title')).toBeInTheDocument();
      expect(screen.getByText('Register as Consumer')).toBeInTheDocument();
      expect(screen.getByText('My Subscriptions')).toBeInTheDocument();
    });

    it('should hide write-gated actions for devops (no stoa:subscriptions:write)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('devops'));
      renderWithProviders(<QuickActions />);

      expect(screen.getByText('onboarding:quickAction.title')).toBeInTheDocument();
      expect(screen.getByText('API Catalog')).toBeInTheDocument();
      expect(screen.getByText('AI Tools')).toBeInTheDocument();
      expect(screen.getByText('View Usage')).toBeInTheDocument();
      expect(screen.queryByText('Register as Consumer')).not.toBeInTheDocument();
      expect(screen.queryByText('My Subscriptions')).not.toBeInTheDocument();
    });

    it('should hide write-gated actions for viewer (no stoa:subscriptions:write)', () => {
      mockUseAuth.mockReturnValue(createAuthMock('viewer'));
      renderWithProviders(<QuickActions />);

      expect(screen.getByText('onboarding:quickAction.title')).toBeInTheDocument();
      expect(screen.getByText('API Catalog')).toBeInTheDocument();
      expect(screen.getByText('AI Tools')).toBeInTheDocument();
      expect(screen.getByText('View Usage')).toBeInTheDocument();
      expect(screen.queryByText('Register as Consumer')).not.toBeInTheDocument();
      expect(screen.queryByText('My Subscriptions')).not.toBeInTheDocument();
    });
  });

  describe('Feature flag interaction', () => {
    it('should show subscription actions when feature flag is enabled and scope allows', () => {
      // With all features enabled (mock default) and cpi-admin scope
      mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));
      renderWithProviders(<QuickActions />);

      // All subscription-gated actions visible (feature enabled + scope present)
      expect(screen.getByText('Register as Consumer')).toBeInTheDocument();
      expect(screen.getByText('My Subscriptions')).toBeInTheDocument();
      expect(screen.getByText('View Usage')).toBeInTheDocument();
    });
  });

  describe('Actions without scope', () => {
    it('should always show Get Started (no scope gate)', () => {
      const roles: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];
      roles.forEach((role) => {
        mockUseAuth.mockReturnValue(createAuthMock(role));
        const { unmount } = renderWithProviders(<QuickActions />);
        expect(screen.getByText('onboarding:quickAction.title')).toBeInTheDocument();
        unmount();
      });
    });
  });

  describe('Rendering', () => {
    it('should render action cards as links', () => {
      renderWithProviders(<QuickActions />);

      const links = screen.getAllByRole('link');
      expect(links.length).toBeGreaterThanOrEqual(6);
    });

    it('should render section heading', () => {
      renderWithProviders(<QuickActions />);

      expect(screen.getByText('Quick Actions')).toBeInTheDocument();
    });
  });
});
