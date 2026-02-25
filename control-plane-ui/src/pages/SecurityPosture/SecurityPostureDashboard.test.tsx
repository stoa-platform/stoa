import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SecurityPostureDashboard } from './SecurityPostureDashboard';
import { createAuthMock } from '../../test/helpers';
import { useAuth } from '../../contexts/AuthContext';
import type { PersonaRole } from '../../test/helpers';

vi.mock('../../contexts/AuthContext', () => ({ useAuth: vi.fn() }));

vi.mock('../../services/api', () => ({
  apiService: {
    get: vi.fn(() =>
      Promise.resolve({
        data: { events: [], summary: {} },
      })
    ),
  },
}));

describe('SecurityPostureDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
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

  it('shows compliance checks', async () => {
    render(<SecurityPostureDashboard />);
    await waitFor(() => {
      expect(screen.getByText('Compliance Checks')).toBeInTheDocument();
      expect(screen.getByText('mTLS enforcement')).toBeInTheDocument();
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

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    '%s persona',
    (role) => {
      it('renders the page', () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        render(<SecurityPostureDashboard />);
        expect(screen.getByText('Security Posture')).toBeInTheDocument();
      });
    }
  );
});
