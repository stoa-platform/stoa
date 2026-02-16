import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanSelector } from './PlanSelector';
import type { Plan } from '../../types';

const makePlan = (overrides: Partial<Plan> = {}): Plan => ({
  id: 'plan-1',
  slug: 'free',
  name: 'Free',
  description: 'For testing',
  tenant_id: 'tenant-1',
  requires_approval: false,
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...overrides,
});

const plans: Plan[] = [
  makePlan({ id: 'p1', slug: 'free', name: 'Free' }),
  makePlan({
    id: 'p2',
    slug: 'basic',
    name: 'Basic',
    rate_limit_per_minute: 1000,
    daily_request_limit: 50000,
  }),
  makePlan({
    id: 'p3',
    slug: 'premium',
    name: 'Premium',
    monthly_request_limit: 1500000,
  }),
  makePlan({
    id: 'p4',
    slug: 'enterprise',
    name: 'Enterprise',
    requires_approval: true,
  }),
];

describe('PlanSelector', () => {
  it('should render all plans', () => {
    render(<PlanSelector plans={plans} selectedPlanId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('Free')).toBeInTheDocument();
    expect(screen.getByText('Basic')).toBeInTheDocument();
    expect(screen.getByText('Premium')).toBeInTheDocument();
    expect(screen.getByText('Enterprise')).toBeInTheDocument();
  });

  it('should show loading state', () => {
    render(<PlanSelector plans={[]} selectedPlanId={null} onSelect={vi.fn()} isLoading={true} />);
    expect(screen.getByText('Loading plans...')).toBeInTheDocument();
  });

  it('should show empty state when no plans', () => {
    render(<PlanSelector plans={[]} selectedPlanId={null} onSelect={vi.fn()} />);
    expect(screen.getByText(/No plans available/)).toBeInTheDocument();
  });

  it('should call onSelect when plan clicked', () => {
    const onSelect = vi.fn();
    render(<PlanSelector plans={plans} selectedPlanId={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByText('Premium'));
    expect(onSelect).toHaveBeenCalledWith('p3');
  });

  it('should mark selected plan with aria-checked', () => {
    render(<PlanSelector plans={plans} selectedPlanId="p2" onSelect={vi.fn()} />);
    const basicBtn = screen.getByRole('radio', { name: /Basic/ });
    expect(basicBtn).toHaveAttribute('aria-checked', 'true');
  });

  it('should show rate limit per minute', () => {
    render(<PlanSelector plans={plans} selectedPlanId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('1K req/min')).toBeInTheDocument();
  });

  it('should show daily request limit', () => {
    render(<PlanSelector plans={plans} selectedPlanId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('50K req/day')).toBeInTheDocument();
  });

  it('should show monthly request limit with M format', () => {
    render(<PlanSelector plans={plans} selectedPlanId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('2M req/month')).toBeInTheDocument();
  });

  it('should show "Unlimited requests" for plan without limits', () => {
    render(<PlanSelector plans={plans} selectedPlanId={null} onSelect={vi.fn()} />);
    expect(screen.getAllByText('Unlimited requests').length).toBeGreaterThanOrEqual(1);
  });

  it('should show "Requires approval" feature', () => {
    render(<PlanSelector plans={plans} selectedPlanId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('Requires approval')).toBeInTheDocument();
  });

  it('should disable buttons when disabled prop is true', () => {
    render(<PlanSelector plans={plans} selectedPlanId={null} onSelect={vi.fn()} disabled={true} />);
    const buttons = screen.getAllByRole('radio');
    buttons.forEach((btn) => expect(btn).toBeDisabled());
  });

  it('should have radiogroup role', () => {
    render(<PlanSelector plans={plans} selectedPlanId={null} onSelect={vi.fn()} />);
    expect(screen.getByRole('radiogroup')).toBeInTheDocument();
  });

  it('should show rate_limit_per_second when no per_minute', () => {
    const plan = makePlan({
      id: 'ps',
      slug: 'starter',
      name: 'Starter',
      rate_limit_per_second: 10,
    });
    render(<PlanSelector plans={[plan]} selectedPlanId={null} onSelect={vi.fn()} />);
    expect(screen.getByText('10 req/sec')).toBeInTheDocument();
  });
});
