import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { TokenUsageWidget } from './TokenUsageWidget';
import { createAuthMock, renderWithProviders, type PersonaRole } from '../../test/helpers';
import type { TokenBudgetStatus } from '../../services/api';

// Mock AuthContext
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

// Mock apiService
vi.mock('../../services/api', () => ({
  apiService: {
    getChatBudgetStatus: vi.fn(),
  },
}));

import { useAuth } from '../../contexts/AuthContext';
import { apiService } from '../../services/api';

const mockBudget: TokenBudgetStatus = {
  user_tokens_today: 1500,
  tenant_tokens_today: 8000,
  daily_budget: 10000,
  remaining: 8500,
  budget_exceeded: false,
  usage_percent: 15,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
  vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue(mockBudget);
});

describe('TokenUsageWidget', () => {
  it('renders loading skeleton while fetching', () => {
    vi.mocked(apiService.getChatBudgetStatus).mockReturnValue(new Promise(() => {}));
    renderWithProviders(<TokenUsageWidget />);
    expect(screen.getByTestId('token-usage-loading')).toBeInTheDocument();
  });

  it('renders budget usage when data is loaded', async () => {
    renderWithProviders(<TokenUsageWidget />);
    expect(await screen.findByTestId('token-usage-widget')).toBeInTheDocument();
    expect(screen.getByText(/1,500/)).toBeInTheDocument();
    expect(screen.getByText(/10,000/)).toBeInTheDocument();
  });

  it('shows green indicator when usage < 60%', async () => {
    renderWithProviders(<TokenUsageWidget />);
    expect(await screen.findByText('15%')).toBeInTheDocument();
    const ring = screen.getByTestId('progress-ring');
    expect(ring.getAttribute('stroke')).toBe('#10b981');
  });

  it('shows amber indicator when usage 60-80%', async () => {
    vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue({
      ...mockBudget,
      usage_percent: 70,
      remaining: 3000,
    });
    renderWithProviders(<TokenUsageWidget />);
    expect(await screen.findByText('70%')).toBeInTheDocument();
    const ring = screen.getByTestId('progress-ring');
    expect(ring.getAttribute('stroke')).toBe('#f59e0b');
  });

  it('shows red indicator and warning when budget exceeded', async () => {
    vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue({
      ...mockBudget,
      usage_percent: 100,
      remaining: 0,
      budget_exceeded: true,
    });
    renderWithProviders(<TokenUsageWidget />);
    expect(await screen.findByTestId('budget-exceeded-warning')).toBeInTheDocument();
    const ring = screen.getByTestId('progress-ring');
    expect(ring.getAttribute('stroke')).toBe('#ef4444');
  });

  it('returns null when no tenant is available', () => {
    vi.mocked(useAuth).mockReturnValue({
      ...createAuthMock('cpi-admin'),
      user: { ...createAuthMock('cpi-admin').user, tenant_id: '' },
    });
    const { container } = renderWithProviders(<TokenUsageWidget />);
    expect(container.firstChild).toBeNull();
  });

  it('shows error state on API failure', async () => {
    vi.mocked(apiService.getChatBudgetStatus).mockRejectedValue(new Error('Network error'));
    renderWithProviders(<TokenUsageWidget />);
    expect(await screen.findByTestId('token-usage-error')).toBeInTheDocument();
  });

  it('formats large token numbers with locale separators', async () => {
    vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue({
      ...mockBudget,
      user_tokens_today: 123456,
      daily_budget: 1000000,
      remaining: 876544,
    });
    renderWithProviders(<TokenUsageWidget />);
    expect(await screen.findByText(/123,456/)).toBeInTheDocument();
    expect(screen.getByText(/1,000,000/)).toBeInTheDocument();
  });

  it('displays correct percentage', async () => {
    vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue({
      ...mockBudget,
      usage_percent: 42.7,
    });
    renderWithProviders(<TokenUsageWidget />);
    expect(await screen.findByText('43%')).toBeInTheDocument();
  });

  it('caps display at 100% even if API returns higher', async () => {
    vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue({
      ...mockBudget,
      usage_percent: 120,
      budget_exceeded: true,
    });
    renderWithProviders(<TokenUsageWidget />);
    expect(await screen.findByText('100%')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'persona: %s',
    (role) => {
      it(`renders widget for ${role}`, async () => {
        vi.mocked(useAuth).mockReturnValue(createAuthMock(role));
        renderWithProviders(<TokenUsageWidget />);
        expect(await screen.findByTestId('token-usage-widget')).toBeInTheDocument();
      });
    }
  );
});
