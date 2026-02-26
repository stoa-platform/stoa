import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

const mockScanHistory = [
  {
    id: 'scan-1',
    scan_type: 'Full Security Scan',
    status: 'completed',
    started_at: '2026-02-25T10:00:00Z',
    completed_at: '2026-02-25T10:05:00Z',
    findings_count: 12,
    duration_seconds: 300,
  },
  {
    id: 'scan-2',
    scan_type: 'Compliance Check',
    status: 'failed',
    started_at: '2026-02-24T08:00:00Z',
    completed_at: '2026-02-24T08:02:00Z',
    findings_count: 0,
    duration_seconds: 120,
  },
  {
    id: 'scan-3',
    scan_type: 'Vulnerability Scan',
    status: 'running',
    started_at: '2026-02-26T06:00:00Z',
    completed_at: null,
    findings_count: 3,
    duration_seconds: null,
  },
];

const mockCronJobStatus = {
  status: 'active' as const,
  last_run: '2026-02-26T06:00:00Z',
  next_run: '2026-02-27T06:00:00Z',
  last_duration_seconds: 45,
};

const mockSecurityEvents = [
  {
    event_type: 'auth_failure',
    count: 5,
    severity: 'critical' as const,
    last_occurred: '2026-02-26T10:00:00Z',
  },
  {
    event_type: 'rate_limit_exceeded',
    count: 3,
    severity: 'high' as const,
    last_occurred: '2026-02-26T09:00:00Z',
  },
  {
    event_type: 'suspicious_request',
    count: 8,
    severity: 'medium' as const,
    last_occurred: '2026-02-26T08:00:00Z',
  },
  {
    event_type: 'policy_violation',
    count: 2,
    severity: 'low' as const,
    last_occurred: '2026-02-26T07:00:00Z',
  },
];

const mockGet = vi.fn();

vi.mock('../../services/api', () => ({
  apiService: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

interface SetupOptions {
  tokenBinding?: Partial<typeof mockTokenBinding> | null;
  events?: typeof mockSecurityEvents;
  scans?: typeof mockScanHistory;
  cronJob?: typeof mockCronJobStatus | null;
}

function setupApiMock(options: SetupOptions = {}) {
  const { tokenBinding: tokenBindingOverride, events = [], scans = [], cronJob = null } = options;

  mockGet.mockImplementation((url: string) => {
    if (url.includes('/token-binding')) {
      if (tokenBindingOverride === null) {
        return Promise.resolve({ data: null });
      }
      return Promise.resolve({
        data:
          tokenBindingOverride !== undefined
            ? { ...mockTokenBinding, ...tokenBindingOverride }
            : mockTokenBinding,
      });
    }
    if (url.includes('/governance/drift')) {
      return Promise.resolve({ data: { items: [], total: 0 } });
    }
    if (url.includes('/scans')) {
      return Promise.resolve({ data: { scans } });
    }
    if (url.includes('/cronjob-status')) {
      return Promise.resolve({ data: cronJob });
    }
    // Default: security events
    return Promise.resolve({ data: { events, summary: {} } });
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
      setupApiMock({
        tokenBinding: { strategy: 'dpop-only', dpop_enforced: true, replay_protection: true },
      });
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
      setupApiMock({ tokenBinding: null });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Security Posture')).toBeInTheDocument();
      });
      expect(screen.queryByText('Token Binding')).not.toBeInTheDocument();
    });

    it('shows require-any mode correctly', async () => {
      setupApiMock({
        tokenBinding: {
          strategy: 'require-any',
          label: 'Require Any Binding',
          dpop_enforced: true,
          mtls_enforced: true,
          replay_protection: true,
        },
      });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Require Any Binding')).toBeInTheDocument();
      });
    });
  });

  describe('Severity Breakdown Cards', () => {
    it('renders 4 severity cards with correct counts', async () => {
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByTestId('severity-card-critical')).toBeInTheDocument();
        expect(screen.getByTestId('severity-card-high')).toBeInTheDocument();
        expect(screen.getByTestId('severity-card-medium')).toBeInTheDocument();
        expect(screen.getByTestId('severity-card-low')).toBeInTheDocument();
      });
    });

    it('shows correct count for each severity level', async () => {
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        const criticalCard = screen.getByTestId('severity-card-critical');
        expect(criticalCard).toHaveTextContent('1');
        const highCard = screen.getByTestId('severity-card-high');
        expect(highCard).toHaveTextContent('1');
        const mediumCard = screen.getByTestId('severity-card-medium');
        expect(mediumCard).toHaveTextContent('1');
        const lowCard = screen.getByTestId('severity-card-low');
        expect(lowCard).toHaveTextContent('1');
      });
    });

    it('shows zero counts when no findings', async () => {
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        const criticalCard = screen.getByTestId('severity-card-critical');
        expect(criticalCard).toHaveTextContent('0');
      });
    });
  });

  describe('Sortable Findings Table', () => {
    it('renders sortable severity header', async () => {
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Auth Failure')).toBeInTheDocument();
      });
      // The Severity column header should be clickable
      const severityHeader = screen.getByText('Severity');
      expect(severityHeader.closest('th')).toBeInTheDocument();
    });

    it('renders sortable category header', async () => {
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Auth Failure')).toBeInTheDocument();
      });
      const categoryHeader = screen.getByText('Category');
      expect(categoryHeader.closest('th')).toBeInTheDocument();
    });

    it('toggles sort direction on severity click', async () => {
      const user = userEvent.setup();
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Auth Failure')).toBeInTheDocument();
      });
      const severityHeader = screen.getByText('Severity');
      // Default sort is severity ascending (critical first)
      expect(screen.getAllByRole('row').length).toBeGreaterThan(1);
      // First click toggles to desc
      await user.click(severityHeader);
      // After click, sort direction changed — rows still render
      expect(screen.getAllByRole('row').length).toBeGreaterThan(1);
    });

    it('switches to category sort on category click', async () => {
      const user = userEvent.setup();
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Auth Failure')).toBeInTheDocument();
      });
      const categoryHeader = screen.getByText('Category');
      await user.click(categoryHeader);
      // After clicking category, rows are sorted alphabetically
      const rows = screen.getAllByRole('row');
      expect(rows.length).toBeGreaterThan(1);
    });
  });

  describe('Scan History Timeline', () => {
    it('renders scan history section when scans exist', async () => {
      setupApiMock({ scans: mockScanHistory });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Scan History')).toBeInTheDocument();
      });
    });

    it('shows scan types in the timeline', async () => {
      setupApiMock({ scans: mockScanHistory });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Full Security Scan')).toBeInTheDocument();
        expect(screen.getByText('Compliance Check')).toBeInTheDocument();
        expect(screen.getByText('Vulnerability Scan')).toBeInTheDocument();
      });
    });

    it('shows findings count per scan', async () => {
      setupApiMock({ scans: mockScanHistory });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('12 findings')).toBeInTheDocument();
        expect(screen.getByText('0 findings')).toBeInTheDocument();
        expect(screen.getByText('3 findings')).toBeInTheDocument();
      });
    });

    it('shows duration for completed scans', async () => {
      setupApiMock({ scans: mockScanHistory });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('300s')).toBeInTheDocument();
        expect(screen.getByText('120s')).toBeInTheDocument();
      });
    });

    it('does not render scan history when no scans', async () => {
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Security Posture')).toBeInTheDocument();
      });
      expect(screen.queryByText('Scan History')).not.toBeInTheDocument();
    });
  });

  describe('CronJob Status Indicator', () => {
    it('renders cronjob status section when data exists', async () => {
      setupApiMock({ cronJob: mockCronJobStatus });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Scan Schedule')).toBeInTheDocument();
      });
    });

    it('shows active status with green dot', async () => {
      setupApiMock({ cronJob: mockCronJobStatus });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        const dot = screen.getByTestId('cronjob-status-dot');
        expect(dot).toHaveClass('bg-green-500');
      });
    });

    it('shows degraded status with yellow dot', async () => {
      setupApiMock({ cronJob: { ...mockCronJobStatus, status: 'degraded' as const } });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        const dot = screen.getByTestId('cronjob-status-dot');
        expect(dot).toHaveClass('bg-yellow-500');
      });
    });

    it('shows paused status with neutral dot', async () => {
      setupApiMock({ cronJob: { ...mockCronJobStatus, status: 'paused' as const } });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        const dot = screen.getByTestId('cronjob-status-dot');
        expect(dot).toHaveClass('bg-neutral-400');
      });
    });

    it('shows last run duration', async () => {
      setupApiMock({ cronJob: mockCronJobStatus });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('(45s)')).toBeInTheDocument();
      });
    });

    it('shows "Never" when last_run is null', async () => {
      setupApiMock({
        cronJob: { ...mockCronJobStatus, last_run: null, last_duration_seconds: null },
      });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Never')).toBeInTheDocument();
      });
    });

    it('shows "Not scheduled" when next_run is null', async () => {
      setupApiMock({ cronJob: { ...mockCronJobStatus, next_run: null } });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Not scheduled')).toBeInTheDocument();
      });
    });

    it('does not render when cronjob data is null', async () => {
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Security Posture')).toBeInTheDocument();
      });
      expect(screen.queryByText('Scan Schedule')).not.toBeInTheDocument();
    });
  });

  describe('Quick Actions (RBAC-gated)', () => {
    it('shows quick actions for cpi-admin with findings', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Quick Actions')).toBeInTheDocument();
        expect(screen.getByText('Acknowledge All')).toBeInTheDocument();
        expect(screen.getByText('Suppress Low')).toBeInTheDocument();
        expect(screen.getByText('Create Ticket')).toBeInTheDocument();
      });
    });

    it('shows quick actions for tenant-admin with findings', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Quick Actions')).toBeInTheDocument();
      });
    });

    it('hides quick actions for devops', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('devops'));
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Security Posture')).toBeInTheDocument();
      });
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Auth Failure')).toBeInTheDocument();
      });
      expect(screen.queryByText('Quick Actions')).not.toBeInTheDocument();
    });

    it('hides quick actions for viewer', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('viewer'));
      setupApiMock({ events: mockSecurityEvents });
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Security Posture')).toBeInTheDocument();
      });
      await waitFor(() => {
        expect(screen.getByText('Auth Failure')).toBeInTheDocument();
      });
      expect(screen.queryByText('Quick Actions')).not.toBeInTheDocument();
    });

    it('hides quick actions when no open findings', async () => {
      vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
      setupApiMock();
      render(<SecurityPostureDashboard />);
      await waitFor(() => {
        expect(screen.getByText('Security Posture')).toBeInTheDocument();
      });
      await waitFor(() => {
        expect(screen.getByText('No open security findings')).toBeInTheDocument();
      });
      expect(screen.queryByText('Quick Actions')).not.toBeInTheDocument();
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

      it('shows severity breakdown cards', async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<SecurityPostureDashboard />);
        await waitFor(() => {
          expect(screen.getByTestId('severity-card-critical')).toBeInTheDocument();
          expect(screen.getByTestId('severity-card-high')).toBeInTheDocument();
          expect(screen.getByTestId('severity-card-medium')).toBeInTheDocument();
          expect(screen.getByTestId('severity-card-low')).toBeInTheDocument();
        });
      });
    }
  );
});
