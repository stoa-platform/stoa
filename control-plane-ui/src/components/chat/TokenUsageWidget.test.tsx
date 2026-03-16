import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { TokenUsageWidget } from '@stoa/shared/components/chat/TokenUsageWidget';
import { renderWithProviders, type PersonaRole } from '../../test/helpers';
import type { TokenBudgetStatus } from '@stoa/shared/hooks/useChatService';

const mockBudget: TokenBudgetStatus = {
  user_tokens_today: 1500,
  tenant_tokens_today: 8000,
  daily_budget: 10000,
  remaining: 8500,
  budget_exceeded: false,
  usage_percent: 15,
};

// Locale-agnostic regex: matches any digit-group separator (comma, space, NBSP, period)
const sep = '[\\s\\u00a0,.]?';

const mockGetBudgetStatus = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockGetBudgetStatus.mockResolvedValue(mockBudget);
});

describe('TokenUsageWidget', () => {
  it('renders loading skeleton while fetching', () => {
    mockGetBudgetStatus.mockReturnValue(new Promise(() => {}));
    renderWithProviders(
      <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(screen.getByTestId('token-usage-loading')).toBeInTheDocument();
  });

  it('renders budget usage when data is loaded', async () => {
    renderWithProviders(
      <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(await screen.findByTestId('token-usage-widget')).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`1${sep}500`))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`10${sep}000`))).toBeInTheDocument();
  });

  it('shows green indicator when usage < 60%', async () => {
    renderWithProviders(
      <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(await screen.findByText('15%')).toBeInTheDocument();
    const ring = screen.getByTestId('progress-ring');
    expect(ring.getAttribute('stroke')).toBe('#10b981');
  });

  it('shows amber indicator when usage 60-80%', async () => {
    mockGetBudgetStatus.mockResolvedValue({
      ...mockBudget,
      usage_percent: 70,
      remaining: 3000,
    });
    renderWithProviders(
      <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(await screen.findByText('70%')).toBeInTheDocument();
    const ring = screen.getByTestId('progress-ring');
    expect(ring.getAttribute('stroke')).toBe('#f59e0b');
  });

  it('shows red indicator and warning when budget exceeded', async () => {
    mockGetBudgetStatus.mockResolvedValue({
      ...mockBudget,
      usage_percent: 100,
      remaining: 0,
      budget_exceeded: true,
    });
    renderWithProviders(
      <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(await screen.findByTestId('budget-exceeded-warning')).toBeInTheDocument();
    const ring = screen.getByTestId('progress-ring');
    expect(ring.getAttribute('stroke')).toBe('#ef4444');
  });

  it('returns null when tenantId is undefined', () => {
    const { container } = renderWithProviders(
      <TokenUsageWidget tenantId={undefined} getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('shows error state on API failure', async () => {
    mockGetBudgetStatus.mockRejectedValue(new Error('Network error'));
    renderWithProviders(
      <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(await screen.findByTestId('token-usage-error')).toBeInTheDocument();
  });

  it('formats large token numbers with locale separators', async () => {
    mockGetBudgetStatus.mockResolvedValue({
      ...mockBudget,
      user_tokens_today: 123456,
      daily_budget: 1000000,
      remaining: 876544,
    });
    renderWithProviders(
      <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(await screen.findByText(new RegExp(`123${sep}456`))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`1${sep}000${sep}000`))).toBeInTheDocument();
  });

  it('displays correct percentage', async () => {
    mockGetBudgetStatus.mockResolvedValue({
      ...mockBudget,
      usage_percent: 42.7,
    });
    renderWithProviders(
      <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(await screen.findByText('43%')).toBeInTheDocument();
  });

  it('caps display at 100% even if API returns higher', async () => {
    mockGetBudgetStatus.mockResolvedValue({
      ...mockBudget,
      usage_percent: 120,
      budget_exceeded: true,
    });
    renderWithProviders(
      <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
    );
    expect(await screen.findByText('100%')).toBeInTheDocument();
  });

  describe.each<PersonaRole>(['cpi-admin', 'tenant-admin', 'devops', 'viewer'])(
    'persona: %s',
    (_role) => {
      it(`renders widget for ${_role}`, async () => {
        renderWithProviders(
          <TokenUsageWidget tenantId="test-tenant" getBudgetStatus={mockGetBudgetStatus} />
        );
        expect(await screen.findByTestId('token-usage-widget')).toBeInTheDocument();
      });
    }
  );
});
