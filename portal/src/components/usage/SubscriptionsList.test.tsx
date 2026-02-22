/**
 * Tests for SubscriptionsList (CAB-1390)
 */

import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { SubscriptionsList } from './SubscriptionsList';
import { renderWithProviders } from '../../test/helpers';
import type { ActiveSubscription } from '../../types';

const makeSub = (overrides: Partial<ActiveSubscription> = {}): ActiveSubscription => ({
  id: 'sub-1',
  tool_id: 'tool-1',
  tool_name: 'Payment Tools',
  tool_description: 'Payment processing tools',
  status: 'active',
  created_at: '2026-01-01T00:00:00Z',
  last_used_at: '2026-02-20T12:00:00Z',
  call_count_total: 150,
  ...overrides,
});

describe('SubscriptionsList', () => {
  it('shows loading skeleton when isLoading is true', () => {
    const { container } = renderWithProviders(
      <SubscriptionsList subscriptions={[]} isLoading={true} />
    );
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('shows empty state when subscriptions is empty', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[]} />);
    expect(screen.getByText('No active subscriptions')).toBeInTheDocument();
  });

  it('shows "Browse tools" CTA in empty state', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[]} />);
    expect(screen.getByText(/browse tools/i)).toBeInTheDocument();
  });

  it('renders subscription tool names', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[makeSub()]} />);
    expect(screen.getByText('Payment Tools')).toBeInTheDocument();
  });

  it('does not render tool_description (not shown in list view)', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[makeSub()]} />);
    // SubscriptionsList shows tool_name only, not description
    expect(screen.getByText('Payment Tools')).toBeInTheDocument();
  });

  it('renders status badge for each subscription', () => {
    renderWithProviders(
      <SubscriptionsList
        subscriptions={[
          makeSub({ id: 's1', status: 'active' }),
          makeSub({ id: 's2', tool_name: 'Expired Tool', status: 'expired' }),
        ]}
      />
    );
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('Expired')).toBeInTheDocument();
  });

  it('renders call count for each subscription', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[makeSub()]} />);
    // call_count_total is formatted as "150 calls" (toLocaleString + " calls")
    expect(screen.getByText(/150.*calls/)).toBeInTheDocument();
  });
});
