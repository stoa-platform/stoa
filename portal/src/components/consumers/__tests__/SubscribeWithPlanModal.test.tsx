import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { SubscribeWithPlanModal } from '../SubscribeWithPlanModal';
import {
  renderWithProviders,
  createAuthMock,
  mockAPI,
  mockApplication,
} from '../../../test/helpers';

const mockUseAuth = vi.fn();
vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => mockUseAuth(),
}));

vi.mock('../../../hooks/useApplications', () => ({
  useApplications: vi.fn(() => ({
    data: { items: [] },
    isLoading: false,
  })),
}));

vi.mock('../../../hooks/usePlans', () => ({
  usePlans: vi.fn(() => ({
    data: { items: [] },
    isLoading: false,
  })),
}));

vi.mock('../PlanSelector', () => ({
  PlanSelector: ({
    plans,
    onSelect,
  }: {
    plans: { id: string; name: string }[];
    onSelect: (id: string) => void;
  }) => (
    <div data-testid="plan-selector">
      {plans.map((p) => (
        <button key={p.id} onClick={() => onSelect(p.id)}>
          {p.name}
        </button>
      ))}
    </div>
  ),
}));

describe('SubscribeWithPlanModal', () => {
  const api = mockAPI();
  const defaultProps = {
    isOpen: true,
    onClose: vi.fn(),
    onSubmit: vi.fn().mockResolvedValue(undefined),
    api: api as never,
    isLoading: false,
    error: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
    defaultProps.onClose = vi.fn();
    defaultProps.onSubmit = vi.fn().mockResolvedValue(undefined);
    mockUseAuth.mockReturnValue(createAuthMock('tenant-admin'));
  });

  it('renders nothing when closed', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} isOpen={false} />);

    expect(screen.queryByText('Subscribe to API')).not.toBeInTheDocument();
  });

  it('renders modal when open', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    expect(screen.getByText('Subscribe to API')).toBeInTheDocument();
  });

  it('renders API name and version in header', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    expect(screen.getByText(`${api.name} v${api.version}`)).toBeInTheDocument();
  });

  it('renders application selector label', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    expect(screen.getByText(/Application/)).toBeInTheDocument();
  });

  it('renders empty application message when no active apps', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    expect(
      screen.getByText('No active applications. Create an application first.')
    ).toBeInTheDocument();
  });

  it('renders loading state for applications', async () => {
    const { useApplications } = await import('../../../hooks/useApplications');
    vi.mocked(useApplications).mockReturnValue({ data: undefined, isLoading: true } as never);

    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    expect(screen.getByText('Loading applications...')).toBeInTheDocument();
  });

  it('renders application dropdown when apps available', async () => {
    const { useApplications } = await import('../../../hooks/useApplications');
    vi.mocked(useApplications).mockReturnValue({
      data: { items: [mockApplication({ status: 'active' })] },
      isLoading: false,
    } as never);

    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    expect(screen.getByRole('combobox')).toBeInTheDocument();
    expect(screen.getByText('My App')).toBeInTheDocument();
  });

  it('renders PlanSelector component', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    expect(screen.getByTestId('plan-selector')).toBeInTheDocument();
  });

  it('renders error message when error prop is set', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} error="Subscription failed" />);

    expect(screen.getByText('Subscription failed')).toBeInTheDocument();
  });

  it('calls onClose when Cancel clicked', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    fireEvent.click(screen.getByText('Cancel'));
    expect(defaultProps.onClose).toHaveBeenCalledOnce();
  });

  it('subscribe button is disabled when no app or plan selected', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} />);

    expect(screen.getByText('Subscribe')).toBeDisabled();
  });

  it('shows loading state when isLoading is true', () => {
    renderWithProviders(<SubscribeWithPlanModal {...defaultProps} isLoading={true} />);

    expect(screen.getByText('Subscribing...')).toBeInTheDocument();
  });
});
