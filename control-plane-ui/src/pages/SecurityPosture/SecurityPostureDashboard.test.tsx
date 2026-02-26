import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SecurityPostureDashboard } from './SecurityPostureDashboard';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

const mockTokenBinding = {
  strategy: 'auto',
  label: 'Auto (Migration)',
  description: 'Unbound tokens accepted. DPoP and mTLS validated when present.',
  dpop_enforced: false,
  mtls_enforced: false,
  dpop_available: true,
  mtls_available: true,
  replay_protection: false,
};

const mockGet = vi.fn();

vi.mock('../../services/api', () => ({
  apiService: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

function setupApiMock(tokenBindingOverride?: Partial<typeof mockTokenBinding> | null) {
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/token-binding')) {
      if (tokenBindingOverride === null) {
        return Promise.resolve({ data: null });
      }
      return Promise.resolve({ data: { ...mockTokenBinding, ...tokenBindingOverride } });
    }
    if (url.includes('/governance/drift')) {
      return Promise.resolve({ data: { items: [], total: 0 } });
    }
    return Promise.resolve({ data: { events: [], summary: {} } });
  });
}

describe('SecurityPostureDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    setupApiMock();
  });

  it('renders the page title', () => {
    render(<SecurityPostureDashboard />);
    expect(screen.getByText('Security Posture')).toBeInTheDocument();
  });

  it('renders the subtitle', () => {
    render(<SecurityPostureDashboard />);
    expect(
      screen.getByText('Continuous security monitoring and compliance scoring')
    ).toBeInTheDocument();
  });

  it('renders refresh button', () => {
    render(<SecurityPostureDashboard />);
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });

  it('shows KPI stat cards after loading', async () => {
    render(<SecurityPostureDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Open Findings')).toBeInTheDocument();
      expect(screen.getByText('Auth Failures (24h)')).toBeInTheDocument();
      expect(screen.getByText('Config Drift')).toBeInTheDocument();
      expect(screen.getByText('Compliance')).toBeInTheDocument();
    });
  });

  it('shows security score gauge', async () => {
    render(<SecurityPostureDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Security Score')).toBeInTheDocument();
    });
  });

  it('shows compliance checks including DPoP', async () => {
    render(<SecurityPostureDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Compliance Checks')).toBeInTheDocument();
      expect(screen.getByText('mTLS enforcement')).toBeInTheDocument();
      expect(screen.getByText('DPoP token binding')).toBeInTheDocument();
      expect(screen.getByText('Audit logging enabled')).toBeInTheDocument();
    });
  });

  it('shows security findings section', async () => {
    render(<SecurityPostureDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Security Findings')).toBeInTheDocument();
    });
  });

  it('shows empty findings message when no data', async () => {
    render(<SecurityPostureDashboard />);
    await waitFor(() => {
      expect(screen.getByText('No open security findings')).toBeInTheDocument();
    });
  });

  it('renders severity filter', async () => {
    render(<SecurityPostureDashboard />);
    await waitFor(() => {
      expect(screen.getByDisplayValue('All Severities')).toBeInTheDocument();
    });
  });

  describe('Token Binding section', () => {
    it('shows token binding card in auto mode', async () => {
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Token Binding')).toBeInTheDocument();
        expect(screen.getByText('Auto (Migration)')).toBeInTheDocument();
        expect(screen.getByText('DPoP (RFC 9449)')).toBeInTheDocument();
        expect(screen.getByText('mTLS (RFC 8705)')).toBeInTheDocument();
        expect(screen.getByText('Replay Protection')).toBeInTheDocument();
        expect(screen.getByText('Sender Constraint')).toBeInTheDocument();
      });
    });

    it('shows enforced status when DPoP is enforced', async () => {
      setupApiMock({ strategy: 'dpop-only', dpop_enforced: true, replay_protection: true });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        const enforcedItems = screen.getAllByText('Enforced');
        expect(enforcedItems.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows available status for non-enforced methods', async () => {
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        const availableItems = screen.getAllByText('Available');
        expect(availableItems.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('hides token binding when API returns null', async () => {
      setupApiMock(null);
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Security Posture')).toBeInTheDocument();
      });
      expect(screen.queryByText('Token Binding')).not.toBeInTheDocument();
    });

    it('shows require-any mode correctly', async () => {
      setupApiMock({
        strategy: 'require-any',
        label: 'Require Any Binding',
        dpop_enforced: true,
        mtls_enforced: true,
        replay_protection: true,
      });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Require Any Binding')).toBeInTheDocument();
      });
    });
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<SecurityPostureDashboard />);
        expect(screen.getByText('Security Posture')).toBeInTheDocument();
      });

      it('shows token binding section', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<SecurityPostureDashboard />);
        await waitFor(() => {
          expect(screen.getByText('Token Binding')).toBeInTheDocument();
        });
      });
    }
  );
});
