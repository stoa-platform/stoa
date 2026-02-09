/**
 * Tests for PlanSelector component (CAB-1121)
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PlanSelector } from './PlanSelector';
import type { Plan } from '../../types';

const mockPlans: Plan[] = [
  {
    id: 'p1',
    slug: 'free',
    name: 'Free Plan',
    description: 'Basic access for evaluation',
    tenant_id: 'tenant-1',
    rate_limit_per_second: 10,
    rate_limit_per_minute: null,
    daily_request_limit: 1000,
    monthly_request_limit: null,
    burst_limit: null,
    requires_approval: false,
    status: 'active',
    created_at: '2026-02-01T10:00:00Z',
    updated_at: '2026-02-01T10:00:00Z',
  },
  {
    id: 'p2',
    slug: 'gold',
    name: 'Gold Plan',
    description: 'Production-grade access',
    tenant_id: 'tenant-1',
    rate_limit_per_second: 100,
    rate_limit_per_minute: null,
    daily_request_limit: 1000000,
    monthly_request_limit: 30000000,
    burst_limit: null,
    requires_approval: true,
    status: 'active',
    created_at: '2026-02-01T10:00:00Z',
    updated_at: '2026-02-01T10:00:00Z',
  },
  {
    id: 'p3',
    slug: 'deprecated',
    name: 'Old Plan',
    description: 'No longer available',
    tenant_id: 'tenant-1',
    rate_limit_per_second: null,
    rate_limit_per_minute: null,
    daily_request_limit: null,
    monthly_request_limit: null,
    burst_limit: null,
    requires_approval: false,
    status: 'deprecated',
    created_at: '2026-02-01T10:00:00Z',
    updated_at: '2026-02-01T10:00:00Z',
  },
];

describe('PlanSelector', () => {
  it('should render active plans only', () => {
    const onSelect = vi.fn();
    render(<PlanSelector plans={mockPlans} onSelect={onSelect} />);

    expect(screen.getByText('Free Plan')).toBeInTheDocument();
    expect(screen.getByText('Gold Plan')).toBeInTheDocument();
    expect(screen.queryByText('Old Plan')).not.toBeInTheDocument();
  });

  it('should render plan descriptions', () => {
    const onSelect = vi.fn();
    render(<PlanSelector plans={mockPlans} onSelect={onSelect} />);

    expect(screen.getByText('Basic access for evaluation')).toBeInTheDocument();
    expect(screen.getByText('Production-grade access')).toBeInTheDocument();
  });

  it('should call onSelect when a plan is clicked', () => {
    const onSelect = vi.fn();
    render(<PlanSelector plans={mockPlans} onSelect={onSelect} />);

    fireEvent.click(screen.getByText('Free Plan'));
    expect(onSelect).toHaveBeenCalledWith(mockPlans[0]);
  });

  it('should show selected state for selected plan', () => {
    const onSelect = vi.fn();
    render(<PlanSelector plans={mockPlans} selectedPlanId="p1" onSelect={onSelect} />);

    // The selected plan should have a check icon (visible by its container)
    const buttons = screen.getAllByRole('button');
    // First button should be selected (Free Plan)
    expect(buttons[0].className).toContain('border-primary-500');
  });

  it('should show "Requires approval" badge', () => {
    const onSelect = vi.fn();
    render(<PlanSelector plans={mockPlans} onSelect={onSelect} />);

    expect(screen.getByText('Requires approval')).toBeInTheDocument();
  });

  it('should format rate limits correctly', () => {
    const onSelect = vi.fn();
    render(<PlanSelector plans={mockPlans} onSelect={onSelect} />);

    // Free plan: 10/s
    expect(screen.getByText('10/s')).toBeInTheDocument();
    // Gold plan: 100/s
    expect(screen.getByText('100/s')).toBeInTheDocument();
  });

  it('should show empty state when no active plans', () => {
    const onSelect = vi.fn();
    render(<PlanSelector plans={[]} onSelect={onSelect} />);

    expect(screen.getByText('No plans available')).toBeInTheDocument();
  });

  it('should show loading skeleton when isLoading', () => {
    const onSelect = vi.fn();
    const { container } = render(<PlanSelector plans={[]} onSelect={onSelect} isLoading={true} />);

    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('should format large numbers with K/M suffixes', () => {
    const onSelect = vi.fn();
    render(<PlanSelector plans={mockPlans} onSelect={onSelect} />);

    // Gold plan: 1M/day, 30M/month
    expect(screen.getByText('1M/day')).toBeInTheDocument();
    expect(screen.getByText('30M/month')).toBeInTheDocument();
  });
});
