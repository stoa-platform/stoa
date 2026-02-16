import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SubscriptionCard } from './SubscriptionCard';
import type { APISubscription } from '../../types';

const baseSubscription: APISubscription = {
  id: 'sub-1',
  applicationId: 'app-1',
  apiId: 'api-1',
  status: 'active',
  plan: 'basic',
  createdAt: '2026-01-15T10:00:00Z',
  api: { id: 'api-1', name: 'Weather API', version: '2.0' } as APISubscription['api'],
};

function renderCard(props: Partial<React.ComponentProps<typeof SubscriptionCard>> = {}) {
  return render(
    <MemoryRouter>
      <SubscriptionCard subscription={baseSubscription} {...props} />
    </MemoryRouter>
  );
}

describe('SubscriptionCard', () => {
  it('should render API name and version', () => {
    renderCard();
    expect(screen.getByText('Weather API')).toBeInTheDocument();
    expect(screen.getByText('v2.0')).toBeInTheDocument();
  });

  it('should show Active status badge', () => {
    renderCard();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('should show plan badge', () => {
    renderCard();
    expect(screen.getByText('Basic Plan')).toBeInTheDocument();
  });

  it('should show formatted subscription date', () => {
    renderCard();
    expect(screen.getByText(/Subscribed/)).toBeInTheDocument();
    expect(screen.getByText(/Jan 15, 2026/)).toBeInTheDocument();
  });

  it('should render View API Details link', () => {
    renderCard();
    const link = screen.getByText('View API Details');
    expect(link.closest('a')).toHaveAttribute('href', '/apis/api-1');
  });

  it('should show cancel button when active and onCancel provided', () => {
    const onCancel = vi.fn();
    renderCard({ onCancel });
    expect(screen.getByText('Cancel Subscription')).toBeInTheDocument();
  });

  it('should call onCancel with subscription id', () => {
    const onCancel = vi.fn();
    renderCard({ onCancel });
    fireEvent.click(screen.getByText('Cancel Subscription'));
    expect(onCancel).toHaveBeenCalledWith('sub-1');
  });

  it('should show Cancelling... when isCancelling', () => {
    renderCard({ onCancel: vi.fn(), isCancelling: true });
    expect(screen.getByText('Cancelling...')).toBeInTheDocument();
  });

  it('should not show cancel button when status is not active', () => {
    const sub = { ...baseSubscription, status: 'cancelled' as const };
    renderCard({ subscription: sub, onCancel: vi.fn() });
    expect(screen.queryByText('Cancel Subscription')).not.toBeInTheDocument();
  });

  it('should fall back to apiId when api.name is missing', () => {
    const sub = { ...baseSubscription, api: undefined };
    renderCard({ subscription: sub });
    expect(screen.getByText('api-1')).toBeInTheDocument();
  });

  it.each([
    ['pending', 'Pending'],
    ['suspended', 'Suspended'],
    ['cancelled', 'Cancelled'],
  ] as const)('should render %s status', (status, label) => {
    const sub = { ...baseSubscription, status };
    renderCard({ subscription: sub });
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('should show usage stats when available', () => {
    const sub = {
      ...baseSubscription,
      usage: { callsToday: 150, callsThisMonth: 3000, dailyLimit: 1000, monthlyLimit: 30000 },
    };
    renderCard({ subscription: sub });
    expect(screen.getByText('150')).toBeInTheDocument();
    expect(screen.getByText('/ 1,000 limit')).toBeInTheDocument();
  });

  it('should show application link when present', () => {
    const sub = {
      ...baseSubscription,
      applicationId: 'app-1',
      application: { id: 'app-1', name: 'My App' } as APISubscription['application'],
    };
    renderCard({ subscription: sub });
    expect(screen.getByText('My App')).toBeInTheDocument();
  });
});
