import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { SubscriptionsList } from '../SubscriptionsList';
import { renderWithProviders } from '../../../test/helpers';
import type { ActiveSubscription } from '../../../types';

const makeSub = (overrides: Partial<ActiveSubscription> = {}): ActiveSubscription => ({
  id: 'sub-1',
  tool_id: 'tool-1',
  tool_name: 'list-apis',
  status: 'active',
  created_at: '2026-01-15T00:00:00Z',
  last_used_at: new Date(Date.now() - 10 * 60000).toISOString(), // 10 min ago
  call_count_total: 500,
  ...overrides,
});

describe('SubscriptionsList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Active Subscriptions heading', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[]} />);

    expect(screen.getByText('Active Subscriptions')).toBeInTheDocument();
  });

  it('renders empty state when no subscriptions', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[]} />);

    expect(screen.getByText('No active subscriptions')).toBeInTheDocument();
  });

  it('renders Browse tools link in empty state', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[]} />);

    expect(screen.getByText('Browse tools →')).toBeInTheDocument();
  });

  it('renders subscription count in heading', () => {
    const subs = [makeSub({ id: 'sub-1' }), makeSub({ id: 'sub-2' })];
    renderWithProviders(<SubscriptionsList subscriptions={subs} />);

    expect(screen.getByText('(2)')).toBeInTheDocument();
  });

  it('renders subscription tool name', () => {
    const sub = makeSub({ tool_name: 'create-order' });
    renderWithProviders(<SubscriptionsList subscriptions={[sub]} />);

    expect(screen.getByText('create-order')).toBeInTheDocument();
  });

  it('renders active status badge', () => {
    const sub = makeSub({ status: 'active' });
    renderWithProviders(<SubscriptionsList subscriptions={[sub]} />);

    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders suspended status badge', () => {
    const sub = makeSub({ status: 'suspended' });
    renderWithProviders(<SubscriptionsList subscriptions={[sub]} />);

    expect(screen.getByText('Suspended')).toBeInTheDocument();
  });

  it('renders call count', () => {
    const sub = makeSub({ call_count_total: 1500 });
    renderWithProviders(<SubscriptionsList subscriptions={[sub]} />);

    expect(screen.getByText('1,500 calls')).toBeInTheDocument();
  });

  it('renders Never when no last_used_at', () => {
    const sub = makeSub({ last_used_at: null });
    renderWithProviders(<SubscriptionsList subscriptions={[sub]} />);

    expect(screen.getByText('Last used Never')).toBeInTheDocument();
  });

  it('renders View all link', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[makeSub()]} />);

    expect(screen.getByText('View all')).toBeInTheDocument();
  });

  it('renders link to tool detail for each subscription', () => {
    const sub = makeSub({ tool_id: 'tool-42' });
    renderWithProviders(<SubscriptionsList subscriptions={[sub]} />);

    const links = screen.getAllByRole('link');
    const toolLink = links.find((l) => l.getAttribute('href') === '/tools/tool-42');
    expect(toolLink).toBeTruthy();
  });

  it('renders loading skeleton when isLoading is true', () => {
    renderWithProviders(<SubscriptionsList subscriptions={[]} isLoading={true} />);

    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('renders multiple subscriptions', () => {
    const subs = [
      makeSub({ id: 'sub-1', tool_name: 'list-apis' }),
      makeSub({ id: 'sub-2', tool_name: 'create-order' }),
      makeSub({ id: 'sub-3', tool_name: 'delete-user' }),
    ];
    renderWithProviders(<SubscriptionsList subscriptions={subs} />);

    expect(screen.getByText('list-apis')).toBeInTheDocument();
    expect(screen.getByText('create-order')).toBeInTheDocument();
    expect(screen.getByText('delete-user')).toBeInTheDocument();
  });
});
