import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatUsageDashboard } from './ChatUsageDashboard';
import { createAuthMock } from '../test/helpers';
import { useAuth } from '../contexts/AuthContext';
import { apiService } from '../services/api';

vi.mock('../contexts/AuthContext', () => ({ useAuth: vi.fn() }));
vi.mock('../services/api', () => ({
  apiService: {
    getChatUsageTenant: vi.fn(),
    getChatBudgetStatus: vi.fn(),
  },
}));

const mockUsage = {
  sources: [
    { source: 'console', tokens: 5000, requests: 10 },
    { source: 'portal', tokens: 3000, requests: 6 },
  ],
  total_tokens: 8000,
  total_requests: 16,
  period_days: 1,
};

const mockBudget = {
  daily_budget: 100_000,
  tenant_tokens_today: 8000,
  usage_percent: 8,
  budget_exceeded: false,
};

describe('ChatUsageDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('stoa-active-tenant', 'test-tenant');
    vi.mocked(useAuth).mockReturnValue(createAuthMock('cpi-admin'));
    vi.mocked(apiService.getChatUsageTenant).mockResolvedValue(mockUsage);
    vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue(mockBudget);
  });

  it('renders the page header', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalled());
    expect(screen.getByText('Chat Usage')).toBeInTheDocument();
  });

  it('shows tenant ID in header', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalled());
    expect(screen.getByText('test-tenant')).toBeInTheDocument();
  });

  it('renders stat cards with token values', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByTestId('usage-cards')).toBeInTheDocument());
    expect(screen.getByText('Total Tokens')).toBeInTheDocument();
    expect(screen.getByText('Console Tokens')).toBeInTheDocument();
    expect(screen.getByText('Portal Tokens')).toBeInTheDocument();
  });

  it('renders period selector buttons', async () => {
    render(<ChatUsageDashboard />);
    expect(screen.getByTestId('period-1')).toBeInTheDocument();
    expect(screen.getByTestId('period-7')).toBeInTheDocument();
    expect(screen.getByTestId('period-30')).toBeInTheDocument();
  });

  it('fetches data with selected period when clicking 7 Days', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId('period-7'));
    await waitFor(() =>
      expect(apiService.getChatUsageTenant).toHaveBeenCalledWith('test-tenant', { days: 7 })
    );
  });

  it('renders source breakdown when tokens > 0', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByTestId('source-breakdown')).toBeInTheDocument());
    expect(screen.getByText('Console')).toBeInTheDocument();
    expect(screen.getByText('Portal')).toBeInTheDocument();
  });

  it('renders budget section', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByTestId('budget-section')).toBeInTheDocument());
    expect(screen.getByText('Daily Budget')).toBeInTheDocument();
    expect(screen.getByTestId('budget-bar')).toBeInTheDocument();
  });

  it('shows refresh button and calls fetch on click', async () => {
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId('refresh-btn'));
    await waitFor(() => expect(apiService.getChatUsageTenant).toHaveBeenCalledTimes(2));
  });

  it('shows no-tenant fallback', () => {
    localStorage.removeItem('stoa-active-tenant');
    const mock = createAuthMock('cpi-admin');
    vi.mocked(useAuth).mockReturnValue({ ...mock, user: { ...mock.user, tenant_id: undefined } });
    render(<ChatUsageDashboard />);
    expect(screen.getByText(/No tenant selected/i)).toBeInTheDocument();
  });

  it('shows error when usage fetch fails', async () => {
    vi.mocked(apiService.getChatUsageTenant).mockRejectedValue(new Error('network'));
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByText(/Failed to load usage data/i)).toBeInTheDocument());
  });

  it('shows budget exceeded message when budget_exceeded is true', async () => {
    vi.mocked(apiService.getChatBudgetStatus).mockResolvedValue({
      ...mockBudget,
      budget_exceeded: true,
      usage_percent: 100,
    });
    render(<ChatUsageDashboard />);
    await waitFor(() => expect(screen.getByText(/Daily budget exceeded/i)).toBeInTheDocument());
  });
});
