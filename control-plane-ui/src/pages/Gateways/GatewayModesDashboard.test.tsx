import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

// Mock api service
vi.mock('../../services/api', () => ({
  apiService: {
    setAuthToken: vi.fn(),
    clearAuthToken: vi.fn(),
    getGatewayModeStats: vi.fn().mockResolvedValue({
      total_gateways: 13,
      modes: [
        { mode: 'edge-mcp', total: 6, online: 5, offline: 0, degraded: 1 },
        { mode: 'sidecar', total: 3, online: 2, offline: 1, degraded: 0 },
        { mode: 'proxy', total: 1, online: 1, offline: 0, degraded: 0 },
        { mode: 'shadow', total: 0, online: 0, offline: 0, degraded: 0 },
        { mode: 'connect', total: 3, online: 3, offline: 0, degraded: 0 },
      ],
    }),
  },
}));

// Mock shared components
vi.mock('@stoa/shared/components/Skeleton', () => ({
  CardSkeleton: () => <div data-testid="card-skeleton" />,
}));

import { GatewayModesDashboard } from './GatewayModesDashboard';

function renderComponent() {
  return render(<GatewayModesDashboard />);
}

describe('GatewayModesDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  });

  it('renders the heading', async () => {
    renderComponent();
    expect(await screen.findByRole('heading', { name: 'Gateway Modes' })).toBeInTheDocument();
  });

  it('renders the subtitle with ADR reference', async () => {
    renderComponent();
    // ADR-024 appears in both subtitle and architecture section
    await waitFor(() => {
      expect(screen.getAllByText(/ADR-024/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows total gateways count', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('13')).toBeInTheDocument();
    });
    expect(screen.getByText('Total STOA Gateways')).toBeInTheDocument();
  });

  it('shows all five gateway modes', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Edge MCP')).toBeInTheDocument();
    });
    expect(screen.getByText('Sidecar runtime')).toBeInTheDocument();
    expect(screen.getByText('Proxy')).toBeInTheDocument();
    expect(screen.getByText('Shadow')).toBeInTheDocument();
    expect(screen.getByText('Connect')).toBeInTheDocument();
  });

  it('shows mode descriptions', async () => {
    renderComponent();
    // Mode descriptions appear in both mode cards and architecture section
    await waitFor(() => {
      expect(screen.getAllByText(/MCP protocol with SSE transport/).length).toBeGreaterThanOrEqual(
        1
      );
    });
    expect(screen.getAllByText(/Policy enforcement/).length).toBeGreaterThanOrEqual(1);
  });

  it('shows instance counts per mode', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('6')).toBeInTheDocument(); // edge-mcp total
    });
    // sidecar=3 and connect=3 both show '3', so use getAllByText
    expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(2);
  });

  it('shows architecture section', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText(/STOA Gateway Architecture/)).toBeInTheDocument();
    });
  });

  it('shows 5 Deployment Modes label', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('5 Deployment Modes')).toBeInTheDocument();
    });
  });

  it('shows connect mode stats from API', async () => {
    renderComponent();
    await waitFor(() => {
      expect(screen.getByText('Connect')).toBeInTheDocument();
    });
    // Connect has 3 total instances in mock data
    const connectLink = screen.getByText('View Connect gateways →');
    expect(connectLink).toBeInTheDocument();
    expect(connectLink.closest('a')).toHaveAttribute('href', '/gateways?mode=connect');
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderComponent();
        expect(await screen.findByRole('heading', { name: 'Gateway Modes' })).toBeInTheDocument();
      });
    }
  );
});
