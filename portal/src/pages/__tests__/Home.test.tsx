/**
 * Tests for Home page (CAB-1323 Phase 2)
 *
 * Verifies dashboard widget rendering and RBAC-based PermissionGate gating.
 * All 4 standard roles have the scopes required by the current widget gates,
 * so all see all widgets. The PermissionGate is future-proofing for roles
 * with restricted scope sets.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { HomePage } from '../Home';
import {
  renderWithProviders,
  createAuthMock,
  mockDashboardStats,
  mockDashboardActivity,
  type PersonaRole,
} from '../../test/helpers';

// Mock AuthContext
const mockUseAuth = vi.fn();
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

// Mock dashboard hooks
const mockUseDashboardStats = vi.fn();
const mockUseDashboardActivity = vi.fn();
vi.mock('../../hooks/useDashboard', () => ({
  useDashboardStats: () => mockUseDashboardStats(),
  useDashboardActivity: () => mockUseDashboardActivity(),
}));

// Mock i18n
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('../../i18n', () => ({
  loadNamespace: vi.fn(),
  LANGUAGE_KEY: 'stoa:language',
}));

vi.mock('../../config', () => ({
  config: {
    api: { baseUrl: 'https://api.gostoa.dev', timeout: 30000 },
    mcp: { baseUrl: 'https://mcp.gostoa.dev', timeout: 30000 },
    grafana: { url: 'https://grafana.gostoa.dev/d/portal' },
    features: {
      enableMCPTools: true,
      enableSubscriptions: true,
      enableAPICatalog: true,
      enableI18n: false,
    },
    portalMode: 'production',
  },
}));

// Mock child components as stubs for isolation
vi.mock('../../components/dashboard', () => ({
  WelcomeHeader: ({ user }: { user: unknown }) => (
    <div data-testid="welcome-header">Welcome{user ? '' : ' Guest'}</div>
  ),
  DashboardStats: () => <div data-testid="dashboard-stats">Stats</div>,
  QuickActions: () => <div data-testid="quick-actions">Quick Actions</div>,
  RecentActivity: () => <div data-testid="recent-activity">Recent Activity</div>,
  FeaturedAPIs: () => <div data-testid="featured-apis">Featured APIs</div>,
  FeaturedAITools: () => <div data-testid="featured-ai-tools">Featured AI Tools</div>,
}));

vi.mock('../../components/usage/GrafanaDashboard', () => ({
  GrafanaDashboard: ({ url, title }: { url: string; title: string }) => (
    <div data-testid="grafana-dashboard">{url ? `Grafana: ${title}` : 'No URL'}</div>
  ),
}));

vi.mock('../../components/layout/TenantBadge', () => ({
  TenantBadge: () => <div data-testid="tenant-badge">Tenant Badge</div>,
}));

describe('HomePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue(createAuthMock('cpi-admin'));
    mockUseDashboardStats.mockReturnValue({
      data: mockDashboardStats(),
      isLoading: false,
    });
    mockUseDashboardActivity.mockReturnValue({
      data: mockDashboardActivity(),
      isLoading: false,
    });
  });

  describe('Page Structure', () => {
    it('should render welcome header', () => {
      renderWithProviders(<HomePage />);
      expect(screen.getByTestId('welcome-header')).toBeInTheDocument();
    });

    it('should render tenant badge', () => {
      renderWithProviders(<HomePage />);
      expect(screen.getByTestId('tenant-badge')).toBeInTheDocument();
    });

    it('should render dashboard stats', () => {
      renderWithProviders(<HomePage />);
      expect(screen.getByTestId('dashboard-stats')).toBeInTheDocument();
    });

    it('should render quick actions', () => {
      renderWithProviders(<HomePage />);
      expect(screen.getByTestId('quick-actions')).toBeInTheDocument();
    });

    it('should render featured APIs', () => {
      renderWithProviders(<HomePage />);
      expect(screen.getByTestId('featured-apis')).toBeInTheDocument();
    });

    it('should render featured AI tools', () => {
      renderWithProviders(<HomePage />);
      expect(screen.getByTestId('featured-ai-tools')).toBeInTheDocument();
    });

    it('should render recent activity', () => {
      renderWithProviders(<HomePage />);
      expect(screen.getByTestId('recent-activity')).toBeInTheDocument();
    });

    it('should render grafana dashboard', () => {
      renderWithProviders(<HomePage />);
      expect(screen.getByTestId('grafana-dashboard')).toBeInTheDocument();
      expect(screen.getByText('Grafana: Usage Analytics')).toBeInTheDocument();
    });
  });

  describe('Persona-based rendering', () => {
    const roles: PersonaRole[] = ['cpi-admin', 'tenant-admin', 'devops', 'viewer'];

    it.each(roles)('should render all widgets for %s (all have required scopes)', (role) => {
      mockUseAuth.mockReturnValue(createAuthMock(role));
      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('welcome-header')).toBeInTheDocument();
      expect(screen.getByTestId('tenant-badge')).toBeInTheDocument();
      expect(screen.getByTestId('dashboard-stats')).toBeInTheDocument();
      expect(screen.getByTestId('quick-actions')).toBeInTheDocument();
      expect(screen.getByTestId('featured-apis')).toBeInTheDocument();
      expect(screen.getByTestId('featured-ai-tools')).toBeInTheDocument();
      expect(screen.getByTestId('recent-activity')).toBeInTheDocument();
      expect(screen.getByTestId('grafana-dashboard')).toBeInTheDocument();
    });
  });

  describe('PermissionGate scoping', () => {
    it('should hide FeaturedAPIs when user lacks stoa:catalog:read', () => {
      const restrictedAuth = createAuthMock('viewer');
      restrictedAuth.hasScope = (scope: string) => scope !== 'stoa:catalog:read';
      mockUseAuth.mockReturnValue(restrictedAuth);

      renderWithProviders(<HomePage />);

      expect(screen.queryByTestId('featured-apis')).not.toBeInTheDocument();
      // Other widgets still visible
      expect(screen.getByTestId('welcome-header')).toBeInTheDocument();
      expect(screen.getByTestId('featured-ai-tools')).toBeInTheDocument();
    });

    it('should hide FeaturedAITools when user lacks stoa:tools:read', () => {
      const restrictedAuth = createAuthMock('viewer');
      restrictedAuth.hasScope = (scope: string) => scope !== 'stoa:tools:read';
      mockUseAuth.mockReturnValue(restrictedAuth);

      renderWithProviders(<HomePage />);

      expect(screen.queryByTestId('featured-ai-tools')).not.toBeInTheDocument();
      expect(screen.getByTestId('featured-apis')).toBeInTheDocument();
    });

    it('should hide RecentActivity when user lacks stoa:subscriptions:read', () => {
      const restrictedAuth = createAuthMock('viewer');
      restrictedAuth.hasScope = (scope: string) => scope !== 'stoa:subscriptions:read';
      mockUseAuth.mockReturnValue(restrictedAuth);

      renderWithProviders(<HomePage />);

      expect(screen.queryByTestId('recent-activity')).not.toBeInTheDocument();
      expect(screen.getByTestId('welcome-header')).toBeInTheDocument();
      expect(screen.getByTestId('dashboard-stats')).toBeInTheDocument();
    });

    it('should hide GrafanaDashboard when user lacks stoa:metrics:read', () => {
      const restrictedAuth = createAuthMock('viewer');
      restrictedAuth.hasScope = (scope: string) => scope !== 'stoa:metrics:read';
      mockUseAuth.mockReturnValue(restrictedAuth);

      renderWithProviders(<HomePage />);

      expect(screen.queryByTestId('grafana-dashboard')).not.toBeInTheDocument();
      expect(screen.getByTestId('welcome-header')).toBeInTheDocument();
    });

    it('should always show WelcomeHeader, DashboardStats, TenantBadge (no gate)', () => {
      // Remove all scopes
      const noScopeAuth = createAuthMock('viewer');
      noScopeAuth.hasScope = () => false;
      mockUseAuth.mockReturnValue(noScopeAuth);

      renderWithProviders(<HomePage />);

      expect(screen.getByTestId('welcome-header')).toBeInTheDocument();
      expect(screen.getByTestId('tenant-badge')).toBeInTheDocument();
      expect(screen.getByTestId('dashboard-stats')).toBeInTheDocument();
      expect(screen.getByTestId('quick-actions')).toBeInTheDocument();
      // Gated widgets hidden
      expect(screen.queryByTestId('featured-apis')).not.toBeInTheDocument();
      expect(screen.queryByTestId('featured-ai-tools')).not.toBeInTheDocument();
      expect(screen.queryByTestId('recent-activity')).not.toBeInTheDocument();
      expect(screen.queryByTestId('grafana-dashboard')).not.toBeInTheDocument();
    });
  });
});
