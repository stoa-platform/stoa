import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SubscribeWithPlanModal } from './SubscribeWithPlanModal';
import { renderWithProviders, createAuthMock } from '../../test/helpers';
import type { API } from '../../types';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../hooks/useApplications', () => ({
  useApplications: vi.fn(),
}));

vi.mock('../../hooks/usePlans', () => ({
  usePlans: vi.fn(),
}));

vi.mock('./PlanSelector', () => ({
  PlanSelector: ({
    plans,
    selectedPlanId,
    onSelect,
  }: {
    plans: { id: string; name: string }[];
    selectedPlanId: string | null;
    onSelect: (id: string) => void;
  }) => (
    <div data-testid="plan-selector">
      {plans.map((p: { id: string; name: string }) => (
        <button
          key={p.id}
          data-testid={`plan-${p.id}`}
          onClick={() => onSelect(p.id)}
          aria-pressed={selectedPlanId === p.id}
        >
          {p.name}
        </button>
      ))}
    </div>
  ),
}));

vi.mock('@stoa/shared/components/Button', () => ({
  Button: ({
    children,
    loading,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }) => (
    <button {...props}>{loading ? 'Loading...' : children}</button>
  ),
}));

import { useAuth } from '../../contexts/AuthContext';
import { useApplications } from '../../hooks/useApplications';
import { usePlans } from '../../hooks/usePlans';

const mockApi: API = {
  id: 'api-1',
  name: 'Payment API',
  version: '2.1.0',
  description: 'Process payments',
  category: 'Finance',
  tags: ['payments'],
  tenantId: 'oasis',
  tenantName: 'OASIS',
  status: 'published',
  endpoints: [],
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-02-01T00:00:00Z',
};

const mockApps = {
  items: [
    { id: 'app-1', name: 'My App', status: 'active' },
    { id: 'app-2', name: 'Other App', status: 'active' },
  ],
};

const mockPlans = {
  items: [
    { id: 'plan-1', name: 'Free', status: 'active', requires_approval: false },
    { id: 'plan-2', name: 'Pro', status: 'active', requires_approval: true },
    { id: 'plan-3', name: 'Archived', status: 'inactive' },
  ],
};

describe('SubscribeWithPlanModal', () => {
  const onClose = vi.fn();
  const onSubmit = vi.fn().mockResolvedValue(undefined);

  const defaultProps = {
    isOpen: true,
    onClose,
    onSubmit,
    api: mockApi,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useAuth).mockReturnValue(createAuthMock('tenant-admin'));
    vi.mocked(useApplications).mockReturnValue({
      data: mockApps,
      isLoading: false,
    } as ReturnType<typeof useApplications>);
    vi.mocked(usePlans).mockReturnValue({
      data: mockPlans,
      isLoading: false,
    } as ReturnType<typeof usePlans>);
  });

  it('should return null when not open', () => {
    const { container } = renderWithProviders(
      <SubscribeWithPlanModal {...defaultProps} isOpen={false} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('should render modal header with API name and version', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);
    expect(screen.getByText('Subscribe to API')).toBeInTheDocument();
    expect(screen.getByText('Payment API v2.1.0')).toBeInTheDocument();
  });

  it('should render application select with active apps', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);
    expect(screen.getByText('Select an application...')).toBeInTheDocument();
    expect(screen.getByText('My App')).toBeInTheDocument();
    expect(screen.getByText('Other App')).toBeInTheDocument();
  });

  it('should show no-apps message when no active applications', () => {
    vi.mocked(useApplications).mockReturnValue({
      data: { items: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof useApplications>);
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);
    expect(screen.getByText(/No active applications/)).toBeInTheDocument();
    expect(screen.getByText('Go to My Apps')).toBeInTheDocument();
  });

  it('should show loading state for applications', () => {
    vi.mocked(useApplications).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as unknown as ReturnType<typeof useApplications>);
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);
    expect(screen.getByText('Loading applications...')).toBeInTheDocument();
  });

  it('should render plan selector with only active plans', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);
    expect(screen.getByTestId('plan-selector')).toBeInTheDocument();
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByText('Pro')).toBeInTheDocument();
    expect(screen.queryByText('Archived')).not.toBeInTheDocument();
  });

  it('should show error when error prop is passed', () => {
    renderWithProviders(
      <SubscribeWithPlanModal {...defaultProps} error="Subscription limit reached" />
    );
    expect(screen.getByText('Subscription limit reached')).toBeInTheDocument();
  });

  it('should not close when isLoading', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} isLoading={true} />);
    await user.click(screen.getByText('Cancel'));
    expect(onClose).not.toHaveBeenCalled();
  });

  it('should close when cancel clicked and not loading', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);
    await user.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalled();
  });

  it('should disable subscribe button when no app or plan selected', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);
    expect(screen.getByText('Subscribe')).toBeDisabled();
  });

  it('should show approval notice when plan requires approval', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    // Select an app
    await user.selectOptions(screen.getByRole('combobox'), 'app-1');

    // Select plan-2 (Pro, requires_approval)
    await user.click(screen.getByTestId('plan-plan-2'));

    await waitFor(() => {
      expect(screen.getByText(/This plan requires admin approval/)).toBeInTheDocument();
    });
  });
});
